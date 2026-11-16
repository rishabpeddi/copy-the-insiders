"""SIC industry codes per CIK (SEC submissions API) and an approximate SIC -> sector-ETF map.

    https://data.sec.gov/submissions/CIK##########.json  ->  "sic", "sicDescription"

The SIC code is the company's CURRENT classification. The map to the 11 Select Sector SPDR
ETFs is an approximation of GICS sectors (SIC and GICS don't line up exactly); the sector clone
built from it is a secondary benchmark only. Before XLRE (Oct 2015) and XLC (Jun 2018) existed,
those sectors fall back to SPY in the clone.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

from cti.config import DATA_DIR

URL = "https://data.sec.gov/submissions/CIK{cik}.json"


def fetch(ciks: list[str], data_dir: Path = DATA_DIR, log=print) -> pd.DataFrame:
    """Cache one small JSON summary per CIK under data/raw/sec_sic/; skip ones already fetched."""
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        raise RuntimeError("Set SEC_USER_AGENT to 'Your Name your-email@example.com'.")
    root = data_dir / "raw" / "sec_sic"
    root.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    todo = [c for c in sorted(set(ciks)) if not (root / f"{c}.json").exists()]
    for k, cik in enumerate(todo, 1):
        r = s.get(URL.format(cik=cik), headers={"User-Agent": ua}, timeout=60)
        if r.status_code == 404:
            (root / f"{cik}.json").write_text(json.dumps({"cik": cik, "sic": None, "status": 404}))
        else:
            r.raise_for_status()
            j = r.json()
            (root / f"{cik}.json").write_text(json.dumps(
                {"cik": cik, "sic": j.get("sic"), "sicDescription": j.get("sicDescription"), "name": j.get("name")}))
        if k % 500 == 0:
            log(f"sic: {k:,}/{len(todo):,}")
        time.sleep(0.12)
    return stage(data_dir)


def stage(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    rows = [json.loads(p.read_text()) for p in (data_dir / "raw" / "sec_sic").glob("*.json")]
    df = pd.DataFrame(rows)
    df["sic"] = pd.to_numeric(df["sic"], errors="coerce")
    df["sector_etf"] = df["sic"].map(sic_to_etf)
    df.to_parquet(data_dir / "staging" / "sec_sic.parquet", index=False)
    return df


def sic_to_etf(sic) -> str | None:  # noqa: C901 - a lookup table, kept flat for readability
    if pd.isna(sic):
        return None
    s = int(sic)
    two = s // 100
    if 100 <= s < 1000:
        return "XLP"                          # agriculture
    if two == 10 or two == 14:
        return "XLB"                          # metal / nonmetallic mining
    if two in (12, 13, 29):
        return "XLE"                          # coal, oil & gas, refining
    if 15 <= two <= 17:
        return "XLI"                          # construction
    if two in (20, 21):
        return "XLP"                          # food, tobacco
    if two in (22, 23, 25, 31, 39):
        return "XLY"                          # textiles, apparel, furniture, leather, misc. consumer goods
    if two in (24, 26, 30, 32, 33):
        return "XLB"                          # lumber, paper, plastics, glass, metals
    if two == 27:
        return "XLC"                          # publishing
    if two == 28:
        return "XLV" if 2830 <= s <= 2836 else ("XLP" if s == 2844 else "XLB")  # pharma / cosmetics / chemicals
    if two == 34:
        return "XLI"
    if two == 35:
        return "XLK" if 3570 <= s <= 3579 else "XLI"   # computers / machinery
    if two == 36:
        return "XLK" if s not in (3630, 3634, 3651) else "XLY"  # electronics / household appliances & audio
    if two == 37:
        return "XLY" if 3710 <= s <= 3716 or s == 3751 else "XLI"  # autos / aerospace & other transport
    if two == 38:
        return "XLV" if 3840 <= s <= 3851 else "XLK"   # medical instruments / measuring & lab instruments
    if 40 <= two <= 47:
        return "XLI"                          # transportation
    if two == 48:
        return "XLC"                          # telecom, broadcasting, cable
    if two == 49:
        return "XLU"
    if two == 50:
        return "XLI"
    if two == 51:
        return "XLP"
    if 52 <= two <= 59:
        return "XLP" if two == 54 or s == 5912 else "XLY"  # grocery & drug stores / other retail
    if two in (60, 61, 62, 63, 64):
        return "XLF"
    if two == 65 or s == 6798:
        return "XLRE"
    if two == 67:
        return "XLF"
    if two == 73:
        return "XLK" if 7370 <= s <= 7379 else "XLI"   # software & IT services / other business services
    if two in (70, 72, 75, 79, 82):
        return "XLY"
    if two == 78:
        return "XLC"
    if two in (80, 83):
        return "XLV"
    if two == 87:
        return "XLI"
    return None
