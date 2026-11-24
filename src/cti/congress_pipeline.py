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


CHAMBERS = ("house", "senate")


def _staged(data_dir: Path, kind: str) -> pd.DataFrame:
    """House and Senate staging tables stacked, with a `chamber` column. Senate is optional."""
    parts = []
    for ch in CHAMBERS:
        p = data_dir / "staging" / "congress" / f"{ch}_{kind}.parquet"
        if p.exists():
            parts.append(pd.read_parquet(p).assign(chamber=ch))
    return pd.concat(parts, ignore_index=True)


def load_transactions(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    tx = _staged(data_dir, "transactions")
    tx["txn_id"] = tx["chamber"] + ":" + tx["doc_id"] + ":" + tx.groupby(["chamber", "doc_id"]).cumcount().astype(str)
    return tx


def load_inputs(cfg: Config, data_dir: Path = DATA_DIR) -> dict:
    stg = data_dir / "staging"
    tx = load_transactions(data_dir)
    tx = tx[tx["chamber"].isin(cfg["groups"]["congress"].get("chambers", ["house"]))]
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
    keep = ["txn_id", "chamber", "doc_id", "filer_id", "last", "first", "state_dst", "owner", "asset", "ticker",
            "norm_ticker", "asset_type", "txn_type", "partial", "trade_date", "public_date", "entry_date",
            "amount_low", "amount_high", "cik", "issuer_name", "security_id", "match_method", "name_match",
            "match_confidence", "matched", "unmatched_reason"]
    res = r[keep].rename(columns={"cik": "issuer_cik"})

    src = cfg["data"]["price_source"]
    con = _con(data_dir)
    try:
        # Price rows for Congress securities the insider side never priced. Drop earlier Congress-only
        # additions first so a re-run never stacks a second ticker's series under the same security.
        con.execute("DELETE FROM prices_daily WHERE security_id NOT IN "
                    "(SELECT security_id FROM securities WHERE ticker IS NOT NULL)")
        have = set(con.execute("SELECT DISTINCT security_id FROM prices_daily").df()["security_id"])
        new = res[res["matched"] & ~res["security_id"].isin(have)][["security_id", "ticker"]].drop_duplicates()
        assert not new["security_id"].duplicated().any(), "one price ticker per security"
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
    return write_quality(res, _staged(data_dir, "documents"), cfg, reports_dir)


def _table(s: pd.Series, total: int, label: str) -> str:
    return "\n".join([f"| {label} | count | share |", "|---|---:|---:|"]
                     + [f"| {a} | {b:,} | {b / max(total, 1):.1%} |" for a, b in s.items()])


def _chamber_table(res: pd.DataFrame, docs: pd.DataFrame) -> str:
    inscope = res[~res["unmatched_reason"].isin(OUT_OF_SCOPE)]
    rows = ["| chamber | PTRs | paper scans | in-scope txns | matched | matched purchases |",
            "|---|---:|---:|---:|---:|---:|"]
    for ch in sorted(docs["chamber"].unique()):
        d, i = docs[docs["chamber"] == ch], inscope[inscope["chamber"] == ch]
        m = i[i["matched"]]
        rows.append(f"| {ch} | {len(d):,} | {int((d['status'] == 'paper_scan_not_parsed').sum()):,} | {len(i):,} "
                    f"| {len(m):,} ({len(m) / max(len(i), 1):.1%}) | {int((m['txn_type'] == 'P').sum()):,} |")
    return "\n".join(rows)


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

    # Who files on paper? If paper filers differ systematically, the parsed sample isn't the population.
    who = docs["state_dst"].where(docs["chamber"] == "house", "Senate").fillna("")
    member = docs["last"].str.upper() + ", " + docs["first"].str.upper() + " (" + who + ")"
    mem = docs.assign(member=member, paper=docs["status"].eq("paper_scan_not_parsed"))
    per = mem.groupby("member")["paper"].agg(["size", "mean"])
    kinds = {"electronic only": int((per["mean"] == 0).sum()), "paper only": int((per["mean"] == 1).sum()),
             "mixed": int(((per["mean"] > 0) & (per["mean"] < 1)).sum())}
    top_paper = per[per["mean"] > 0].sort_values(["mean", "size"], ascending=False).head(15)
    paper_rows = "\n".join(f"| {m} | {int(r['size'])} | {r['mean']:.0%} |" for m, r in top_paper.iterrows())
    paper_share_ptrs = float(mem["paper"].mean())
    top10_share = float(per.sort_values("size", ascending=False).head(10)["size"].sum() / max(len(mem), 1))

    k = min(int(cfg["resolution"]["audit_sample_size"]), matched)
    audit = res[res["matched"]].sample(n=k, random_state=int(cfg["resolution"]["audit_seed"]))
    audit_dir = reports_dir / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    from cti.audit import ptr_url, write_sample
    a = audit[["txn_id", "chamber", "doc_id", "last", "first", "asset", "norm_ticker", "ticker", "issuer_name",
               "match_method", "match_confidence", "trade_date", "public_date"]].copy()
    a.insert(1, "ptr_url", [ptr_url(c, d, pd.Timestamp(p).year)
                            for c, d, p in zip(a["chamber"], a["doc_id"], a["public_date"], strict=True)])
    write_sample(a, audit_dir / "congress_match_audit_sample.csv")

    nl = "\n"
    md = f"""# Congress data quality (generated): House and Senate PTRs

Sources: House Clerk periodic transaction reports (2015 onward) and Senate eFD periodic transaction
reports (2012 onward). Both chambers form one Congress group.

## By chamber
{_chamber_table(res, docs)}

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

## Electronic vs paper filers
{len(per):,} members filed PTRs: {kinds['electronic only']:,} electronic only, {kinds['paper only']:,} paper only,
{kinds['mixed']:,} both. {paper_share_ptrs:.1%} of all PTRs are paper. The 10 most frequent filers account for
{top10_share:.1%} of PTRs, so a few members drive much of the sample. Members with the highest paper share:

| member | PTRs | paper |
|---|---:|---:|
{paper_rows}

Paper filers' trades are missing from every result. If they trade differently, the House result
describes electronic filers, not all members.

## Hand audit
`reports/audit/congress_match_audit_sample.csv`: {k} random matched transactions. Fill `audit_correct`.
"""
    (reports_dir / "data_quality_congress.md").write_text(md, encoding="utf-8")
    return {"parsed": len(res), "in_scope": n, "matched": matched, "reasons": reasons.to_dict()}
