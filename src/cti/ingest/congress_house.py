"""House of Representatives Periodic Transaction Reports (PTRs) from the House Clerk.

Index:  https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip  (XML, every filing)
PTR:    https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{DocID}.pdf

DocIDs starting with "2" are electronically filed PDFs with a text layer and are parsed. Others
("8", "9") are scanned paper filings with no text; they are counted, not parsed (OCR is future
work). The index starts listing PTRs in 2015.

Raw files are immutable: data/raw/house_ptr/{year}/{DocID}.pdf plus a per-year MANIFEST.json.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import re
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

from cti.config import DATA_DIR
from cti.ingest.raw import save_raw

INDEX_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{y}FD.zip"
PTR_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{y}/{doc}.pdf"
UA = {"User-Agent": "cti-research-prototype"}
PAUSE_S = 0.25


def fetch_index(year: int, session: requests.Session, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    r = session.get(INDEX_URL.format(y=year), headers=UA, timeout=120)
    r.raise_for_status()
    save_raw("house_index", f"{year}FD.zip", r.content, url=INDEX_URL.format(y=year), data_dir=data_dir)
    return parse_index(r.content)


def parse_index(zip_bytes: bytes) -> pd.DataFrame:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".xml"))
        xml = zf.read(name).decode("utf-8-sig", errors="replace")
    rows = []
    for m in re.findall(r"<Member>(.*?)</Member>", xml, re.S):
        def g(tag: str, m: str = m) -> str:
            x = re.search(rf"<{tag}>(.*?)</{tag}>", m, re.S)
            return x.group(1).strip() if x else ""
        if g("FilingType") != "P":
            continue
        rows.append({"doc_id": g("DocID"), "year": int(g("Year") or 0), "last": g("Last"), "first": g("First"),
                     "prefix": g("Prefix"), "suffix": g("Suffix"), "state_dst": g("StateDst"),
                     "filing_date": pd.to_datetime(g("FilingDate"), format="%m/%d/%Y", errors="coerce")})
    df = pd.DataFrame(rows)
    if not df.empty:
        df["electronic"] = df["doc_id"].str.startswith("2")
    return df


def download_ptrs(index: pd.DataFrame, session: requests.Session, data_dir: Path = DATA_DIR, log=print) -> int:
    """Download electronic PTR PDFs not already on disk. Returns the number downloaded."""
    n = 0
    for year, grp in index[index["electronic"]].groupby("year"):
        d = data_dir / "raw" / "house_ptr" / str(year)
        d.mkdir(parents=True, exist_ok=True)
        mpath = d / "MANIFEST.json"
        manifest = json.loads(mpath.read_text()) if mpath.exists() else {}
        for i, doc in enumerate(grp["doc_id"]):
            path = d / f"{doc}.pdf"
            if path.exists():
                continue
            url = PTR_URL.format(y=year, doc=doc)
            r = session.get(url, headers=UA, timeout=120)
            if r.status_code == 404:
                manifest[path.name] = {"status": 404, "url": url}
                continue
            r.raise_for_status()
            tmp = path.with_suffix(".part")
            tmp.write_bytes(r.content)
            tmp.replace(path)
            manifest[path.name] = {"sha256": hashlib.sha256(r.content).hexdigest(), "bytes": len(r.content),
                                   "url": url, "fetched_utc": dt.datetime.now(dt.UTC).isoformat()}
            n += 1
            if n % 200 == 0:
                mpath.write_text(json.dumps(manifest, indent=1, sort_keys=True))
                log(f"house ptr: {n} downloaded (at {year}, {i + 1}/{len(grp)})")
            time.sleep(PAUSE_S)
        mpath.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return n


def ingest(start_year: int, end_year: int, data_dir: Path = DATA_DIR, log=print) -> pd.DataFrame:
    s = requests.Session()
    idx = pd.concat([fetch_index(y, s, data_dir) for y in range(start_year, end_year + 1)], ignore_index=True)
    out = data_dir / "staging" / "congress"
    out.mkdir(parents=True, exist_ok=True)
    idx.to_parquet(out / "house_index.parquet", index=False)
    log(f"house index: {len(idx):,} PTRs, {int(idx['electronic'].sum()):,} electronic")
    download_ptrs(idx, s, data_dir, log)
    return idx


def _parse_one(path: str) -> tuple[str, list[dict], str | None]:
    from cti.ingest.congress_parse import parse_text, pdf_text

    try:
        return path, parse_text(pdf_text(path)), None
    except Exception as e:  # a corrupt PDF must not kill the batch; it's logged per document
        return path, [], f"{type(e).__name__}: {e}"[:200]


def stage(data_dir: Path = DATA_DIR, workers: int = 6, log=print) -> pd.DataFrame:
    """Parse every downloaded electronic PTR -> staging/congress/house_transactions.parquet.
    Also writes house_documents.parquet: one row per PTR in the index with its parse status."""
    from concurrent.futures import ProcessPoolExecutor

    idx = pd.read_parquet(data_dir / "staging" / "congress" / "house_index.parquet")
    paths = {str(p): p.stem for p in (data_dir / "raw" / "house_ptr").glob("*/2*.pdf")}
    rows, status = [], {}
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for k, (path, parsed, err) in enumerate(ex.map(_parse_one, list(paths), chunksize=16), 1):
            doc = paths[path]
            status[doc] = ("parse_error" if err else "parsed" if parsed else "no_transactions_found", err)
            rows += [{"doc_id": doc, **r} for r in parsed]
            if k % 1000 == 0:
                log(f"house parse: {k:,}/{len(paths):,}")
    tx = pd.DataFrame(rows)
    docs = idx.copy()
    docs["status"] = docs["doc_id"].map(lambda d: status.get(d, (None,))[0])
    docs.loc[~docs["electronic"], "status"] = "paper_scan_not_parsed"
    docs.loc[docs["electronic"] & docs["status"].isna(), "status"] = "not_downloaded"
    docs["error"] = docs["doc_id"].map(lambda d: status.get(d, (None, None))[1])
    docs["n_transactions"] = docs["doc_id"].map(tx.groupby("doc_id").size() if len(tx) else {}).fillna(0)
    out = data_dir / "staging" / "congress"
    docs.to_parquet(out / "house_documents.parquet", index=False)
    if len(tx):
        tx = tx.merge(idx[["doc_id", "last", "first", "state_dst", "filing_date"]], on="doc_id", how="left")
    tx.to_parquet(out / "house_transactions.parquet", index=False)
    log(f"house parse: {len(tx):,} transactions from {int((docs['status'] == 'parsed').sum()):,} PTRs; "
        + ", ".join(f"{k}={v:,}" for k, v in docs["status"].value_counts().items()))
    return tx
