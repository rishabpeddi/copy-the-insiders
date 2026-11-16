"""Load one period's inputs from the warehouse, run the engine for each pre-registered scenario,
compute metrics, write results.

Scenarios: `primary` is the pre-registered configuration; each sensitivity run changes exactly one
thing from it (prereg.yaml `sensitivity`). Test-period runs go through cti.lock first (see
cli.run_cmd); this module never decides that.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from cti.backtest.benchmarks import sector_clone_nav
from cti.backtest.engine import EngineConfig, EngineResult, run
from cti.config import DATA_DIR, REPORTS_DIR, Config
from cti.ingest import factors as ff
from cti.stats import factor_model
from cti.stats.bootstrap import TRADING_DAYS, block_bootstrap_ci
from cti.stats.power import minimum_detectable_alpha

GROUPS = {"insider": ("signals_insider", "signals_insider_sells", "signal_resolution", "signals_insider_all"),
          "congress": ("signals_congress", "signals_congress_sells", "congress_resolution", "signals_congress_all")}


@dataclass(frozen=True)
class Scenario:
    name: str = "primary"
    cost: str = "base"
    hold: int | None = None
    rebalance: str | None = None
    filing_lag: str = "cutoff"        # or "none"
    tenb51: str = "primary"           # or "footnote_only" (insider)
    min_confidence: str | None = None  # congress: None = prereg value
    weighting: str = "equal"          # or "amount_mid" (congress)
    bound: str | None = None          # survivorship bound: minus_100 | zero | benchmark


def scenarios(cfg: Config, group: str) -> list[Scenario]:
    s = cfg["sensitivity"]
    base = Scenario()
    out = [base]
    out += [replace(base, name=f"costs_{c}", cost=c) for c in s.get("costs", [])]
    out += [replace(base, name=f"hold_{h}", hold=int(h)) for h in s.get("hold_trading_days", [])]
    out += [replace(base, name=f"rebalance_{r}", rebalance=r) for r in s.get("rebalance", [])]
    out += [replace(base, name=f"filing_lag_{v}", filing_lag=v) for v in s.get("filing_lag", [])]
    if group == "insider":
        out += [replace(base, name=f"10b5_1_{v}", tenb51=v) for v in s.get("insider_10b5_1", [])]
    if group == "congress":
        out += [replace(base, name=f"confidence_{v}", min_confidence=v) for v in s.get("congress_match_confidence", [])]
        out += [replace(base, name=f"weighting_{v}", weighting=v) for v in s.get("congress_weighting", [])]
    out += [replace(base, name=f"bound_{b}", bound=b) for b in s.get("survivorship_bounds", [])]
    return out


def _period_bounds(cfg: Config, period: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    start, end = cfg.period(period)
    return pd.Timestamp(start), pd.Timestamp(end) if end else pd.Timestamp.today().normalize()


def load_inputs(cfg: Config, period: str, data_dir: Path = DATA_DIR, group: str = "insider") -> dict:
    """Everything any scenario needs; scenario filters are applied in `prepare`."""
    buys_t, sells_t, res_t, all_t = GROUPS[group]
    lo, hi = _period_bounds(cfg, period)
    con = duckdb.connect(str(data_dir / "warehouse.duckdb"), read_only=True)
    try:
        q = lambda sql: con.execute(sql, [lo, hi]).df()  # noqa: E731
        buys = q(f"SELECT * FROM {buys_t} WHERE entry_date BETWEEN ? AND ?")
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
        ref = q("SELECT date, series, total_return FROM reference_returns WHERE date BETWEEN ? AND ?")
        # Universe pass rate by year among matched purchases, and the unmatched purchases that the
        # survivorship bounds stand in for.
        reasons = ", ".join(f"'{r}'" for r in cfg["survivorship_bounds"]["reasons"])
        pass_rate = q(f"SELECT year(entry_date) AS y, avg((universe_reason IS NULL)::INT) AS rate FROM {all_t} "
                      "WHERE entry_date BETWEEN ? AND ? GROUP BY 1")
        if group == "insider":
            unmatched = q("SELECT r.txn_id AS signal_id, r.issuer_cik AS issuer_key, c.filer_id, "
                          "r.public_date, r.entry_date, "
                          "c.filing_lag_days, c.is_10b5_1, c.footnote_mentions_10b5_1 "
                          "FROM signal_resolution r JOIN signals_insider_candidates c USING (txn_id) "
                          f"WHERE r.entry_date BETWEEN ? AND ? AND r.unmatched_reason IN ({reasons})")
        else:
            unmatched = q("SELECT txn_id AS signal_id, coalesce(issuer_cik, norm_ticker, asset) AS issuer_key, "
                          "filer_id, public_date, entry_date, "
                          "date_diff('day', trade_date, public_date) AS filing_lag_days "
                          f"FROM congress_resolution WHERE entry_date BETWEEN ? AND ? AND txn_type = 'P' "
                          f"AND unmatched_reason IN ({reasons})")
    finally:
        con.close()
    ref = ref.pivot(index="date", columns="series", values="total_return").reindex(pd.DatetimeIndex(cal))

    # Delisting rule for the free source: yfinance gives no reason, so a history that ends inside
    # the period is treated as `delisting.other: last_price` (exit at the last close, return 0).
    last = prices.groupby("security_id")["date"].transform("max")
    ends_inside = (prices["date"] == last) & (last < pd.Timestamp(cal.iloc[-1]))
    prices.loc[ends_inside, "delist_return"] = 0.0
    try:
        factors = ff.load(data_dir)
    except FileNotFoundError:
        factors = None
    sic_path = data_dir / "staging" / "sec_sic.parquet"
    sector = (pd.read_parquet(sic_path).set_index("cik")["sector_etf"] if sic_path.exists() else None)
    etfs = ref.drop(columns=["TBILL"], errors="ignore")
    for c in etfs.columns:  # ETFs before inception (XLRE 2015, XLC 2018) fall back to SPY
        etfs[c] = etfs[c].fillna(etfs["SPY"])
    return {"group": group, "calendar": list(cal), "buys": buys, "sells": sells, "prices": prices,
            "etf_returns": etfs.fillna(0.0), "sector": sector,
            "spy": ref["SPY"].fillna(0.0), "tbill": ref["TBILL"].fillna(0.0), "factors": factors,
            "pass_rate": dict(zip(pass_rate["y"], pass_rate["rate"], strict=True)), "unmatched": unmatched,
            "n_delisted_last_price": int(ends_inside.sum()), "start": pd.Timestamp(cal.iloc[0]).date()}


def _filters(df: pd.DataFrame, cfg: Config, group: str, sc: Scenario) -> tuple[pd.DataFrame, dict]:
    g = cfg["groups"][group]
    n0, drops = len(df), {}
    if sc.filing_lag == "cutoff" and "filing_lag_days" in df:
        keep = df["filing_lag_days"].isna() | (df["filing_lag_days"] <= int(g["max_filing_lag_days"]))
        drops["filing_lag"] = int((~keep).sum())
        df = df[keep]
    if group == "insider" and g.get("exclude_10b5_1") and "is_10b5_1" in df:
        col = "footnote_mentions_10b5_1" if sc.tenb51 == "footnote_only" else "is_10b5_1"
        keep = ~df[col].fillna(False).astype(bool)
        drops["10b5_1"] = int((~keep).sum())
        df = df[keep]
    if group == "congress" and "match_confidence" in df:
        minc = sc.min_confidence or g.get("min_match_confidence", "low")
        allowed = {"low": {"low", "medium", "high"}, "medium": {"medium", "high"}, "high": {"high"}}[minc]
        keep = df["match_confidence"].isin(allowed)
        drops["low_confidence"] = int((~keep).sum())
        df = df[keep]
    drops["kept"], drops["before"] = len(df), n0
    return df, drops


def _synthetic(inp: dict, cfg: Config, sc: Scenario, hold: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Synthetic signals + price paths for unmatched purchases (survivorship bound).

    Unmatched purchases are grouped into issuer episodes that mirror the engine's one-position-per-
    ticker rule: an episode starts at a purchase and absorbs later purchases of the same issuer within
    `hold` trading days. Each episode is kept with probability = that year's universe pass rate among
    matched purchases (seeded), and becomes one synthetic security priced at 0% / SPY / -100%.
    """
    um, _ = _filters(inp["unmatched"].copy(), cfg, inp["group"], replace(sc, bound=None))
    cal = pd.DatetimeIndex(inp["calendar"])
    um = um.assign(i=cal.searchsorted(pd.to_datetime(um["entry_date"])))
    um = um[(um["i"] < len(cal))]
    um = um[cal[um["i"].clip(upper=len(cal) - 1)] == pd.to_datetime(um["entry_date"])]
    um = um.sort_values(["issuer_key", "i"])
    ep, last_key, start = [], None, -10**9
    n_ep = 0
    for key, i in zip(um["issuer_key"], um["i"], strict=True):
        if key != last_key or i >= start + hold:
            n_ep += 1
            start, last_key = i, key
        ep.append((n_ep, start))
    um["episode"] = [e for e, _ in ep]
    um["ep_start"] = [st for _, st in ep]

    rng = np.random.default_rng(int(cfg["survivorship_bounds"]["seed"]))
    episodes = um.drop_duplicates("episode")[["episode", "ep_start"]]
    rate = pd.Series(cal[episodes["ep_start"]].year).map(inp["pass_rate"]).fillna(0.0).to_numpy()
    keep_ep = set(episodes["episode"][rng.random(len(episodes)) < rate])
    um = um[um["episode"].isin(keep_ep)]

    spy_idx = (1 + inp["spy"]).cumprod()
    rows = []
    for e, st in um.drop_duplicates("episode")[["episode", "ep_start"]].itertuples(index=False):
        span = cal[st:min(st + hold + 1, len(cal))]
        px = spy_idx.reindex(span).to_numpy() if sc.bound == "benchmark" else np.ones(len(span))
        dr = np.full(len(span), np.nan)
        if sc.bound == "minus_100":
            dr[min(hold - 1, len(span) - 1)] = -1.0   # worthless by the close before the scheduled exit
        else:
            dr[-1] = 0.0                              # exit at the last price, never the -100% default
        rows.append(pd.DataFrame({"security_id": f"synthetic:{e}", "date": span, "open": px, "close": px,
                                  "delist_return": dr}))
    sec = "synthetic:" + um["episode"].astype(str)
    sig = pd.DataFrame({"signal_id": "synthetic:" + um["signal_id"].astype(str), "side": "buy", "security_id": sec,
                        "filer_id": um["filer_id"], "public_date": um["public_date"], "entry_date": um["entry_date"],
                        "weight": 1.0})
    px = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["security_id", "date"])
    return sig, px


