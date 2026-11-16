"""Event-driven daily portfolio simulation.

`run(signals, prices, calendar, cfg, cash_returns)` is a pure function: no I/O, no database.

Timing conventions (all pre-registered in PREREG.md):
- Trades happen at the OPEN. Positions are marked at the CLOSE. Cash accrues the day's cash
  return after the day's trades.
- Each trading day, in order:
    1. Mark held positions from yesterday's close to today's open.
    2. Exits at the open: hold limit reached, or a sale by one of the position's source filers
       with entry_date == today.
    3. Entries at the open: buy signals with entry_date == today. A buy on an already-held
       security adds to that position's sources and does not reset its hold clock.
    4. If anything changed (or a delisting happened at yesterday's close), rebalance to equal
       weight. turnover = value sold on exits + sum |target - current| over remaining positions,
       with targets computed on pre-cost equity E. cost = bps * turnover, and each post-trade
       position is (E - cost) / n. With no positions left, cash = E - cost.
    5. Mark positions open-to-close. A security whose `delist_return` is set on this date (or
       whose price history ends before the calendar does) is removed at the close after
       applying that return; its proceeds go to cash.
    6. Accrue the cash return; record the day.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from cti.backtest.costs import cost_rate


class LookAheadError(AssertionError):
    """Raised when an input would let the strategy trade on information before it was public."""


@dataclass(frozen=True)
class EngineConfig:
    hold_trading_days: int = 126
    early_exit_on_filer_sale: bool = True
    cost_bps_per_side: float = 10.0
    starting_nav: float = 1.0
    no_price_delist_return: float = -1.0

    @classmethod
    def from_prereg(cls, cfg, cost_scenario: str = "base", hold_trading_days: int | None = None):
        p = cfg.portfolio
        return cls(
            hold_trading_days=int(hold_trading_days or p["hold_trading_days"]),
            early_exit_on_filer_sale=bool(p["early_exit_on_filer_sale"]),
            cost_bps_per_side=cfg.cost_bps(cost_scenario),
            starting_nav=float(p.get("starting_nav", 1.0)),
            no_price_delist_return=float(cfg["delisting"]["no_price"]),
        )


@dataclass
class _Position:
    position_id: int
    security_id: str
    entry_idx: int
    entry_date: dt.date
    value: float = 0.0
    last_close: float | None = None
    growth: float = 1.0  # product of price relatives while held (the stock's own return)
    filers: set = field(default_factory=set)
    signal_ids: list = field(default_factory=list)


@dataclass
class EngineResult:
    daily: pd.DataFrame
    positions: pd.DataFrame
    skipped_signals: pd.DataFrame


SIGNAL_COLUMNS = ["signal_id", "side", "security_id", "filer_id", "public_date", "entry_date"]
PRICE_COLUMNS = ["security_id", "date", "open", "close"]


def _to_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s).dt.date


def validate_signals(signals: pd.DataFrame) -> pd.DataFrame:
    missing = set(SIGNAL_COLUMNS) - set(signals.columns)
    if missing:
        raise ValueError(f"signals missing columns: {sorted(missing)}")
    s = signals.copy()
    s["public_date"] = _to_date(s["public_date"])
    s["entry_date"] = _to_date(s["entry_date"])
    bad = s[~(s["entry_date"] > s["public_date"])]
    if len(bad):
        raise LookAheadError(
            f"{len(bad)} signal(s) enter on or before their public date, e.g. "
            f"{bad.iloc[0][['signal_id', 'public_date', 'entry_date']].to_dict()}"
        )
    if not set(s["side"]).issubset({"buy", "sell"}):
        raise ValueError("signal side must be 'buy' or 'sell'")
    return s


def run(signals: pd.DataFrame, prices: pd.DataFrame, calendar, cfg: EngineConfig,
        cash_returns: pd.Series | None = None) -> EngineResult:
    sig = validate_signals(signals)
    missing = set(PRICE_COLUMNS) - set(prices.columns)
    if missing:
        raise ValueError(f"prices missing columns: {sorted(missing)}")

    days = sorted(pd.to_datetime(pd.Series(list(calendar))).dt.date)
    if not days:
        raise ValueError("empty calendar")
    rate = cost_rate(cfg.cost_bps_per_side)

    # Lookups: day x security arrays (NaN = no quote). The loop only ever reads row i (today),
    # so it cannot see future prices. Only securities with a buy signal are needed.
    n_days = len(days)
    day_idx = {d: i for i, d in enumerate(days)}
    secs = sorted(set(sig.loc[sig["side"] == "buy", "security_id"]))
    sec_idx = {s: j for j, s in enumerate(secs)}
    opens = np.full((n_days, len(secs)), np.nan)
    C = np.full_like(opens, np.nan)
    D = np.full_like(opens, np.nan)
    p = prices[prices["security_id"].isin(sec_idx)]
    pi = _to_date(p["date"]).map(day_idx)
    keep = pi.notna().to_numpy()
    rows = pi[keep].astype(int).to_numpy()
    cols = p["security_id"][keep].map(sec_idx).to_numpy()
    opens[rows, cols] = p["open"].to_numpy(dtype=float)[keep]
    C[rows, cols] = p["close"].to_numpy(dtype=float)[keep]
    if "delist_return" in p.columns:
        D[rows, cols] = pd.to_numeric(p["delist_return"], errors="coerce").to_numpy(dtype=float)[keep]
    has_q = ~np.isnan(opens) & ~np.isnan(C)
    last_idx = np.where(has_q.any(axis=0), n_days - 1 - np.argmax(has_q[::-1], axis=0), -1)

    def quote(sec: str, i: int):
        j = sec_idx.get(sec)
        if j is None or not has_q[i, j]:
            return None
        return opens[i, j], C[i, j], D[i, j], j

    cash_ret = {} if cash_returns is None else {
        pd.Timestamp(k).date(): float(v) for k, v in cash_returns.items()}

    buys_by_day: dict[dt.date, list] = defaultdict(list)
    sells_by_day: dict[dt.date, list] = defaultdict(list)
    for r in sig.sort_values(["entry_date", "signal_id"]).itertuples(index=False):
        (buys_by_day if r.side == "buy" else sells_by_day)[r.entry_date].append(r)

    held: dict[str, _Position] = {}
    cash = cfg.starting_nav
    next_id = 1
    pending_rebalance = False
    daily_rows, closed_rows, skipped = [], [], []

    def close_out(pos: _Position, date: dt.date, reason: str) -> None:
        closed_rows.append({
            "position_id": pos.position_id, "security_id": pos.security_id,
            "entry_date": pos.entry_date, "exit_date": date, "exit_reason": reason,
            "source_signal_ids": list(pos.signal_ids), "exit_value": pos.value,
            "gross_return": pos.growth - 1.0,
        })

    for i, today in enumerate(days):
        # 1. Yesterday's close -> today's open.
        for pos in held.values():
            q = quote(pos.security_id, i)
            if q and pos.last_close:
                pos.value *= q[0] / pos.last_close
                pos.growth *= q[0] / pos.last_close

        # 2. Exits at the open.
        sold_value = 0.0
        exiting: dict[str, str] = {}
        for sec, pos in held.items():
            if i - pos.entry_idx >= cfg.hold_trading_days:
                exiting[sec] = "hold_limit"
        if cfg.early_exit_on_filer_sale:
            for s in sells_by_day.get(today, []):
                pos = held.get(s.security_id)
                if pos and s.security_id not in exiting and s.filer_id in pos.filers:
                    exiting[s.security_id] = "filer_sale"
        for sec, reason in exiting.items():
            pos = held.pop(sec)
            sold_value += pos.value
            cash += pos.value
            close_out(pos, today, reason)

        # 3. Entries at the open.
        new_entries = 0
        for b in buys_by_day.get(today, []):
            pos = held.get(b.security_id)
            if pos is not None:
                pos.filers.add(b.filer_id)
                pos.signal_ids.append(b.signal_id)
                continue
            if quote(b.security_id, i) is None:
                skipped.append({"signal_id": b.signal_id, "date": today, "reason": "no_price_on_entry"})
                continue
            held[b.security_id] = _Position(next_id, b.security_id, i, today,
                                            filers={b.filer_id}, signal_ids=[b.signal_id])
            next_id += 1
            new_entries += 1

        # 4. Rebalance to equal weight.
        turnover = cost = 0.0
        if exiting or new_entries or pending_rebalance:
            equity = cash + sum(pos.value for pos in held.values())
            n = len(held)
            if n:
                target = equity / n
                turnover = sold_value + sum(abs(target - pos.value) for pos in held.values())
                cost = rate * turnover
                for pos in held.values():
                    pos.value = (equity - cost) / n
                cash = 0.0
            else:
                turnover = sold_value
                cost = rate * turnover
                cash = equity - cost
            pending_rebalance = False

        # 5. Open -> close, then delistings.
        for sec in list(held):
            pos = held[sec]
            q = quote(sec, i)
            if q is None:
                continue
            o, c, dr, j = q
            if o > 0:
                pos.value *= c / o
                pos.growth *= c / o
            pos.last_close = c
            ends_early = i == last_idx[j] and i < n_days - 1
            if not math.isnan(dr) or ends_early:
                r = dr if not math.isnan(dr) else cfg.no_price_delist_return
                pos.value *= 1.0 + r
                pos.growth *= 1.0 + r
                held.pop(sec)
                cash += pos.value
                close_out(pos, today, "delist")
                pending_rebalance = bool(held) or pending_rebalance

        # 6. Cash return and record.
        cash *= 1.0 + cash_ret.get(today, 0.0)
        nav = cash + sum(pos.value for pos in held.values())
        daily_rows.append({"date": today, "nav": nav, "cash": cash, "n_positions": len(held),
                           "turnover": turnover, "cost_paid": cost})

    for pos in held.values():
        closed_rows.append({
            "position_id": pos.position_id, "security_id": pos.security_id,
            "entry_date": pos.entry_date, "exit_date": None, "exit_reason": "open",
            "source_signal_ids": list(pos.signal_ids), "exit_value": pos.value,
            "gross_return": pos.growth - 1.0,
        })

    positions = pd.DataFrame(closed_rows, columns=[
        "position_id", "security_id", "entry_date", "exit_date", "exit_reason",
        "source_signal_ids", "exit_value", "gross_return"]).sort_values("position_id", ignore_index=True)
    return EngineResult(
        daily=pd.DataFrame(daily_rows),
        positions=positions,
        skipped_signals=pd.DataFrame(skipped, columns=["signal_id", "date", "reason"]),
    )
