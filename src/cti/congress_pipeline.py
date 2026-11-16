"""Congress (House) glue: load staged PTR transactions, resolve, fetch missing prices, write tables + report."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from cti.config import DATA_DIR, REPORTS_DIR, Config
from cti.ingest import prices as px_mod
from cti.ingest import reference as ref
from cti.pipeline import _end_date, price_source
from cti.resolve.congress import form4_ticker_history
from cti.resolve.congress import resolve as resolve_congress

OUT_OF_SCOPE = {"not_purchase_or_sale", "not_stock_asset_type", "no_ticker"}


def _con(data_dir: Path, read_only: bool = False):
    return duckdb.connect(str(data_dir / "warehouse.duckdb"), read_only=read_only)


def load_inputs(cfg: Config, data_dir: Path = DATA_DIR) -> dict:
    stg = data_dir / "staging"
    tx = pd.read_parquet(stg / "congress" / "house_transactions.parquet")
    tx["txn_id"] = "house:" + tx["doc_id"] + ":" + tx.groupby("doc_id").cumcount().astype(str)
    prices = pd.read_parquet(stg / "prices" / f"{cfg['data']['price_source']}.parquet", columns=["ticker", "date"])
    prices["date"] = pd.to_datetime(prices["date"])
    con = _con(data_dir, read_only=True)
    try:
        filings = con.execute("SELECT issuer_cik, issuer_ticker, issuer_name, filed_date FROM core_filings").df()
        secs = con.execute("SELECT cik, ticker FROM securities").df()
        cal = con.execute("SELECT * FROM calendar").df()
    finally:
        con.close()
    return {"tx": tx, "hist": form4_ticker_history(filings), "sec_map": ref.load_sec_tickers(data_dir),
            "secs": secs, "prices": prices, "calendar": cal}


def _resolve(cfg: Config, inp: dict) -> pd.DataFrame:
    return resolve_congress(inp["tx"], inp["hist"], inp["sec_map"], inp["secs"], inp["prices"], inp["calendar"],
                            max_gap_days=int(cfg["resolution"]["congress_max_ticker_gap_days"]),
                            min_history_days=int(cfg["resolution"]["min_price_history_days"]))


def ingest_prices(cfg: Config, data_dir: Path = DATA_DIR, log=print) -> int:
    """Fetch prices for mapped Congress tickers the price store doesn't have yet."""
    r = _resolve(cfg, load_inputs(cfg, data_dir))
    want = set(r.loc[r["unmatched_reason"].eq("ticker_not_in_price_source"), "price_ticker"].dropna())
    nf = data_dir / "staging" / "prices" / f"{cfg['data']['price_source']}_not_found.txt"
    tried = set(nf.read_text().split()) if nf.exists() else set()
    want = sorted(want - tried)
    src = price_source(cfg)
    for i in range(0, len(want), 400):
        px_mod.fetch_and_stage(want[i:i + 400], str(cfg["data"]["price_history_start"]), _end_date(), src, data_dir)
        log(f"congress prices: {min(i + 400, len(want))}/{len(want)}")
    return len(want)


def run_resolution(cfg: Config, data_dir: Path = DATA_DIR, reports_dir: Path = REPORTS_DIR) -> dict:
    r = _resolve(cfg, load_inputs(cfg, data_dir))
    keep = ["txn_id", "doc_id", "filer_id", "last", "first", "state_dst", "owner", "asset", "ticker",
            "norm_ticker", "asset_type", "txn_type", "partial", "trade_date", "public_date", "entry_date",
            "amount_low", "amount_high", "cik", "issuer_name", "security_id", "match_method", "name_match",
            "match_confidence", "matched", "unmatched_reason"]
    res = r[keep].rename(columns={"cik": "issuer_cik"})

    src = cfg["data"]["price_source"]
    con = _con(data_dir)
    try:
        # Price rows for Congress securities the insider side never priced.
        have = set(con.execute("SELECT DISTINCT security_id FROM prices_daily").df()["security_id"])
        new = res[res["matched"] & ~res["security_id"].isin(have)][["security_id", "ticker"]].drop_duplicates()
        if len(new):
            px = pd.read_parquet(data_dir / "staging" / "prices" / f"{src}.parquet")
            add = px.merge(new, on="ticker")[["security_id", "ticker", "date", "open", "close", "adj_open",
                                               "adj_close", "close_nominal", "volume", "split", "dividend"]]
            add["delist_return"] = float("nan")
            con.register("_add", add)
            con.execute("INSERT INTO prices_daily SELECT * FROM _add")
            con.unregister("_add")
        con.register("_res", res)
        con.execute("CREATE OR REPLACE TABLE congress_resolution AS SELECT * FROM _res")
        con.unregister("_res")
        ex = ref.load_sec_tickers(data_dir).drop_duplicates("cik")[["cik", "exchange"]]
        con.register("_ex", ex)
        con.execute("CREATE OR REPLACE TABLE sec_exchange AS SELECT * FROM _ex")
        con.unregister("_ex")
    finally:
        con.close()
    docs = pd.read_parquet(data_dir / "staging" / "congress" / "house_documents.parquet")
    return write_quality(res, docs, cfg, reports_dir)