def prepare(inp: dict, cfg: Config, sc: Scenario) -> dict:
    group = inp["group"]
    buys, drops = _filters(inp["buys"].copy(), cfg, group, sc)
    buys["weight"] = buys["amount_mid"].fillna(1.0) if sc.weighting == "amount_mid" else 1.0
    cols = ["signal_id", "side", "security_id", "filer_id", "public_date", "entry_date", "weight"]
    signals = pd.concat([buys[cols], inp["sells"].assign(weight=1.0)[cols]], ignore_index=True)
    prices = inp["prices"]
    hold = int(sc.hold or cfg.portfolio["hold_trading_days"])
    n_syn = 0
    if sc.bound:
        syn_sig, syn_px = _synthetic(inp, cfg, sc, hold)
        n_syn = int(syn_sig["security_id"].nunique()) if len(syn_sig) else 0
        signals = pd.concat([signals, syn_sig], ignore_index=True)
        prices = pd.concat([prices, syn_px], ignore_index=True)
    drops["synthetic_unmatched"] = n_syn
    return {"signals": signals, "prices": prices, "drops": drops, "hold": hold}


def metrics(res: EngineResult, inp: dict, cfg: Config, test_years: float) -> dict:
    d = res.daily.set_index(pd.DatetimeIndex(res.daily["date"]))
    r = d["nav"].pct_change().fillna(d["nav"].iloc[0] / cfg.portfolio.get("starting_nav", 1.0) - 1)
    spy = inp["spy"].reindex(r.index).fillna(0.0)
    tb = inp["tbill"].reindex(r.index).fillna(0.0)
    active = (r - spy).to_numpy()
    years = len(r) / TRADING_DAYS
    nav_end = float(d["nav"].iloc[-1])
    vol = float(r.std() * np.sqrt(TRADING_DAYS))
    te = float(np.std(active, ddof=1) * np.sqrt(TRADING_DAYS))
    beta = float(np.cov(r, spy)[0, 1] / np.var(spy, ddof=1))
    jensen = float(((r - tb) - beta * (spy - tb)).mean() * TRADING_DAYS)
    inf = cfg["inference"]
    kw = {"block_months": int(inf["block_months"]), "reps": int(inf["reps"]), "alpha": float(inf["alpha"]),
          "seed": int(inf["seed"])}
    point, lo, hi = block_bootstrap_ci(active, **kw)
    pos = res.positions
    m = {
        "years": round(years, 2),
        "cagr": nav_end ** (1 / years) - 1, "spy_cagr": float((1 + spy).prod()) ** (1 / years) - 1,
        "ann_vol": vol, "sharpe": float((r - tb).mean() * TRADING_DAYS / vol) if vol else None,
        "max_drawdown": float((d["nav"] / d["nav"].cummax() - 1).min()), "beta_vs_spy": beta,
        "jensen_alpha_ann": jensen, "active_return_ann": point, "active_ci_low": lo, "active_ci_high": hi,
        "tracking_error_ann": te, "mda_spy_test_period": minimum_detectable_alpha(te, test_years, alpha=kw["alpha"]),
        "test_years": round(test_years, 2),
        "avg_positions": float(d["n_positions"].mean()), "max_positions": int(d["n_positions"].max()),
        "avg_cash_weight": float((d["cash"] / d["nav"]).mean()),
        "turnover_per_year": float(d["turnover"].sum() / d["nav"].mean() / years),
        "costs_per_year": float(d["cost_paid"].sum() / d["nav"].mean() / years),
        "n_positions_opened": int(len(pos)), "exit_reasons": pos["exit_reason"].value_counts().to_dict(),
        "median_position_return": float(pos["gross_return"].median()) if len(pos) else None,
        "skipped_signals": int(len(res.skipped_signals)),
    }
    if inp["sector"] is not None and len(res.holdings):
        clone = sector_clone(res, d["nav"], inp)
        cr = clone.pct_change().fillna(clone.iloc[0] - 1)
        cp, clo, chi = block_bootstrap_ci((r - cr.reindex(r.index).fillna(0.0)).to_numpy(), **kw)
        m.update({"clone_cagr": float(clone.iloc[-1]) ** (1 / years) - 1, "active_vs_clone_ann": cp,
                  "clone_ci_low": clo, "clone_ci_high": chi})
    if inp["factors"] is not None:
        f = factor_model.fit(r, inp["factors"], **kw)
        m.update({"ff_alpha_ann": f.alpha_ann, "ff_ci_low": f.ci_low, "ff_ci_high": f.ci_high,
                  "ff_resid_vol_ann": f.resid_vol_ann, "ff_r2": f.r2, "ff_betas": f.betas, "ff_days": f.n_days,
                  "mda_ff_test_period": factor_model.mda(f, test_years, alpha=kw["alpha"])})
    return m


