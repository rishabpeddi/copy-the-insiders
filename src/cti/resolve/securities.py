"""Resolve Form 4 issuers (CIK + reported ticker) to a security with a price history.

security_id = "cik:<10-digit CIK>". The issuer CIK is stable across ticker changes, so it is
the key. Choosing the ticker used for prices, per issuer, in this order:
  1. a current SEC ticker for the CIK that also appears in the filings    -> cik_and_filing_ticker
  2. the SEC's current primary ticker for the CIK                         -> cik_current_ticker
  3. the most recently reported filing ticker                             -> filing_ticker
taking the first that exists in the price source.

Then each transaction gets a price check: reported price / nominal close on the trade date. This
catches ticker reuse (the ticker now belongs to a different company) and data-entry errors.
Thresholds come from prereg.yaml `resolution`. Nothing is dropped silently: every candidate gets
either a match with method + confidence, or an unmatched reason.
"""

from __future__ import annotations

import math
import re

import numpy as np
import pandas as pd

from cti.ingest.reference import next_trading_day_after

_JUNK = {"NONE", "N/A", "NA", "NULL", "-", "--", "0", "NOTICKER", "NONE."}
_VALID = re.compile(r"^[A-Z][A-Z0-9\-]{0,9}$")


def normalize_ticker(raw) -> str | None:
    """'NYSE:NYCB' -> NYCB, 'GEF,GEF.B' -> GEF, '(CALX)' -> CALX, 'BRK.B' -> BRK-B, 'NONE' -> None."""
    if raw is None or (isinstance(raw, float) and math.isnan(raw)):
        return None
    s = str(raw).upper().strip().strip("[](){}$ ").strip()
    if s in _JUNK:  # before splitting, so 'N/A' doesn't become 'N'
        return None
    if ":" in s:
        s = s.split(":", 1)[1].strip()
    tokens = [t for t in re.split(r"[,;/\s]+", s) if t]
    if not tokens:
        return None
    t = tokens[0].strip("[](){}$.").replace(".", "-")
    if t in _JUNK or not _VALID.match(t):
        return None
    return t


def choose_tickers(candidates: pd.DataFrame, sec_map: pd.DataFrame, priced: set[str]) -> pd.DataFrame:
    """One row per issuer_cik: security_id, ticker, match_method, or unmatched_reason."""
    c = candidates.assign(norm=candidates["issuer_ticker"].map(normalize_ticker))
    filing = (c.dropna(subset=["norm"]).sort_values("public_date", ascending=False)
              .groupby("issuer_cik")["norm"].apply(lambda s: list(dict.fromkeys(s))))
    sec = sec_map.groupby("cik")["ticker"].apply(list)
    names = c.groupby("issuer_cik")["issuer_name"].last()
    exch = sec_map.drop_duplicates("cik").set_index("cik")["exchange"]

    rows = []
    for cik in c["issuer_cik"].unique():
        f = filing.get(cik, [])
        s = [t.replace(".", "-") for t in sec.get(cik, [])]
        ordered = [(t, "cik_and_filing_ticker") for t in s if t in f]
        ordered += [(s[0], "cik_current_ticker")] if s else []
        ordered += [(t, "filing_ticker") for t in f]
        hit = next(((t, m) for t, m in ordered if t in priced), None)
        reason = None if hit else ("no_ticker_candidates" if not ordered else "ticker_not_in_price_source")
        rows.append({
            "security_id": f"cik:{cik}", "cik": cik, "name": names.get(cik),
            "ticker": hit[0] if hit else None, "match_method": hit[1] if hit else None,
            "exchange": exch.get(cik), "candidate_tickers": [t for t, _ in ordered],
            "unmatched_reason": reason,
        })
    return pd.DataFrame(rows)