def _table(s: pd.Series, total: int, label: str) -> str:
    return "\n".join([f"| {label} | count | share |", "|---|---:|---:|"]
                     + [f"| {a} | {b:,} | {b / max(total, 1):.1%} |" for a, b in s.items()])


def write_quality(res: pd.DataFrame, docs: pd.DataFrame, cfg: Config, reports_dir: Path) -> dict:
    inscope = res[~res["unmatched_reason"].isin(OUT_OF_SCOPE)]
    n, matched = len(inscope), int(inscope["matched"].sum())
    reasons = res.loc[~res["matched"], "unmatched_reason"].value_counts()
    conf = res.loc[res["matched"], "match_confidence"].value_counts()
    methods = res.loc[res["matched"], "match_method"].value_counts()

    docs = docs.assign(year=pd.to_datetime(docs["filing_date"]).dt.year)
    by_year = docs.groupby("year").agg(ptrs=("doc_id", "size"),
                                       parsed=("status", lambda s: int((s == "parsed").sum())),
                                       paper=("status", lambda s: int((s == "paper_scan_not_parsed").sum())))
    iy = inscope.assign(year=pd.to_datetime(inscope["public_date"]).dt.year).groupby("year")["matched"]
    by_year = by_year.join(iy.agg(["size", "mean"]), how="left")
    yrows = []
    for y, row in by_year.iterrows():
        size = 0 if pd.isna(row["size"]) else int(row["size"])
        rate = "" if pd.isna(row["mean"]) else f"{row['mean']:.1%}"
        yrows.append(f"| {y} | {int(row['ptrs']):,} | {int(row['parsed']):,} | {int(row['paper']):,} "
                     f"| {size:,} | {rate} |")

    k = min(int(cfg["resolution"]["audit_sample_size"]), matched)
    audit = res[res["matched"]].sample(n=k, random_state=int(cfg["resolution"]["audit_seed"]))
    audit_dir = reports_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    audit[["txn_id", "doc_id", "last", "first", "asset", "norm_ticker", "ticker", "issuer_name", "match_method",
           "match_confidence", "trade_date"]].assign(audit_correct="", audit_note="") \
        .to_csv(audit_dir / "congress_match_audit_sample.csv", index=False)

    nl = "\n"
    md = f"""# Congress data quality (generated): House PTRs

Source: House Clerk periodic transaction reports (2015 onward). Senate not yet included.

## Documents
{_table(docs['status'].value_counts(), len(docs), "PTR status")}

Paper scans have no text layer; parsing them needs OCR (not done), so they are a coverage gap.

## Transactions
- Parsed transactions: **{len(res):,}**
- In scope (purchase or sale of a stock with a ticker): **{n:,}**
- Matched to a priced security: **{matched:,} ({matched / max(n, 1):.1%} of in scope)**

{_table(reasons, len(res), "Unmatched / out-of-scope reason")}

{_table(conf, matched, "Match confidence (matched)")}

{_table(methods, matched, "Match method (matched)")}

## By filing year
| year | PTRs | parsed (electronic) | paper scans | in-scope txns | matched |
|---|---:|---:|---:|---:|---:|
{nl.join(yrows)}

## Hand audit
`reports/audit/congress_match_audit_sample.csv`: {k} random matched transactions. Fill `audit_correct`.
"""
    (reports_dir / "data_quality_congress.md").write_text(md, encoding="utf-8")
    return {"parsed": len(res), "in_scope": n, "matched": matched, "reasons": reasons.to_dict()}
