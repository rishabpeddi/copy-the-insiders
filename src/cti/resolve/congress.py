"""Resolve Congress PTR transactions (ticker + asset name, no CIK) to securities.

Mapping ticker -> issuer CIK, in order:
  1. form4_ticker_history: an issuer whose own Form 4 filings reported this ticker around the trade
     date (within `max_gap_days` of its first/last such filing). Point-in-time, so renames and
     reused tickers resolve to the company that had the ticker THEN.
  2. sec_current_ticker: today's SEC ticker map. Only accepted if the asset name matches the
     company name (otherwise the ticker may have been reused: unmatched `name_mismatch`).
The price ticker for a CIK is the one the insider resolution already chose (follows renames),
else the reported ticker.

Every in-scope transaction ends matched with a confidence, or unmatched with a reason.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from cti.resolve.securities import normalize_ticker

_STOP = {"inc", "corp", "corporation", "company", "co", "ltd", "plc", "the", "class", "a", "b", "c",
         "common", "stock", "shares", "share", "holdings", "holding", "group", "ordinary", "new", "nv",
         "sa", "ag", "llc", "lp", "trust", "incorporated", "limited", "de", "spa",
         "and", "of", "adr", "ads", "depositary", "series", "par", "value", "cl", "com", "stores"}


def name_tokens(s) -> list[str]:
    """'McDonald's Corp' -> ['mcdonalds'], 'Wal-Mart Stores' -> ['walmart'], 'V.F. Corp' -> ['vf']."""
    if not isinstance(s, str):
        return []
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]|/[a-z]{2}/", " ", s.lower())
    s = re.sub(r"(?<=\w)['’.\-](?=\w)", "", s)  # join within-word punctuation
    return [t for t in re.findall(r"[a-z0-9]+", s) if t not in _STOP]


def names_match(a, b) -> bool:
    ta, tb = name_tokens(a), name_tokens(b)
    if {t for t in ta if len(t) > 1} & {t for t in tb if len(t) > 1}:
        return True
    ja, jb = "".join(ta), "".join(tb)  # 'v f' vs 'vf'
    return len(ja) >= 2 and len(jb) >= 2 and (ja == jb or (min(len(ja), len(jb)) >= 4 and (ja in jb or jb in ja)))


def scope(tx: pd.DataFrame) -> pd.Series:
    """Reason a transaction is out of scope, or None. Pre-2019 PTRs carry no asset codes."""
    r = pd.Series(None, index=tx.index, dtype=object)
    r[~tx["txn_type"].isin(["P", "S"])] = "not_purchase_or_sale"
    r[r.isna() & tx["asset_type"].notna() & (tx["asset_type"] != "ST")] = "not_stock_asset_type"
    r[r.isna() & tx["norm_ticker"].isna()] = "no_ticker"
    return r


def form4_ticker_history(filings: pd.DataFrame) -> pd.DataFrame:
    """filings: issuer_cik, issuer_ticker, issuer_name, filed_date -> one row per (ticker, cik) span."""
    f = filings.assign(t=filings["issuer_ticker"].map(normalize_ticker)).dropna(subset=["t"])
    f["filed_date"] = pd.to_datetime(f["filed_date"])
    return (f.groupby(["t", "issuer_cik"])
            .agg(first=("filed_date", "min"), last=("filed_date", "max"), n=("filed_date", "size"),
                 f4_name=("issuer_name", "last")).reset_index())