def resolve(candidates: pd.DataFrame, sec_map: pd.DataFrame, prices: pd.DataFrame,
            calendar: pd.DataFrame, tight_pct: float, max_ratio: float,
            min_history_days: int = 20) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    candidates: txn_id, issuer_cik, issuer_ticker, issuer_name, trade_date, public_date, reported_price
    prices: staged long format (ticker, date, close_nominal, ...)
    Returns (securities, resolution) where resolution has one row per candidate txn.
    Tickers with fewer than `min_history_days` rows (delisted-ticker stubs) are not treated as priced.
    """
    counts = prices["ticker"].value_counts()
    priced = set(counts[counts >= min_history_days].index)
    prices = prices[prices["ticker"].isin(priced)]
    secs = choose_tickers(candidates, sec_map, priced)
    span = prices.groupby("ticker")["date"].agg(["min", "max"])
    secs["listed_from"] = secs["ticker"].map(span["min"])
    secs["listed_to"] = secs["ticker"].map(span["max"])

    r = candidates.merge(secs[["cik", "security_id", "ticker", "match_method", "unmatched_reason"]],
                         left_on="issuer_cik", right_on="cik", how="left").drop(columns="cik")
    r["trade_date"] = pd.to_datetime(r["trade_date"])
    r["public_date"] = pd.to_datetime(r["public_date"])
    r["entry_date"] = next_trading_day_after(r["public_date"], calendar).to_numpy()

    # Price on entry day, and nominal close on (or just before) the trade date.
    px = prices[["ticker", "date", "close_nominal"]].copy()
    px["date"] = pd.to_datetime(px["date"])
    keys = px[["ticker", "date"]].drop_duplicates().rename(columns={"date": "entry_date"})
    keys["has_entry_price"] = True
    r["entry_date"] = r["entry_date"].astype("datetime64[ns]")
    keys["entry_date"] = keys["entry_date"].astype("datetime64[ns]")
    r = r.merge(keys, on=["ticker", "entry_date"], how="left")
    r["has_entry_price"] = r["has_entry_price"].eq(True)

    r = r.sort_values("trade_date").reset_index(drop=True)
    r["trade_date"] = r["trade_date"].astype("datetime64[ns]")
    px["date"] = px["date"].astype("datetime64[ns]")
    has_t = r["ticker"].notna() & r["trade_date"].notna()
    asof = pd.merge_asof(r.loc[has_t, ["trade_date", "ticker"]].reset_index(),
                         px.sort_values("date").rename(columns={"date": "trade_date"}),
                         on="trade_date", by="ticker", direction="backward",
                         tolerance=pd.Timedelta(days=7)).set_index("index")
    r["close_nominal_at_trade"] = asof["close_nominal"]
    r["price_ratio"] = r["reported_price"] / r["close_nominal_at_trade"]
    r.loc[~(r["reported_price"] > 0), "price_ratio"] = np.nan

    lr = np.abs(np.log(r["price_ratio"]))
    strong = r["match_method"].eq("cik_and_filing_ticker")
    conf = np.select(
        [r["price_ratio"].isna() & strong, r["price_ratio"].isna(),
         (lr <= math.log1p(tight_pct)) & strong, lr <= math.log1p(tight_pct), lr <= math.log(max_ratio)],
        ["medium", "low", "high", "medium", "low"], default="mismatch")
    r["match_confidence"] = np.where(r["ticker"].isna(), None, conf)

    reason = r["unmatched_reason"].copy()
    reason[reason.isna() & r["entry_date"].isna()] = "entry_after_calendar_end"
    reason[reason.isna() & ~r["has_entry_price"]] = "no_price_on_entry_date"
    reason[reason.isna() & (r["match_confidence"] == "mismatch")] = "price_mismatch"
    r["unmatched_reason"] = reason
    r["matched"] = reason.isna()
    r.loc[~r["matched"], "match_confidence"] = None

    cols = ["txn_id", "security_id", "ticker", "match_method", "match_confidence", "matched",
            "unmatched_reason", "trade_date", "public_date", "entry_date", "reported_price",
            "close_nominal_at_trade", "price_ratio", "issuer_cik", "issuer_ticker", "issuer_name"]
    return secs, r[cols]
