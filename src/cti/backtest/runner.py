"""Load one period's inputs from the warehouse, run the engine, compute metrics, write results.

Test-period runs go through cti.lock first (see cli.run_cmd); this module never decides that.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from cti.backtest.engine import EngineConfig, EngineResult, run
from cti.config import DATA_DIR, REPORTS_DIR, Config
from cti.stats.bootstrap import TRADING_DAYS, block_bootstrap_ci
from cti.stats.power import minimum_detectable_alpha


def _period_bounds(cfg: Config, period: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start, end = cfg.period(period)
    return pd.Timestamp(start), pd.Timestamp(end) if end else pd.Timestamp.today().normalize()


GROUPS = {"insider": ("signals_insider", "signals_insider_sells"),
          "congress": ("signals_congress", "signals_congress_sells")}


def load_inputs(cfg: Config, period: str, data_dir: Path = DATA_DIR, group: str = "insider") -> dict:
    buys_t, sells_t = GROUPS[group]
    lo, hi = _period_bounds(cfg, period)
    con = duckdb.connect(str(data_dir / "warehouse.duckdb"), read_only=True)
    try:
        q = lambda sql: con.execute(sql, [lo, hi]).df()  # noqa: E731
        buys = q("SELECT signal_id, side, security_id, filer_id, public_date, entry_date "
                 f"FROM {buys_t} WHERE entry_date BETWEEN ? AND ?")
        # A group whose data starts after the period start (House PTRs: 2015) is evaluated from its
        # first signal, not padded with a year of T-bills.
        if len(buys):
            lo = max(lo, pd.Timestamp(buys["entry_date"].min()))
        cal = q("SELECT date FROM calendar WHERE date BETWEEN ? AND ? ORDER BY date")["date"]
        sells = q("SELECT signal_id, side, security_id, filer_id, public_date, entry_date "
                  f"FROM {sells_t} WHERE entry_date BETWEEN ? AND ?")
        prices = q("SELECT security_id, date, adj_open AS open, adj_close AS close, delist_return "
                   "FROM prices_daily WHERE date BETWEEN ? AND ? "
                   f"AND security_id IN (SELECT DISTINCT security_id FROM {buys_t})")
        ref = q("SELECT date, series, total_return FROM reference_returns "
                "WHERE date BETWEEN ? AND ? AND series IN ('SPY', 'TBILL')")
    finally:
        con.close()
    ref = ref.pivot(index="date", columns="series", values="total_return").reindex(pd.DatetimeIndex(cal))

    # Delisting rule for the free source: yfinance gives no reason, so a history that ends inside
    # the period is treated as `delisting.other: last_price` (exit at the last close, return 0).
    last = prices.groupby("security_id")["date"].transform("max")
    ends_inside = (prices["date"] == last) & (last < pd.Timestamp(cal.iloc[-1]))
    prices.loc[ends_inside, "delist_return"] = 0.0
    return {"calendar": list(cal), "signals": pd.concat([buys, sells], ignore_index=True),
            "prices": prices, "spy": ref["SPY"].fillna(0.0), "tbill": ref["TBILL"].fillna(0.0),
            "n_delisted_last_price": int(ends_inside.sum()), "start": pd.Timestamp(cal.iloc[0]).date()}


def metrics(res: EngineResult, spy: pd.Series, tbill: pd.Series, cfg: Config, test_years: float) -> dict:
    d = res.daily.set_index(pd.DatetimeIndex(res.daily["date"]))
    r = d["nav"].pct_change().fillna(d["nav"].iloc[0] / cfg.portfolio.get("starting_nav", 1.0) - 1)
    spy = spy.reindex(r.index).fillna(0.0)
    tb = tbill.reindex(r.index).fillna(0.0)
    active = (r - spy).to_numpy()
    years = len(r) / TRADING_DAYS
    nav_end = float(d["nav"].iloc[-1])
    spy_end = float((1 + spy).prod())
    vol = float(r.std() * np.sqrt(TRADING_DAYS))
    te = float(np.std(active, ddof=1) * np.sqrt(TRADING_DAYS))
    beta = float(np.cov(r, spy)[0, 1] / np.var(spy, ddof=1))
    jensen = float(((r - tb) - beta * (spy - tb)).mean() * TRADING_DAYS)
    inf = cfg["inference"]
    point, lo, hi = block_bootstrap_ci(active, block_months=int(inf["block_months"]), reps=int(inf["reps"]),
                                       alpha=float(inf["alpha"]), seed=int(inf["seed"]))
    dd = float((d["nav"] / d["nav"].cummax() - 1).min())
    pos = res.positions
    return {
        "years": round(years, 2),
        "cagr": nav_end ** (1 / years) - 1, "spy_cagr": spy_end ** (1 / years) - 1,
        "ann_vol": vol, "sharpe": float((r - tb).mean() * TRADING_DAYS / vol) if vol else None,
        "max_drawdown": dd, "beta_vs_spy": beta, "jensen_alpha_ann": jensen,
        "active_return_ann": point, "active_ci_low": lo, "active_ci_high": hi,
        "tracking_error_ann": te, "information_ratio": point / te if te else None,
        "mda_test_period": minimum_detectable_alpha(te, test_years, alpha=float(inf["alpha"])),
        "test_years": round(test_years, 2),
        "avg_positions": float(d["n_positions"].mean()), "max_positions": int(d["n_positions"].max()),
        "days_in_cash_only": int((d["n_positions"] == 0).sum()),
        "turnover_per_year": float(d["turnover"].sum() / d["nav"].mean() / years),
        "costs_per_year": float(d["cost_paid"].sum() / d["nav"].mean() / years),
        "n_positions_opened": int(len(pos)),
        "exit_reasons": pos["exit_reason"].value_counts().to_dict(),
        "median_position_return": float(pos["gross_return"].median()),
        "skipped_signals": int(len(res.skipped_signals)),
    }


def run_period(cfg: Config, period: str, scenario: str = "base", cost: str = "base",
               hold: int | None = None, data_dir: Path = DATA_DIR, reports_dir: Path = REPORTS_DIR,
               group: str = "insider") -> dict:
    inp = load_inputs(cfg, period, data_dir, group)
    ecfg = EngineConfig.from_prereg(cfg, cost_scenario=cost, hold_trading_days=hold)
    res = run(inp["signals"], inp["prices"], inp["calendar"], ecfg, cash_returns=inp["tbill"])
    t0, t1 = _period_bounds(cfg, "test")
    test_years = (t1 - t0).days / 365.25
    m = metrics(res, inp["spy"], inp["tbill"], cfg, test_years)
    m.update({"group": group, "start": str(inp["start"]), "period": period, "scenario": scenario,
              "engine": asdict(ecfg), "prereg_sha256": cfg.sha256,
              "n_buy_signals": int((inp["signals"]["side"] == "buy").sum()),
              "n_delisted_last_price": inp["n_delisted_last_price"]})

    out = reports_dir / f"{period}_results" / f"{group}_{scenario}"
    out.mkdir(parents=True, exist_ok=True)
    res.daily.assign(spy_nav=(1 + inp["spy"].reindex(pd.DatetimeIndex(res.daily["date"])).fillna(0)).cumprod()
                     .to_numpy()).to_parquet(out / "daily.parquet", index=False)
    pos = res.positions.assign(source_signal_ids=res.positions["source_signal_ids"].map(",".join))
    pos.to_parquet(out / "positions.parquet", index=False)
    (out / "metrics.json").write_text(json.dumps(m, indent=2, default=str))
    return {"metrics": m, "result": res, "inputs": inp}
