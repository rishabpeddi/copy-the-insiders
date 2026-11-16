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
    4. Rebalance, per `cfg.rebalance`. Target weight of a position = its score / total score
       (score = 1 for equal weighting, or the sum of its signals' `weight` column).
       - "monthly_drift" (pre-registered primary): new entries get their target share of equity
         E, funded from cash first and then pro rata from existing positions; otherwise weights
         drift and exit proceeds sit in cash. On the first trading day of each month everything
         is reset to target weights. turnover = exits sold + entry buys + funding sales.
       - "on_entry_or_exit" (sensitivity): reset everything to target weights on any day a
         position opens or closes.
       For a full reset, turnover = value sold on exits + sum |target - current| with targets on
       pre-cost equity E; cost = bps * turnover and each post-trade position is target*(E-cost)/E.
       For entry funding, the cost is taken from the new positions pro rata.
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
    rebalance: str = "on_entry_or_exit"   # or "monthly_drift"
    weighting: str = "equal"              # or "signal" (uses the signals' `weight` column)
    record_month_end_holdings: bool = True  # for the sector-clone benchmark

    @classmethod
    def from_prereg(cls, cfg, cost_scenario: str = "base", hold_trading_days: int | None = None,
                    rebalance: str | None = None, weighting: str | None = None):
        p = cfg.portfolio
        return cls(
            hold_trading_days=int(hold_trading_days or p["hold_trading_days"]),
            early_exit_on_filer_sale=bool(p["early_exit_on_filer_sale"]),
            cost_bps_per_side=cfg.cost_bps(cost_scenario),
            starting_nav=float(p.get("starting_nav", 1.0)),
            no_price_delist_return=float(cfg["delisting"]["no_price"]),
            rebalance=rebalance or p["rebalance"],
            weighting=weighting or ("equal" if p["weighting"] == "equal" else "signal"),
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
    score: float = 1.0   # weighting score (1 for equal weight)
    filers: set = field(default_factory=set)
    signal_ids: list = field(default_factory=list)


@dataclass
class EngineResult:
    daily: pd.DataFrame
    positions: pd.DataFrame
    skipped_signals: pd.DataFrame
    holdings: pd.DataFrame = field(default_factory=pd.DataFrame)  # month-end: date, security_id, value


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

    # Lookups: per security, arrays over just its own span of calendar days (sparse; memory grows
    # with price rows, not days x securities). The loop only ever reads day i (today), so it
    # cannot see future prices. Only securities with a buy signal are needed.
    n_days = len(days)
    day_idx = {d: i for i, d in enumerate(days)}
    wanted = set(sig.loc[sig["side"] == "buy", "security_id"])
    p = prices[prices["security_id"].isin(wanted)].copy()
    dup = p.duplicated(["security_id", "date"], keep=False)
    if dup.any():
        ex = p.loc[dup, "security_id"].iloc[0]
        raise ValueError(f"{int(dup.sum())} duplicate (security_id, date) price rows, e.g. {ex}: two price "
                         "series under one security would make returns meaningless")
    p["i"] = _to_date(p["date"]).map(day_idx)
    p = p.dropna(subset=["i"])
    p["i"] = p["i"].astype(int)
    if "delist_return" not in p.columns:
        p["delist_return"] = np.nan
    p["delist_return"] = pd.to_numeric(p["delist_return"], errors="coerce")
    book: dict[str, tuple] = {}  # sec -> (start, opens, closes, delist, has_quote, last_idx)
    for sec, g in p.sort_values("i").groupby("security_id", sort=False):
        i0, i1 = int(g["i"].iloc[0]), int(g["i"].iloc[-1])
        o = np.full(i1 - i0 + 1, np.nan)
        c = np.full_like(o, np.nan)
        d = np.full_like(o, np.nan)
        k = g["i"].to_numpy() - i0
        o[k] = g["open"].to_numpy(dtype=float)
        c[k] = g["close"].to_numpy(dtype=float)
        d[k] = g["delist_return"].to_numpy(dtype=float)
        hq = ~np.isnan(o) & ~np.isnan(c)
        last = i0 + int(np.nonzero(hq)[0][-1]) if hq.any() else -1
        book[sec] = (i0, o, c, d, hq, last)

    def quote(sec: str, i: int):
        b = book.get(sec)
        if b is None:
            return None
        i0, o, c, d, hq, last = b
        k = i - i0
        if k < 0 or k >= len(o) or not hq[k]:
            return None
        return o[k], c[k], d[k], last

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
    daily_rows, closed_rows, skipped, hold_rows = [], [], [], []

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
        new_secs: list[str] = []
        for b in buys_by_day.get(today, []):
            w = float(getattr(b, "weight", 1.0)) if cfg.weighting == "signal" else 1.0
            pos = held.get(b.security_id)
            if pos is not None:
                pos.filers.add(b.filer_id)
                pos.signal_ids.append(b.signal_id)
                if cfg.weighting == "signal":
                    pos.score += w  # takes effect at the next full rebalance
                continue
            if quote(b.security_id, i) is None:
                skipped.append({"signal_id": b.signal_id, "date": today, "reason": "no_price_on_entry"})
                continue
            held[b.security_id] = _Position(next_id, b.security_id, i, today, score=w,
                                            filers={b.filer_id}, signal_ids=[b.signal_id])
            new_secs.append(b.security_id)
            next_id += 1
            new_entries += 1

        # 4. Rebalance.
        turnover = cost = 0.0
        month_start = i > 0 and (today.year, today.month) != (days[i - 1].year, days[i - 1].month)
        if cfg.rebalance == "monthly_drift":
            full = month_start and bool(held)
            fund_only = bool(new_entries) and not full
        else:
            full = bool(exiting or new_entries or pending_rebalance)
            fund_only = False
        if full:
            equity = cash + sum(pos.value for pos in held.values())
            total = sum(pos.score for pos in held.values())
            if held:
                tgt = {sec: equity * pos.score / total for sec, pos in held.items()}
                turnover = sold_value + sum(abs(tgt[sec] - pos.value) for sec, pos in held.items())
                cost = rate * turnover
                for sec, pos in held.items():
                    pos.value = tgt[sec] * (equity - cost) / equity
                cash = 0.0
            else:
                turnover = sold_value
                cost = rate * turnover
                cash = equity - cost
            pending_rebalance = False
        elif fund_only:
            equity = cash + sum(pos.value for pos in held.values())
            total = sum(pos.score for pos in held.values())
            tgt = {sec: equity * held[sec].score / total for sec in new_secs}
            need = sum(tgt.values())
            from_cash = min(cash, need)
            from_pos = need - from_cash
            existing = [pos for sec, pos in held.items() if sec not in tgt]
            ex_val = sum(pos.value for pos in existing)
            if from_pos > 0 and ex_val > 0:
                for pos in existing:
                    pos.value -= from_pos * pos.value / ex_val
            cash -= from_cash
            turnover = sold_value + need + from_pos
            cost = rate * turnover
            for sec, v in tgt.items():
                held[sec].value = v - cost * v / need
        elif exiting:
            turnover = sold_value
            cost = rate * turnover
            cash -= cost

        # 5. Open -> close, then delistings.
        for sec in list(held):
            pos = held[sec]
            q = quote(sec, i)
            if q is None:
                continue
            o, c, dr, last = q
            if o > 0:
                pos.value *= c / o
                pos.growth *= c / o
            pos.last_close = c
            ends_early = i == last and i < n_days - 1
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
        month_end = i == n_days - 1 or (days[i + 1].year, days[i + 1].month) != (today.year, today.month)
        if cfg.record_month_end_holdings and month_end:
            hold_rows += [{"date": today, "security_id": sec, "value": pos.value} for sec, pos in held.items()]

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
        holdings=pd.DataFrame(hold_rows, columns=["date", "security_id", "value"]),
    )
