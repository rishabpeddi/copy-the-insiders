"""Fama-French 5 factors (2x3) + momentum, daily, from Kenneth French's data library.

Only the plain-http URLs work (the https host returns 404). Files are checksummed as raw snapshots.
Values are percent in the source; staged as decimals: date, mkt_rf, smb, hml, rmw, cma, rf, mom.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd
import requests

from cti.config import DATA_DIR
from cti.ingest.raw import latest_snapshot, save_raw

BASE = "http://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
FILES = {"ff5": "F-F_Research_Data_5_Factors_2x3_daily_CSV.zip", "mom": "F-F_Momentum_Factor_daily_CSV.zip"}


def fetch(data_dir: Path = DATA_DIR) -> None:
    for name in FILES.values():
        r = requests.get(BASE + name, timeout=120, headers={"User-Agent": "cti-research-prototype"})
        r.raise_for_status()
        save_raw("french_factors", name, r.content, url=BASE + name, data_dir=data_dir)


def parse_french_csv(zip_bytes: bytes) -> pd.DataFrame:
    """The CSV has prose above and below the table; the table starts at a line beginning with ','."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        text = zf.read(zf.namelist()[0]).decode("latin-1")
    lines = text.splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(","))
    rows = []
    for ln in lines[start + 1:]:
        if not ln.strip() or not ln.strip()[0].isdigit():
            break
        rows.append(ln)
    cols = ["date"] + [c.strip().lower().replace("-", "_") for c in lines[start].split(",")[1:]]
    df = pd.read_csv(io.StringIO("\n".join(rows)), header=None, names=cols)
    df["date"] = pd.to_datetime(df["date"].astype(str), format="%Y%m%d")
    for c in cols[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce") / 100.0
    return df


def stage(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    ff5 = parse_french_csv(latest_snapshot("french_factors", FILES["ff5"], data_dir).read_bytes())
    mom = parse_french_csv(latest_snapshot("french_factors", FILES["mom"], data_dir).read_bytes())
    df = ff5.merge(mom, on="date", how="inner")
    out = data_dir / "staging" / "factors_daily.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return df


def load(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    return pd.read_parquet(data_dir / "staging" / "factors_daily.parquet")
