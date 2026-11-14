"""SEC Insider Transactions Data Sets adapter (Forms 3/4/5, quarterly).

Source: https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets
Each quarter is a zip of tab-separated files (SUBMISSION, REPORTINGOWNER, NONDERIV_TRANS,
FOOTNOTES, ...). Raw zips are written once to data/raw/form4/ and never modified; a
checksum manifest records what was downloaded and when. Staging converts the tables we
use into one Parquet file per table per quarter: strings, plus parsed date columns.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import os
import re
import time
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import requests

from cti.config import DATA_DIR

URL = "https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{q}_form345.zip"
TABLES = ["SUBMISSION", "REPORTINGOWNER", "NONDERIV_TRANS", "FOOTNOTES"]
DATE_COLUMNS = {
    "SUBMISSION": ["FILING_DATE", "PERIOD_OF_REPORT", "DATE_OF_ORIG_SUB"],
    "NONDERIV_TRANS": ["TRANS_DATE", "DEEMED_EXECUTION_DATE"],
}
OPTIONAL_COLUMNS = {
    "SUBMISSION": ["AFF10B5ONE", "DATE_OF_ORIG_SUB"],  # 10b5-1 checkbox exists only since April 2023
    "NONDERIV_TRANS": ["DEEMED_EXECUTION_DATE"],
}
SEC_MIN_INTERVAL_S = 0.2  # SEC fair-access limit is 10 req/s; stay well under it.


def raw_dir(data_dir: Path = DATA_DIR) -> Path:
    return data_dir / "raw" / "form4"


def staging_dir(data_dir: Path = DATA_DIR) -> Path:
    return data_dir / "staging" / "form4"


def quarters(start: str, end: str) -> Iterator[str]:
    """'2014Q1', '2014Q3' -> '2014q1', '2014q2', '2014q3'."""
    pat = r"(\d{4})Q([1-4])"
    m1, m2 = re.fullmatch(pat, start.upper()), re.fullmatch(pat, end.upper())
    if not (m1 and m2):
        raise ValueError("Quarters must look like 2014Q1")
    y, q = int(m1[1]), int(m1[2])
    end_t = (int(m2[1]), int(m2[2]))
    while (y, q) <= end_t:
        yield f"{y}q{q}"
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)


def _user_agent() -> str:
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        raise RuntimeError(
            "Set SEC_USER_AGENT to 'Your Name your-email@example.com'. SEC blocks requests without one."
        )
    return ua


def _manifest_path(data_dir: Path) -> Path:
    return raw_dir(data_dir) / "MANIFEST.json"


def _load_manifest(data_dir: Path) -> dict:
    p = _manifest_path(data_dir)
    return json.loads(p.read_text()) if p.exists() else {}


def _save_manifest(m: dict, data_dir: Path) -> None:
    p = _manifest_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(m, indent=2, sort_keys=True))


def download(q: str, session: requests.Session | None = None, data_dir: Path = DATA_DIR) -> Path:
    """Download one quarter's zip to data/raw. Existing files are verified, never overwritten."""
    rd = raw_dir(data_dir)
    rd.mkdir(parents=True, exist_ok=True)
    path = rd / f"{q}_form345.zip"
    manifest = _load_manifest(data_dir)
    if path.exists():
        recorded = manifest.get(path.name, {}).get("sha256")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if recorded and recorded != actual:
            raise RuntimeError(f"{path.name} checksum changed since download. Raw data must be immutable.")
        return path

    s = session or requests.Session()
    resp = s.get(URL.format(q=q), headers={"User-Agent": _user_agent()}, timeout=180)
    resp.raise_for_status()
    bad = zipfile.ZipFile(io.BytesIO(resp.content)).testzip()  # fail fast on a corrupt download
    if bad:
        raise RuntimeError(f"{q}: corrupt member {bad} in downloaded zip")
    tmp = path.with_suffix(".part")
    tmp.write_bytes(resp.content)
    tmp.replace(path)
    manifest[path.name] = {
        "sha256": hashlib.sha256(resp.content).hexdigest(),
        "bytes": len(resp.content),
        "url": URL.format(q=q),
        "downloaded_utc": dt.datetime.now(dt.UTC).isoformat(),
    }
    _save_manifest(manifest, data_dir)
    time.sleep(SEC_MIN_INTERVAL_S)
    return path


def parse_sec_date(s: pd.Series) -> pd.Series:
    """SEC files use '31-MAR-2023'; tolerate ISO dates too. Unparseable -> NaT."""
    out = pd.to_datetime(s, format="%d-%b-%Y", errors="coerce")
    iso = pd.to_datetime(s.where(out.isna()), format="%Y-%m-%d", errors="coerce")
    return out.fillna(iso)


def read_table(zip_path: Path, table: str) -> pd.DataFrame:
    with zipfile.ZipFile(zip_path) as zf:
        name = next((n for n in zf.namelist() if Path(n).stem.upper() == table), None)
        if name is None:
            return pd.DataFrame()
        with zf.open(name) as f:
            df = pd.read_csv(f, sep="\t", dtype=str, keep_default_na=False, na_values=[""],
                             quoting=3, encoding="utf-8", encoding_errors="replace")
    for col in DATE_COLUMNS.get(table, []):
        if col in df.columns:
            df[col] = parse_sec_date(df[col])
    return df


def stage(zip_path: Path, data_dir: Path = DATA_DIR) -> dict[str, int]:
    """Write each table to data/staging/form4/<TABLE>/<quarter>.parquet. Returns row counts."""
    q = zip_path.name.split("_")[0]
    counts = {}
    for table in TABLES:
        df = read_table(zip_path, table)
        if df.empty:
            counts[table] = 0
            continue
        df.insert(0, "QUARTER", q)
        # Columns the SQL models rely on but that older quarters lack.
        for col in OPTIONAL_COLUMNS.get(table, []):
            if col not in df.columns:
                df[col] = pd.Series([None] * len(df), dtype="string")
        out = staging_dir(data_dir) / table / f"{q}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out, index=False)
        counts[table] = len(df)
    return counts


def ingest(start: str, end: str, data_dir: Path = DATA_DIR) -> dict[str, dict[str, int]]:
    session = requests.Session()
    return {q: stage(download(q, session, data_dir), data_dir) for q in quarters(start, end)}
