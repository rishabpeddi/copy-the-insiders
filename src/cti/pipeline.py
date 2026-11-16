"""Phase 2 glue: reference + price ingestion, security resolution, warehouse tables, data-quality report.

Keeps I/O here so the logic modules (resolve, reference, prices) stay pure and testable.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import duckdb
import pandas as pd

from cti.config import DATA_DIR, REPORTS_DIR, Config
from cti.ingest import prices as px_mod
from cti.ingest import reference as ref
from cti.resolve.securities import normalize_ticker, resolve


def price_source(cfg: Config) -> px_mod.PriceSource:
    name = cfg["data"]["price_source"]
    if name == "yfinance":
        return px_mod.YFinanceSource()
    raise ValueError(f"Unknown price_source {name!r}. Add an adapter in cti/ingest/prices.py.")


def _warehouse(data_dir: Path, read_only: bool = False):
    return duckdb.connect(str(data_dir / "warehouse.duckdb"), read_only=read_only)


def load_candidates(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    con = _warehouse(data_dir, read_only=True)
    try:
        return con.execute("SELECT * FROM signals_insider_candidates").df()
    finally:
        con.close()


def _end_date() -> str:
    return (dt.date.today() + dt.timedelta(days=1)).isoformat()


def ingest_reference(cfg: Config, data_dir: Path = DATA_DIR) -> dict:
    ref.fetch_tbill(int(str(cfg["data"]["price_history_start"])[:4]), data_dir)
    ref.fetch_sec_tickers(data_dir)
    start = str(cfg["data"]["price_history_start"])
    staged = px_mod.fetch_and_stage(ref.REFERENCE_TICKERS, start, _end_date(), price_source(cfg), data_dir)
    got = sorted(set(staged["ticker"]) & set(ref.REFERENCE_TICKERS))
    return {"reference_tickers": got, "missing": sorted(set(ref.REFERENCE_TICKERS) - set(got))}


def tickers_to_fetch(candidates: pd.DataFrame, sec_map: pd.DataFrame) -> list[str]:
    filing = {t for t in candidates["issuer_ticker"].map(normalize_ticker) if t}
    ciks = set(candidates["issuer_cik"])
    # Only the SEC tickers choose_tickers can use: the CIK's primary ticker, plus any that also
    # appear in filings. Skips warrants/preferreds (DAVEW, NEE-PU) that would never be chosen.
    m = sec_map[sec_map["cik"].isin(ciks)].assign(t=lambda d: d["ticker"].str.replace(".", "-"))
    primary = set(m.groupby("cik")["t"].first())
    return sorted(filing | primary | (set(m["t"]) & filing))


def ingest_prices(cfg: Config, data_dir: Path = DATA_DIR, only_missing: bool = True,
                  chunk: int = 400, log=print) -> dict:
    cands = load_candidates(data_dir)
    want = tickers_to_fetch(cands, ref.load_sec_tickers(data_dir))
    staged_path = data_dir / "staging" / "prices" / f"{cfg['data']['price_source']}.parquet"
    nf_path = staged_path.with_name(f"{cfg['data']['price_source']}_not_found.txt")
    if only_missing and staged_path.exists():
        have = set(pd.read_parquet(staged_path, columns=["ticker"])["ticker"])
        tried = set(nf_path.read_text().split()) if nf_path.exists() else set()
        want = [t for t in want if t not in have and t not in tried]
    # Each chunk is saved as its own raw pull, so an interrupted run resumes where it stopped.
    src = price_source(cfg)
    for i in range(0, len(want), chunk):
        part = want[i:i + chunk]
        staged = px_mod.fetch_and_stage(part, str(cfg["data"]["price_history_start"]), _end_date(), src, data_dir)
        log(f"prices: {min(i + chunk, len(want)):,}/{len(want):,} requested; "
            f"{staged['ticker'].nunique():,} tickers staged")
    return {"requested": len(want)}


def run_resolution(cfg: Config, data_dir: Path = DATA_DIR, reports_dir: Path = REPORTS_DIR) -> dict:
    res_cfg = cfg["resolution"]
    src = cfg["data"]["price_source"]
    prices = pd.read_parquet(data_dir / "staging" / "prices" / f"{src}.parquet")
    prices["date"] = pd.to_datetime(prices["date"])
    spy = prices.loc[prices["ticker"] == ref.SPY, "date"]
    if spy.empty:
        raise RuntimeError("No SPY prices; run `cti ingest reference` first.")
    calendar = ref.build_calendar(spy)
    sec_map = ref.load_sec_tickers(data_dir)
    cands = load_candidates(data_dir)

    secs, resolution = resolve(cands, sec_map, prices, calendar,
                               tight_pct=float(res_cfg["price_check_tight_pct"]),
                               max_ratio=float(res_cfg["price_check_max_ratio"]),
                               min_history_days=int(res_cfg["min_price_history_days"]))
    refret = ref.reference_returns(prices, calendar, ref.load_tbill(data_dir))

    matched_tickers = secs.dropna(subset=["ticker"])[["security_id", "ticker"]]
    prices_daily = prices.merge(matched_tickers, on="ticker")[
        ["security_id", "ticker", "date", "open", "close", "adj_open", "adj_close", "close_nominal",
         "volume", "split", "dividend"]]
    prices_daily["delist_return"] = float("nan")  # yfinance has none; CRSP/vendor adapter fills this

    con = _warehouse(data_dir)
    try:
        for name, df in {"calendar": calendar, "securities": secs.drop(columns="candidate_tickers")
                         .assign(candidate_tickers=secs["candidate_tickers"].map(",".join)),
                         "signal_resolution": resolution, "reference_returns": refret,
                         "prices_daily": prices_daily}.items():
            con.register("_df", df)
            con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _df")
            con.unregister("_df")
    finally:
        con.close()

    summary = write_quality_report(cands, secs, resolution, prices, calendar, cfg, reports_dir)
    return summary


def write_quality_report(cands, secs, res, prices, calendar, cfg: Config, reports_dir: Path) -> dict:
    reports_dir.mkdir(parents=True, exist_ok=True)
    n = len(res)
    matched = int(res["matched"].sum())
    reasons = res.loc[~res["matched"], "unmatched_reason"].value_counts()
    conf = res.loc[res["matched"], "match_confidence"].value_counts()
    methods = res.loc[res["matched"], "match_method"].value_counts()
    issuers = secs["security_id"].nunique()
    issuers_matched = int(secs["ticker"].notna().sum())
    shared = secs.dropna(subset=["ticker"]).groupby("ticker")["cik"].nunique()
    shared = shared[shared > 1]
    by_q = res.assign(q=pd.to_datetime(res["public_date"]).dt.to_period("Q").astype(str)) \
        .groupby("q")["matched"].agg(["size", "mean"])
    pub = pd.to_datetime(res["public_date"])
    period_rows = []
    for name, p in cfg["periods"].items():
        m = pub >= pd.Timestamp(p["start"])
        if p.get("end"):
            m &= pub <= pd.Timestamp(p["end"])
        period_rows.append(f"| {name} | {p['start']} to {p.get('end') or 'now'} | {int(m.sum()):,} | "
                           f"{res.loc[m, 'matched'].mean():.1%} |")

    # Hand-audit sample: random matched transactions, with what's needed to check each by eye.
    k = min(int(cfg["resolution"]["audit_sample_size"]), matched)
    sample = res[res["matched"]].sample(n=k, random_state=int(cfg["resolution"]["audit_seed"]))
    audit_dir = reports_dir / "audit"
    audit_dir.mkdir(exist_ok=True)
    from cti.audit import sec_filing_url, write_sample
    audit = sample[["txn_id", "issuer_cik", "issuer_name", "issuer_ticker", "ticker", "match_method",
                    "match_confidence", "trade_date", "reported_price", "close_nominal_at_trade", "price_ratio"]].copy()
    audit.insert(1, "filing_url", [sec_filing_url(t.split(":")[0], c)
                                   for t, c in zip(audit["txn_id"], audit["issuer_cik"], strict=True)])
    write_sample(audit, audit_dir / "match_audit_sample.csv")
    res[~res["matched"]].to_csv(audit_dir / "unmatched.csv", index=False)

    def table(s: pd.Series, total: int, label: str) -> str:
        lines = [f"| {label} | count | share |", "|---|---:|---:|"]
        lines += [f"| {k} | {v:,} | {v / max(total, 1):.1%} |" for k, v in s.items()]
        return "\n".join(lines)

    cal_start, cal_end = calendar["date"].min().date(), calendar["date"].max().date()
    generated = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    md = f"""# Data quality (generated)

