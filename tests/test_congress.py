"""House PTR parsing and Congress resolution, on hand-written text shaped like real PTR layouts."""

from __future__ import annotations

import pandas as pd
import pytest

from cti.ingest.congress_parse import parse_text
from cti.resolve.congress import form4_ticker_history, names_match, resolve

# 2015-2018 layout: no asset codes, ticker sometimes wrapped to the next line, case mangled by the font.
OLD = """tranSactionS
iD owner asset transaction Date notification amount
type Date
Eaton Corporation, PLC ordinary Shares S 02/25/2015 02/25/2015 $1,001 - $15,000
(ETN)
FILING STATuS: New
SubHoLDING oF: Morgan Stanley IRA - X141
PPG Industries, Inc. (PPG) P 03/4/2015 03/4/2015 $1,001 - $15,000
FILING STATuS: New
SP u.S. Treasury Bills P 02/23/2017 02/28/2017 Spouse/DC Over
$1,000,000
FIlINg STaTuS: New
"""

# 2020+ layout: asset codes, owner column, amount high end wrapped, labels blanked with odd glyphs.
NEW = """ID Owner Asset Transaction Date Notification Amount Cap.
Type Date Gains >
$200?
SP Alphabet Inc. - Class A (gOOgl) P 02/28/2020 03/20/2020 $15,001 -
[ST] $50,000
F     S    : New
S     O : Schwab Brokerage Account
JT Microsoft Corporation (MSFT) [ST] S (partial) 04/06/2020 04/07/2020 $1,001 - $15,000
F     S    : New
JT Artistry in Motion, LLC [OI] P 04/15/2026 04/15/2026 $50,001 -
$100,000
* For the complete list of asset type abbreviations, please visit https://fd.house.gov/reference/asset-type-codes.aspx.
"""


def test_old_layout():
    rows = parse_text(OLD)
    assert [r["ticker"] for r in rows] == ["ETN", "PPG", None]
    assert [r["txn_type"] for r in rows] == ["S", "P", "P"]
    assert rows[0]["asset"].startswith("Eaton Corporation") and rows[0]["asset_type"] is None
    assert rows[1]["trade_date"] == pd.Timestamp("2015-03-04")
    assert rows[2]["owner"] == "SP" and rows[2]["amount_low"] == 1_000_001 and rows[2]["amount_high"] is None


def test_new_layout():
    rows = parse_text(NEW)
    assert [(r["owner"], r["ticker"], r["asset_type"], r["txn_type"]) for r in rows] == [
        ("SP", "GOOGL", "ST", "P"), ("JT", "MSFT", "ST", "S"), ("JT", None, "OI", "P")]
    assert rows[0]["amount_low"] == 15_001 and rows[0]["amount_high"] == 50_000
    assert rows[1]["partial"] is True
    assert "Schwab" not in rows[0]["asset"] and ":" not in rows[0]["asset"]  # labels never leak into names
    assert rows[2]["amount_high"] == 100_000


@pytest.mark.parametrize("a,b,ok", [
    ("McDonald's Corporation (MCD)", "MCDONALDS CORP", True),
    ("V.F. Corporation (VFC)", "V F CORP", True),
    ("Wal-Mart Stores, Inc. (WMT)", "Walmart Inc.", True),
    ("American International group, Inc. New (AIg)", "AMERICAN INTERNATIONAL GROUP, INC.", True),
    ("Barrick gold Corporation (ABX)", "Abacus Global Management, Inc.", False),
    ("ENI S.p.A. (E)", "ENDONOVO THERAPEUTICS, INC.", False),
])
def test_names_match(a, b, ok):
    assert names_match(a, b) is ok


DAYS = pd.bdate_range("2020-01-01", periods=40)


@pytest.fixture
def world():
    tx = pd.DataFrame([
        # txn, asset, ticker, type, asset_type, trade_i, filed_i
        ("t1", "Danaher Corporation (DHR)", "DHR", "P", "ST", 1, 5),       # Form 4 history -> high
        ("t2", "Barrick Gold Corp (ABX)", "ABX", "P", "ST", 1, 5),          # current map, name differs -> out
        ("t3", "Vanguard Small-Cap ETF (VB)", "VB", "P", "ST", 1, 5),       # not mapped to any company
        ("t4", "Some LLC", None, "P", "OI", 1, 5),                          # not a stock
        ("t5", "Newco Inc (NEW)", "NEW", "P", "ST", 1, 5),                  # current map + name ok -> medium
        ("t6", "Danaher Corporation (DHR)", "DHR", "E", "ST", 1, 5),        # exchange, not P/S
        ("t7", "Laterco (LATE)", "LATE", "P", "ST", 1, 5),                  # prices start after entry
    ], columns=["txn_id", "asset", "ticker", "txn_type", "asset_type", "ti", "fi"])
    tx["trade_date"] = DAYS[tx["ti"]]
    tx["filing_date"] = DAYS[tx["fi"]]
    tx = tx.assign(last="Doe", first="Jane", state_dst="CA01", owner=None).drop(columns=["ti", "fi"])
    filings = pd.DataFrame({"issuer_cik": ["0000000001"] * 3, "issuer_ticker": ["DHR"] * 3,
                            "issuer_name": ["DANAHER CORP /DE/"] * 3,
                            "filed_date": pd.to_datetime(["2019-06-01", "2019-12-01", "2020-03-01"])})
    sec_map = pd.DataFrame({"cik": ["0000000001", "0000000002", "0000000003", "0000000004"],
                            "name": ["Danaher", "Abacus Global Management", "Newco Inc", "Laterco"],
                            "ticker": ["DHR", "ABX", "NEW", "LATE"], "exchange": "NYSE"})
    secs = pd.DataFrame({"cik": ["0000000001"], "ticker": ["DHR"]})
    prices = pd.concat([pd.DataFrame({"ticker": t, "date": DAYS[i0:]}) for t, i0 in
                        [("DHR", 0), ("ABX", 0), ("VB", 0), ("NEW", 0), ("LATE", 20)]], ignore_index=True)
    cal = pd.DataFrame({"date": DAYS})
    return resolve(tx, form4_ticker_history(filings), sec_map, secs, prices, cal, max_gap_days=365,
                   min_history_days=5).set_index("txn_id")


def test_congress_resolution(world):
    r = world
    assert r.loc["t1", "match_confidence"] == "high" and r.loc["t1", "match_method"] == "form4_ticker_history"
    assert r.loc["t1", "security_id"] == "cik:0000000001"
    assert r.loc["t2", "unmatched_reason"] == "name_mismatch"
    assert r.loc["t3", "unmatched_reason"] == "ticker_not_mapped"
    assert r.loc["t4", "unmatched_reason"] == "not_stock_asset_type"
    assert r.loc["t5", "match_confidence"] == "medium"
    assert r.loc["t6", "unmatched_reason"] == "not_purchase_or_sale"
    assert r.loc["t7", "unmatched_reason"] == "entry_before_price_history"


def test_congress_entry_strictly_after_filing(world):
    m = world[world["matched"]]
    assert (m["entry_date"] > m["public_date"]).all()
    assert (m["entry_date"] == DAYS[6]).all()  # filed on day 5 -> enters day 6
