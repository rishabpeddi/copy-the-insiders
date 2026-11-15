"""Form 4 staging and SQL models on a tiny hand-built SEC-format zip (no network)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import duckdb
import pytest

from cti.build import build
from cti.config import load_config
from cti.ingest.sec_form4 import parse_sec_date, quarters, stage

SUBMISSION = """ACCESSION_NUMBER\tFILING_DATE\tPERIOD_OF_REPORT\tDOCUMENT_TYPE\tISSUERCIK\tISSUERNAME\tISSUERTRADINGSYMBOL
0001-20-000001\t05-FEB-2020\t03-FEB-2020\t4\t111\tAcme Corp\tacme
0001-20-000002\t10-FEB-2020\t03-FEB-2020\t4/A\t111\tAcme Corp\tACME
0001-20-000003\t06-FEB-2020\t04-FEB-2020\t4\t111\tAcme Corp\tACME
0001-20-000004\t07-FEB-2020\t05-FEB-2020\t4\t222\tBeta Inc\tBETA
0001-20-000005\t07-FEB-2020\t05-FEB-2020\t3\t222\tBeta Inc\tBETA
0001-20-000006\t07-FEB-2020\t05-FEB-2020\t4\t111\tAcme Corp\tACME
"""
OWNERS = """ACCESSION_NUMBER\tRPTOWNERCIK\tRPTOWNERNAME\tRPTOWNER_RELATIONSHIP\tRPTOWNER_TITLE
0001-20-000001\t9001\tJane CEO\tDirector,Officer\tCEO
0001-20-000002\t9001\tJane CEO\tDirector,Officer\tCEO
0001-20-000003\t9002\tBig Holder\tTenPercentOwner\t
0001-20-000004\t9003\tBob Director\tDirector\t
0001-20-000006\t9004\tPat CFO\tOfficer\tCFO
"""
TRANS = """ACCESSION_NUMBER\tNONDERIV_TRANS_SK\tSECURITY_TITLE\tTRANS_DATE\tTRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tTRANS_ACQUIRED_DISP_CD
0001-20-000001\t1\tCommon\t03-FEB-2020\tP\t1000\t20\tA
0001-20-000002\t1\tCommon\t03-FEB-2020\tP\t1000\t20\tA
0001-20-000003\t1\tCommon\t04-FEB-2020\tP\t5000\t20\tA
0001-20-000004\t1\tCommon\t05-FEB-2020\tP\t100\t50\tA
0001-20-000006\t1\tDepositary Shares for Series B Preferred Stock\t05-FEB-2020\tP\t5000\t25\tA
"""
FOOTNOTES = """ACCESSION_NUMBER\tFOOTNOTE_ID\tFOOTNOTE_TXT
0001-20-000004\tF1\tPurchased under a Rule 10b5-1 trading plan adopted 2019.
"""


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    raw = tmp_path / "raw" / "form4"
    raw.mkdir(parents=True)
    z = raw / "2020q1_form345.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("SUBMISSION.tsv", SUBMISSION)
        zf.writestr("REPORTINGOWNER.tsv", OWNERS)
        zf.writestr("NONDERIV_TRANS.tsv", TRANS)
        zf.writestr("FOOTNOTES.tsv", FOOTNOTES)
    counts = stage(z, data_dir=tmp_path)
    assert counts == {"SUBMISSION": 6, "REPORTINGOWNER": 5, "NONDERIV_TRANS": 5, "FOOTNOTES": 1}
    build(load_config(), data_dir=tmp_path)
    return tmp_path


def q(data_dir: Path, sql: str):
    con = duckdb.connect(str(data_dir / "warehouse.duckdb"), read_only=True)
    try:
        return con.execute(sql).fetchall()
    finally:
        con.close()


def test_quarters():
    assert list(quarters("2019Q3", "2020Q2")) == ["2019q3", "2019q4", "2020q1", "2020q2"]


def test_parse_sec_date():
    import pandas as pd
    out = parse_sec_date(pd.Series(["31-MAR-2023", "2023-03-31", "junk"]))
    assert str(out[0].date()) == "2023-03-31" and str(out[1].date()) == "2023-03-31" and pd.isna(out[2])


def test_core_filings_keeps_form4_only_and_flags_amendments(data_dir):
    rows = q(data_dir, "SELECT filing_id, is_amendment, issuer_ticker FROM core_filings ORDER BY 1")
    assert [r[0][-1] for r in rows] == ["1", "2", "3", "4", "6"]  # the Form 3 is dropped
    assert rows[1][1] is True and rows[0][2] == "ACME"


def test_amendment_duplicate_keeps_earliest_public_filing(data_dir):
    kept = q(data_dir, "SELECT filing_id, filed_date FROM core_transactions WHERE filer_id = '9001'")
    assert len(kept) == 1 and kept[0][0] == "0001-20-000001"
    dropped = q(data_dir, "SELECT filing_id, drop_reason FROM core_transactions_dropped")
    assert dropped == [("0001-20-000002", "duplicate_of_earlier_filing")]


def test_insider_signal_rules_come_from_prereg(data_dir):
    rows = q(data_dir, "SELECT filer_id FROM signals_insider_candidates")
    # 9001: officer buy $20k -> kept. 9002: 10% owner, not officer/director -> out.
    # 9003: director but $5k < $10k minimum AND 10b5-1 footnote -> out.
    # 9004: officer, $125k, but buying preferred depositary shares -> out by security_title rule.
    assert rows == [("9001",)]
    m = q(data_dir, "SELECT is_10b5_1_method FROM core_transactions WHERE filer_id = '9003'")
    assert m == [("footnote",)]
