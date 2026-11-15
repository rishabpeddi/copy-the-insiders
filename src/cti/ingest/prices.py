"""Price adapter. Free source (yfinance) for prototyping; swap in CRSP or a vendor later.

Every source returns the same long format (one row per ticker per day):
    ticker, date, open, high, low, close, adj_close, volume, split, dividend
where `close` and `open` are split-adjusted (not dividend-adjusted) and `adj_close` is the
total-return close. `stage_prices` adds:
    split_factor_after  product of splits strictly after `date` (nominal = close * factor)
    close_nominal       the price as it was quoted that day; comparable to Form 4 prices
    adj_open            open on the total-return scale, so adj_open/adj_close(prev) is the overnight return

Known limit: yfinance mostly covers stocks that still trade (survivorship bias). Securities it
cannot find are logged as unmatched with reason `ticker_not_in_price_source`.
"""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Protocol

import pandas as pd

from cti.config import DATA_DIR
from cti.ingest.raw import save_raw, snapshot_dir

LONG_COLUMNS = ["ticker", "date", "open", "high", "low", "close", "adj_close", "volume", "split", "dividend"]
_YF_RENAME = {"Open": "open", "High": "high", "Low": "low", "Close": "close", "Adj Close": "adj_close",
              "Volume": "volume", "Stock Splits": "split", "Dividends": "dividend"}


class PriceSource(Protocol):
    name: str

    def fetch(self, tickers: list[str], start: str, end: str) -> pd.DataFrame: ...


def reshape_yfinance(df: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """yfinance wide frame (MultiIndex ticker x field, group_by='ticker') -> long format."""
    if df is None or df.empty:
        return pd.DataFrame(columns=LONG_COLUMNS)
    if df.columns.nlevels == 1:  # single ticker without group level
        df = pd.concat({tickers[0]: df}, axis=1)
    parts = []
    for t in df.columns.get_level_values(0).unique():
        sub = df[t].rename(columns=_YF_RENAME)
        sub = sub.dropna(subset=[c for c in ("open", "close") if c in sub.columns], how="any")
        if sub.empty:
            continue
        for c in LONG_COLUMNS[2:]:
            if c not in sub.columns:
                sub[c] = 0.0 if c in ("split", "dividend") else float("nan")
        sub = sub.reset_index().rename(columns={"Date": "date", "index": "date"})
        sub["ticker"] = t
        parts.append(sub[LONG_COLUMNS])
    if not parts:
        return pd.DataFrame(columns=LONG_COLUMNS)
    out = pd.concat(parts, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.tz_localize(None).dt.normalize()
    out[["split", "dividend"]] = out[["split", "dividend"]].fillna(0.0)
    return out


class YFinanceSource:
    name = "yfinance"

    def __init__(self, batch_size: int = 50, pause_s: float = 1.0, retries: int = 2):
        self.batch_size, self.pause_s, self.retries = batch_size, pause_s, retries

    def _download(self, tickers: list[str], start: str, end: str) -> pd.DataFrame:
        import yfinance as yf

        # threads=False: yfinance's SQLite timezone cache locks under threads on Windows.
        wide = yf.download(tickers, start=start, end=end, auto_adjust=False, actions=True,
                           group_by="ticker", progress=False, threads=False)
        return reshape_yfinance(wide, tickers)

    def fetch(self, tickers: list[str], start: str, end: str) -> pd.DataFrame:
        frames, todo = [], list(tickers)
        for attempt in range(self.retries + 1):
            got: set[str] = set()
            for i in range(0, len(todo), self.batch_size):
                df = self._download(todo[i:i + self.batch_size], start, end)
                frames.append(df)
                got |= set(df["ticker"])
                time.sleep(self.pause_s)
            todo = [t for t in todo if t not in got]
            if not todo or attempt == self.retries:
                break
            time.sleep(self.pause_s * 5)
        out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=LONG_COLUMNS)
        return out.drop_duplicates(["ticker", "date"], keep="last")


def add_derived(px: pd.DataFrame) -> pd.DataFrame:
    """Split factor, nominal close and total-return open. Pure function of one ticker's full history."""
    px = px.sort_values(["ticker", "date"]).copy()
    split = px["split"].where(px["split"] > 0, 1.0)
    # factor_after(d) = product of splits on dates > d = (product up to and incl. last) / (product up to d)
    cum = split.groupby(px["ticker"]).cumprod()
    total = cum.groupby(px["ticker"]).transform("last")
    px["split_factor_after"] = total / cum
    px["close_nominal"] = px["close"] * px["split_factor_after"]
    px["adj_open"] = px["open"] * px["adj_close"] / px["close"]
    return px


def fetch_and_stage(tickers: list[str], start: str, end: str, source: PriceSource,
                    data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Fetch, save the raw pull as an immutable snapshot, and rebuild staging from all snapshots."""
    tickers = sorted(set(tickers))
    pulled = source.fetch(tickers, start, end)
    buf = io.BytesIO()
    pulled.to_parquet(buf, index=False)
    stamp = time.strftime("%H%M%S")
    save_raw(f"prices_{source.name}", f"pull_{stamp}.parquet", buf.getvalue(),
             url=f"{source.name}:{len(tickers)} tickers {start}..{end}", data_dir=data_dir)
    missing = sorted(set(tickers) - set(pulled["ticker"]))
    save_raw(f"prices_{source.name}", f"pull_{stamp}_not_found.txt", "\n".join(missing).encode(),
             data_dir=data_dir)
    return stage_prices(source.name, data_dir)


def stage_prices(source_name: str, data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Union every raw pull (later pulls win per ticker), derive columns, write staging parquet."""
    root = data_dir / "raw" / f"prices_{source_name}"
    pulls = sorted(root.glob("*/pull_*.parquet"))
    if not pulls:
        raise FileNotFoundError(f"No raw price pulls under {root}")
    frames = []
    for order, p in enumerate(pulls):
        df = pd.read_parquet(p)
        df["_order"] = order
        frames.append(df)
    allpx = pd.concat(frames, ignore_index=True)
    # A later pull of a ticker replaces its whole history (adjustments change retroactively).
    latest = allpx.groupby("ticker")["_order"].transform("max")
    allpx = allpx[allpx["_order"] == latest].drop(columns="_order")
    staged = add_derived(allpx)
    out = data_dir / "staging" / "prices" / f"{source_name}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    staged.to_parquet(out, index=False)
    nf = sorted(set().union(*[set(p.read_text().split()) for p in root.glob("*/pull_*_not_found.txt")])
                - set(staged["ticker"]))
    (data_dir / "staging" / "prices" / f"{source_name}_not_found.txt").write_text("\n".join(nf))
    return staged


__all__ = ["PriceSource", "YFinanceSource", "fetch_and_stage", "stage_prices", "add_derived",
           "reshape_yfinance", "snapshot_dir"]
