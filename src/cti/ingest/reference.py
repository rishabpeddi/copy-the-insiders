"""Reference data: SPY + sector ETFs, 3-month T-bill returns, trading calendar, SEC ticker map.

- Trading calendar = the dates SPY traded. That is the exchange calendar by construction, and
  needs no extra dependency.
- T-bill: US Treasury 13-week bill rate (discount basis, % per year; same measure as FRED DTB3). Daily return on
  trading day t = rate(previous trading day)/100 * calendar days since the previous trading day / 360.
  Using the previous day's rate means the return for t is known at the start of t.
- SEC company_tickers_exchange.json maps CIK -> current ticker + exchange. It is a CURRENT
  snapshot, so it cannot by itself resolve companies that were delisted or changed tickers.
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
from pathlib import Path

import pandas as pd
import requests

from cti.config import DATA_DIR
from cti.ingest.raw import latest_snapshot, save_raw

SPY = "SPY"
# XLRE starts Oct 2015 and XLC June 2018; before that their sectors sat inside XLF and XLK/XLY.
SECTOR_ETFS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY"]
REFERENCE_TICKERS = [SPY, *SECTOR_ETFS]

TREASURY_URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
                "daily-treasury-rates.csv/{y}/all?type=daily_treasury_bill_rates&field_tdr_date_value={y}"
                "&page&_format=csv")
TREASURY_COL = "13 WEEKS BANK DISCOUNT"  # same measure as FRED DTB3 (3-month, discount basis, %)
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers_exchange.json"


def fetch_tbill(start_year: int, data_dir: Path = DATA_DIR) -> list[Path]:
    """US Treasury daily bill rates, one raw CSV per year. (FRED's CSV endpoint refuses scripted
    downloads from some networks; Treasury is the primary source anyway.)"""
    paths = []
    for y in range(start_year, dt.date.today().year + 1):
        url = TREASURY_URL.format(y=y)
        r = requests.get(url, timeout=60, headers={"User-Agent": "cti-research-prototype"})
        r.raise_for_status()
        paths.append(save_raw("treasury_bills", f"bills_{y}.csv", r.content, url=url, data_dir=data_dir))
    return paths


def parse_treasury(raw: bytes) -> pd.Series:
    df = pd.read_csv(io.BytesIO(raw))
    s = pd.to_numeric(df[TREASURY_COL], errors="coerce")
    s.index = pd.to_datetime(df["Date"], format="%m/%d/%Y")
    return s.dropna().rename("TBILL_13W")


def fetch_sec_tickers(data_dir: Path = DATA_DIR) -> Path:
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        raise RuntimeError("Set SEC_USER_AGENT to 'Your Name your-email@example.com'.")
    r = requests.get(SEC_TICKERS_URL, timeout=60, headers={"User-Agent": ua})
    r.raise_for_status()
    return save_raw("sec_tickers", "company_tickers_exchange.json", r.content, url=SEC_TICKERS_URL,
                    data_dir=data_dir)


def parse_sec_tickers(raw: bytes) -> pd.DataFrame:
    """-> cik (10-digit string), name, ticker, exchange. One CIK can have several tickers (classes)."""
    j = json.loads(raw)
    df = pd.DataFrame(j["data"], columns=j["fields"])
    df["cik"] = df["cik"].astype(int).astype(str).str.zfill(10)
    df["ticker"] = df["ticker"].str.upper().str.strip()
    return df[["cik", "name", "ticker", "exchange"]]


def build_calendar(trading_dates) -> pd.DataFrame:
    d = pd.DatetimeIndex(sorted(set(pd.to_datetime(list(trading_dates))))).normalize()
    return pd.DataFrame({"date": d, "next_trading_day": list(d[1:]) + [pd.NaT]})


def next_trading_day_after(dates, calendar: pd.DataFrame) -> pd.Series:
    """First trading day strictly after each date (NaT past the calendar end)."""
    cal = pd.DatetimeIndex(calendar["date"])
    x = pd.to_datetime(pd.Series(dates)).dt.normalize()
    pos = cal.searchsorted(x.to_numpy(), side="right")
    out = pd.Series(pd.NaT, index=x.index, dtype="datetime64[ns]")
    ok = pos < len(cal)
    out[ok] = cal[pos[ok]]
    return out


def tbill_daily_returns(dtb3: pd.Series, calendar: pd.DataFrame) -> pd.Series:
    cal = pd.DatetimeIndex(calendar["date"])
    rate = dtb3.sort_index().reindex(cal.union(dtb3.index)).ffill().reindex(cal)
    prev_rate = rate.shift(1)
    days = pd.Series(cal, index=cal).diff().dt.days
    r = (prev_rate / 100.0) * days / 360.0
    return r.fillna(0.0).rename("TBILL")


def load_sec_tickers(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    return parse_sec_tickers(latest_snapshot("sec_tickers", "company_tickers_exchange.json", data_dir)
                             .read_bytes())


def load_tbill(data_dir: Path = DATA_DIR) -> pd.Series:
    """Latest snapshot of each year's file, concatenated."""
    root = data_dir / "raw" / "treasury_bills"
    years = sorted({p.name for p in root.glob("*/bills_*.csv")})
    if not years:
        raise FileNotFoundError("No Treasury bill snapshots. Run `cti ingest reference`.")
    parts = [parse_treasury(latest_snapshot("treasury_bills", y, data_dir).read_bytes()) for y in years]
    s = pd.concat(parts).sort_index()
    return s[~s.index.duplicated(keep="last")]


def reference_returns(prices: pd.DataFrame, calendar: pd.DataFrame, dtb3: pd.Series) -> pd.DataFrame:
    """Long table: date, series, total_return for SPY, sector ETFs and TBILL."""
    ref = prices[prices["ticker"].isin(REFERENCE_TICKERS)].sort_values(["ticker", "date"])
    ref = ref.assign(total_return=ref.groupby("ticker")["adj_close"].pct_change())
    out = ref[["date", "ticker", "total_return"]].rename(columns={"ticker": "series"}).dropna()
    tb = tbill_daily_returns(dtb3, calendar)
    tb_df = pd.DataFrame({"date": tb.index, "series": "TBILL", "total_return": tb.to_numpy()})
    return pd.concat([out, tb_df], ignore_index=True)