def sector_clone(res: EngineResult, nav: pd.Series, inp: dict) -> pd.Series:
    """Monthly sector-ETF clone of the strategy's month-end sector weights (secondary benchmark)."""
    h = res.holdings.copy()
    h["etf"] = h["security_id"].str.removeprefix("cik:").map(inp["sector"])
    h["etf"] = h["etf"].where(h["etf"].isin(inp["etf_returns"].columns), "SPY")  # unknown / synthetic -> SPY
    h["date"] = pd.DatetimeIndex(h["date"])
    w = h.pivot_table(index="date", columns="etf", values="value", aggfunc="sum").fillna(0.0)
    w = w.div(nav.reindex(w.index), axis=0)
    rets = inp["etf_returns"].reindex(columns=w.columns).fillna(0.0)
    return sector_clone_nav(w, rets, inp["tbill"])


def run_scenario(cfg: Config, inp: dict, sc: Scenario, period: str, reports_dir: Path = REPORTS_DIR) -> dict:
    prep = prepare(inp, cfg, sc)
    ecfg = EngineConfig.from_prereg(cfg, cost_scenario=sc.cost, hold_trading_days=prep["hold"],
                                    rebalance=sc.rebalance, weighting="signal" if sc.weighting != "equal" else "equal")
    res = run(prep["signals"], prep["prices"], inp["calendar"], ecfg, cash_returns=inp["tbill"])
    t0, t1 = _period_bounds(cfg, "test")
    m = metrics(res, inp, cfg, (t1 - t0).days / 365.25)
    if inp["group"] == "insider" and sc.name == "primary" and "is_10b5_1" in inp["buys"]:
        b = inp["buys"]
        prim, foot = b["is_10b5_1"].fillna(False).astype(bool), b["footnote_mentions_10b5_1"].fillna(False).astype(bool)
        m["tenb51_counts"] = {"flagged_by_primary_rule": int(prim.sum()), "flagged_by_footnote_text": int(foot.sum()),
                              "primary_only (checkbox, no footnote)": int((prim & ~foot).sum()),
                              "footnote_only (footnote, checkbox says no)": int((foot & ~prim).sum()),
                              "purchases_in_period": int(len(b))}
    m.update({"group": inp["group"], "scenario": sc.name, "scenario_spec": asdict(sc), "period": period,
              "start": str(inp["start"]), "engine": asdict(ecfg), "prereg_sha256": cfg.sha256,
              "signal_filters": prep["drops"], "n_delisted_last_price": inp["n_delisted_last_price"]})
    out = reports_dir / f"{period}_results" / f"{inp['group']}_{sc.name}"
    out.mkdir(parents=True, exist_ok=True)
    spy_nav = (1 + inp["spy"].reindex(pd.DatetimeIndex(res.daily["date"])).fillna(0)).cumprod().to_numpy()
    res.daily.assign(spy_nav=spy_nav).to_parquet(out / "daily.parquet", index=False)
    res.positions.assign(source_signal_ids=res.positions["source_signal_ids"].map(",".join)) \
        .to_parquet(out / "positions.parquet", index=False)
    (out / "metrics.json").write_text(json.dumps(m, indent=2, default=str))
    return m


def run_period(cfg: Config, period: str, group: str = "insider", only: list[str] | None = None,
               data_dir: Path = DATA_DIR, reports_dir: Path = REPORTS_DIR, log=print) -> list[dict]:
    inp = load_inputs(cfg, period, data_dir, group)
    out = []
    for sc in scenarios(cfg, group):
        if only and sc.name not in only:
            continue
        m = run_scenario(cfg, inp, sc, period, reports_dir)
        log(f"{group:8} {sc.name:26} CAGR {m['cagr']:7.2%}  SPY {m['spy_cagr']:7.2%}  "
            f"FF alpha {m.get('ff_alpha_ann', float('nan')):+.2%} "
            f"[{m.get('ff_ci_low', float('nan')):+.2%}, {m.get('ff_ci_high', float('nan')):+.2%}]")
        out.append(m)
    return out