def map_to_cik(tx: pd.DataFrame, hist: pd.DataFrame, sec_map: pd.DataFrame, max_gap_days: int) -> pd.DataFrame:
    m = tx[["txn_id", "norm_ticker", "trade_date"]].merge(hist, left_on="norm_ticker", right_on="t", how="inner")
    td = pd.to_datetime(m["trade_date"])
    gap = np.maximum((m["first"] - td).dt.days, (td - m["last"]).dt.days).clip(lower=0)
    m = m.assign(gap=gap)[gap <= max_gap_days].sort_values(["txn_id", "gap", "n"], ascending=[True, True, False])
    f4 = m.drop_duplicates("txn_id").set_index("txn_id")[["issuer_cik", "f4_name"]]

    sec = sec_map.assign(t=sec_map["ticker"].str.replace(".", "-", regex=False)).drop_duplicates("t")
    cur = tx[["txn_id", "norm_ticker"]].merge(sec[["t", "cik", "name"]], left_on="norm_ticker", right_on="t",
                                              how="inner").set_index("txn_id")
    out = pd.DataFrame(index=tx["txn_id"])
    out["cik"] = f4["issuer_cik"].reindex(out.index)
    out["issuer_name"] = f4["f4_name"].reindex(out.index)
    out["match_method"] = np.where(out["cik"].notna(), "form4_ticker_history", None)
    use_cur = out["cik"].isna() & cur["cik"].reindex(out.index).notna()
    out.loc[use_cur, "cik"] = cur["cik"].reindex(out.index)[use_cur]
    out.loc[use_cur, "issuer_name"] = cur["name"].reindex(out.index)[use_cur]
    out.loc[use_cur, "match_method"] = "sec_current_ticker"
    return out.reset_index()


def resolve(tx: pd.DataFrame, hist: pd.DataFrame, sec_map: pd.DataFrame, insider_secs: pd.DataFrame,
            prices: pd.DataFrame, calendar: pd.DataFrame, max_gap_days: int = 365,
            min_history_days: int = 20) -> pd.DataFrame:
    from cti.ingest.reference import next_trading_day_after

    tx = tx.copy()
    tx["norm_ticker"] = tx["ticker"].map(normalize_ticker)
    tx["scope_reason"] = scope(tx)
    ins = tx[tx["scope_reason"].isna()]
    cik = map_to_cik(ins, hist, sec_map, max_gap_days)
    r = tx.merge(cik, on="txn_id", how="left")
    r["name_match"] = [names_match(a, b) for a, b in zip(r["asset"], r["issuer_name"], strict=True)]

    chosen = insider_secs.dropna(subset=["ticker"]).set_index("cik")["ticker"]
    r["price_ticker"] = r["cik"].map(chosen).fillna(r["norm_ticker"])
    r["security_id"] = np.where(r["cik"].notna(), "cik:" + r["cik"].fillna(""), None)

    counts = prices["ticker"].value_counts()
    priced = set(counts[counts >= min_history_days].index)
    first_px = prices[prices["ticker"].isin(priced)].groupby("ticker")["date"].min()
    r["public_date"] = pd.to_datetime(r["filing_date"])
    r["entry_date"] = next_trading_day_after(r["public_date"], calendar).to_numpy()

    reason = r["scope_reason"].copy()
    reason[reason.isna() & r["cik"].isna()] = "ticker_not_mapped"
    reason[reason.isna() & (r["match_method"] == "sec_current_ticker") & ~r["name_match"]] = "name_mismatch"
    reason[reason.isna() & ~r["price_ticker"].isin(priced)] = "ticker_not_in_price_source"
    reason[reason.isna() & r["entry_date"].isna()] = "entry_after_calendar_end"
    reason[reason.isna() & (r["entry_date"] < r["price_ticker"].map(first_px))] = "entry_before_price_history"
    reason[reason.isna() & ~(r["entry_date"] > r["public_date"])] = "entry_not_after_public"  # never expected
    r["unmatched_reason"] = reason
    r["matched"] = reason.isna()
    r["match_confidence"] = np.select(
        [~r["matched"], (r["match_method"] == "form4_ticker_history") & r["name_match"], r["name_match"]],
        [None, "high", "medium"], default="low")
    r["ticker"] = r["price_ticker"]
    r["filer_id"] = ("house:" + r["last"].str.upper().str.replace(r"[^A-Z]", "", regex=True) + ":"
                     + r["first"].str.upper().str.replace(r"[^A-Z]", "", regex=True).str[:12] + ":"
                     + r["state_dst"].fillna("").str.upper())
    return r