Generated {generated} by `cti resolve`. Price source: **{cfg['data']['price_source']}**
(survivors only: see "Survivorship" below). Calendar: {len(calendar):,} trading days, {cal_start} to {cal_end}.

## Insider purchase candidates -> securities
- Candidate transactions (after filing rules): **{n:,}**
- Matched to a priced security: **{matched:,} ({matched / max(n, 1):.1%})**
- Issuers: {issuers:,}; with a priced ticker: {issuers_matched:,} ({issuers_matched / max(issuers, 1):.1%})

| period | dates | candidates | matched |
|---|---|---:|---:|
{chr(10).join(period_rows)}

If the match rate differs a lot between dev and test, the two samples are biased differently
(older periods lose more delisted companies), and dev results won't predict test results.

{table(conf, matched, "Match confidence (matched)")}

{table(methods, matched, "Match method (matched)")}

{table(reasons, n, "Unmatched reason")}

## Match rate by filing quarter
| quarter | candidates | matched |
|---|---:|---:|
""" + "\n".join(f"| {q} | {int(r['size']):,} | {r['mean']:.1%} |" for q, r in by_q.iterrows()) + f"""

## Tickers shared by more than one CIK
{len(shared)} tickers. These may be share classes, parent/subsidiary filers, or ticker reuse; check
them in the audit. {", ".join(shared.index[:30]) or "None."}

## Survivorship
`ticker_not_in_price_source` is mostly companies that were delisted, acquired, or renamed with no
history kept by the free source. Those are exactly the cases survivorship bias hides, so this
number is a lower bound on the bias problem, not noise. Final results need CRSP or a vendor that
covers delistings.

## Hand audit
`reports/audit/match_audit_sample.csv` has {k} random matched transactions (seed
{cfg['resolution']['audit_seed']}). Fill `audit_correct` (y/n) for each one by checking that the
ticker belongs to the issuer on the trade date. Unmatched rows with reasons:
`reports/audit/unmatched.csv`.
"""
    (reports_dir / "data_quality.md").write_text(md, encoding="utf-8")
    return {"candidates": n, "matched": matched, "match_rate": matched / max(n, 1),
            "reasons": reasons.to_dict(), "confidence": conf.to_dict()}
