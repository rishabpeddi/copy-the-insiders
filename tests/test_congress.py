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


def test_one_price_ticker_per_company_and_no_fund_families():
    tx = pd.DataFrame([
        ("b1", "Barclays PLC ADR (BCS)", "BCS"), ("b2", "Barclays PLC Ordinary (BCLYF)", "BCLYF"),
        ("e1", "ProShares UltraShort Yen (YCS)", "YCS"),
    ], columns=["txn_id", "asset", "ticker"]).assign(txn_type="P", asset_type="ST", last="Doe", first="J",
                                                     state_dst="CA01", owner=None)
    tx["trade_date"], tx["filing_date"] = DAYS[1], DAYS[5]
    sec_map = pd.DataFrame({"cik": ["0000312069", "0000312069"] + ["0001415311"] * 5,
                            "name": ["Barclays PLC"] * 2 + ["ProShares Trust II"] * 5,
                            "ticker": ["BCS", "BCLYF", "YCS", "EUO", "UCO", "SCO", "UVXY"], "exchange": "NYSE"})
    prices = pd.concat([pd.DataFrame({"ticker": t, "date": DAYS}) for t in ["BCS", "BCLYF", "YCS", "EUO"]])
    r = resolve(tx, form4_ticker_history(pd.DataFrame(columns=["issuer_cik", "issuer_ticker", "issuer_name",
                                                               "filed_date"])),
                sec_map, pd.DataFrame(columns=["cik", "ticker"]), prices, pd.DataFrame({"date": DAYS}),
                min_history_days=5).set_index("txn_id")
    assert r.loc["b1", "ticker"] == r.loc["b2", "ticker"] == "BCS"   # both trades priced with ONE series
    assert r.loc["e1", "unmatched_reason"] == "ticker_not_mapped"     # fund-family CIK not used


SENATE_PTR = """<html><body><table class="table">
<thead><tr><th>#</th><th>Transaction Date</th><th>Owner</th><th>Ticker</th><th>Asset Name</th>
<th>Asset Type</th><th>Type</th><th>Amount</th><th>Comment</th></tr></thead>
<tbody>
<tr><td>1</td><td>10/30/2026</td><td>Joint</td><td>--</td><td>Illinois St GO Bond Rate/Coupon: 5.0%</td>
    <td>Municipal Security</td><td>Purchase</td><td>$1,001 - $15,000</td><td>--</td></tr>
<tr><td>2</td><td>10/06/2026</td><td>Spouse</td><td><a href="https://finance.yahoo.com/q?s=DHR">DHR</a></td>
    <td>Danaher Corporation</td><td>Stock</td><td>Sale (Partial)</td><td>$50,001 - $100,000</td><td>--</td></tr>
<tr><td>3</td><td>10/07/2026</td><td>Self</td><td>--</td><td>WBD</td><td>Stock</td><td>Purchase</td>
    <td>Over $50,000,000</td><td>--</td></tr>
</tbody></table></body></html>"""


def test_senate_ptr_table():
    from cti.ingest.congress_senate import parse_ptr_html

    rows = parse_ptr_html(SENATE_PTR)
    assert [(r["ticker"], r["asset_type"], r["txn_type"]) for r in rows] == [
        (None, "GS", "P"), ("DHR", "ST", "S"), ("WBD", "ST", "P")]   # WBD: ticker given in the asset-name column
    assert rows[1]["partial"] is True and rows[1]["owner"] == "Spouse"
    assert (rows[1]["amount_low"], rows[1]["amount_high"]) == (50_001, 100_000)
    assert (rows[2]["amount_low"], rows[2]["amount_high"]) == (50_000_001, None)
    assert rows[0]["trade_date"] == pd.Timestamp("2026-10-30")


def test_senate_index_rows_and_paper():
    from cti.ingest.congress_senate import parse_index_rows

    idx = parse_index_rows([
        ["Rafael E", "Cruz", "Cruz, Ted (Senator)",
         '<a href="/search/view/ptr/f0f7eba0-ca09-4b80-a97b-64b6dafb835e/" target="_blank">'
         'Periodic Transaction Report for 11/18/2026</a>', "11/18/2026"],
        ["Jane", "Doe", "Doe, Jane (Senator)",
         '<a href="/search/view/paper/0a1b2c3d-0000-0000-0000-000000000000/" target="_blank">'
         'Periodic Transaction Report Amendment</a>', "01/05/2015"]])
    assert list(idx["electronic"]) == [True, False] and list(idx["amendment"]) == [False, True]
    assert idx.loc[0, "doc_id"] == "f0f7eba0-ca09-4b80-a97b-64b6dafb835e"
    assert idx.loc[1, "filing_date"] == pd.Timestamp("2015-01-05")


def test_senate_filer_ids_are_kept_apart_from_house():
    tx = pd.DataFrame([("h1", "house", "CA01"), ("s1", "senate", "")], columns=["txn_id", "chamber", "state_dst"])
    tx = tx.assign(asset="Danaher Corporation (DHR)", ticker="DHR", txn_type="P", asset_type="ST", last="Doe",
                   first="Jane", owner=None, trade_date=DAYS[1], filing_date=DAYS[5])
    hist = form4_ticker_history(pd.DataFrame({"issuer_cik": ["0000000001"], "issuer_ticker": ["DHR"],
                                              "issuer_name": ["DANAHER CORP"], "filed_date": [DAYS[0]]}))
    r = resolve(tx, hist, pd.DataFrame({"cik": ["0000000001"], "name": ["Danaher"], "ticker": ["DHR"],
                                        "exchange": "NYSE"}),
                pd.DataFrame({"cik": ["0000000001"], "ticker": ["DHR"]}),
                pd.DataFrame({"ticker": "DHR", "date": DAYS}), pd.DataFrame({"date": DAYS}),
                min_history_days=5).set_index("txn_id")
    assert r.loc["h1", "filer_id"] == "house:DOE:JANE:CA01" and r.loc["s1", "filer_id"] == "senate:DOE:JANE:"
    assert r["matched"].all()


def test_senate_amendment_dedup_keeps_same_report_repeats():
    from cti.ingest.congress_senate import dedupe_amendments

    base = dict(last="Doe", first="Jane", owner="Self", trade_date=DAYS[1], txn_type="P", amount_low=1001,
                ticker="DHR", asset="Danaher")
    tx = pd.DataFrame([{**base, "doc_id": "orig", "filing_date": DAYS[5]},
                       {**base, "doc_id": "orig", "filing_date": DAYS[5]},          # second lot, same report: real
                       {**base, "doc_id": "amend", "filing_date": DAYS[9]},         # repeated in the amendment
                       {**base, "doc_id": "amend", "filing_date": DAYS[9], "owner": "Spouse"}])  # new in amendment
    out = dedupe_amendments(tx)
    assert list(out["doc_id"]) == ["orig", "orig", "amend"] and out.attrs["dropped"] == 1
