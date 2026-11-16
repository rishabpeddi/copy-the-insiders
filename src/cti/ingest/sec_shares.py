"""Point-in-time shares outstanding from SEC XBRL frames (cover page, dei:EntityCommonStockSharesOutstanding).

One request per calendar quarter returns every filer's cover-page share count dated in that quarter:
    https://data.sec.gov/api/xbrl/frames/dei/EntityCommonStockSharesOutstanding/shares/CY2019Q4I.json
The cover-page date (`end`) is the "latest practicable date" just before the filing, so a value
becomes public a few days after `end`. The universe filter only uses values with
end + universe.shares_lag_days (cover) or shares_fallback_lag_days (wavg) < entry.

Known limits: one value per company per quarter, so multi-class companies may report only one class
(market cap understated); companies that don't file XBRL (some foreign/small filers) are missing.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path

import pandas as pd
import requests

from cti.config import DATA_DIR
from cti.ingest.raw import save_raw

# kind -> (frame URL, period suffix). "cover" = cover-page count (instant, per class for multi-class
# filers, which the frames API then omits); "wavg" = weighted-average basic shares for the quarter
# (duration, all classes combined), used as a fallback with a longer publication lag.
CONCEPTS = {
    "cover": "https://data.sec.gov/api/xbrl/frames/dei/EntityCommonStockSharesOutstanding/shares/CY{y}Q{q}I.json",
    "wavg": "https://data.sec.gov/api/xbrl/frames/us-gaap/WeightedAverageNumberOfSharesOutstandingBasic/shares/CY{y}Q{q}.json",
}


def frame_periods(start_year: int, today: dt.date | None = None) -> list[tuple[int, int]]:
    today = today or dt.date.today()
    out = []
    for y in range(start_year, today.year + 1):
        for q in range(1, 5):
            if dt.date(y, 3 * q - 2, 1) <= today:
                out.append((y, q))
    return out


def fetch(start_year: int, data_dir: Path = DATA_DIR, log=print) -> int:
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        raise RuntimeError("Set SEC_USER_AGENT to 'Your Name your-email@example.com'.")
    s = requests.Session()
    n = 0
    for kind, template in CONCEPTS.items():
        for y, q in frame_periods(start_year):
            url = template.format(y=y, q=q)
            r = s.get(url, headers={"User-Agent": ua}, timeout=120)
            if r.status_code == 404:  # quarter with no data yet
                log(f"shares {kind} CY{y}Q{q}: none yet")
                continue
            r.raise_for_status()
            save_raw("sec_shares", f"{kind}_CY{y}Q{q}.json", r.content, url=url, data_dir=data_dir)
            n += 1
            time.sleep(0.2)
    log(f"shares: {n} quarterly frames saved")
    return n


def parse_frame(raw: bytes, kind: str) -> pd.DataFrame:
    j = json.loads(raw)
    df = pd.DataFrame(j["data"])
    if df.empty:
        return pd.DataFrame(columns=["cik", "end", "shares", "accn", "kind"])
    df["cik"] = df["cik"].astype(int).astype(str).str.zfill(10)
    df["end"] = pd.to_datetime(df["end"])
    df["kind"] = kind
    return df.rename(columns={"val": "shares"})[["cik", "end", "shares", "accn", "kind"]]


def stage(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    root = data_dir / "raw" / "sec_shares"
    latest: dict[str, Path] = {}
    for p in sorted(root.glob("*/*_CY*.json")):
        latest[p.name] = p  # later snapshot of the same quarter wins
    if not latest:
        raise FileNotFoundError("No SEC share frames. Run `cti ingest shares`.")
    df = pd.concat([parse_frame(p.read_bytes(), p.name.split("_")[0]) for p in latest.values()],
                   ignore_index=True)
    df = df[df["shares"] > 0].drop_duplicates(["cik", "kind", "end"], keep="last")
    df = df.sort_values(["cik", "end", "kind"])
    out = data_dir / "staging" / "sec_shares.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return df
