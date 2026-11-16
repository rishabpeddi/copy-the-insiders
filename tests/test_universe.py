"""Universe filter + signals SQL (40_signals_insider) on a tiny hand-built warehouse."""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from cti.build import build_marts
from cti.config import load_config

DAYS = pd.bdate_range("2024-01-01", periods=30)


@pytest.fixture
def wh(tmp_path):
    cfg = load_config()
    con = duckdb.connect(str(tmp_path / "warehouse.duckdb"))
    cal = pd.DataFrame({"date": DAYS})
    sr = pd.DataFrame([
        # txn, security, ticker, public_i, entry_i
        ("ok", "cik:0000000001", "AAA", 20, 21),
        ("cheap", "cik:0000000002", "BBB", 20, 21),
        ("small", "cik:0000000003", "CCC", 20, 21),
        ("noshares", "cik:0000000004", "DDD", 20, 21),   # only share count is too recent to be public
        ("otc", "cik:0000000005", "EEE", 20, 21),
        ("jump", "cik:0000000006", "FFF", 20, 21),        # price jumps to $50 ON entry day; prior close $4
    ], columns=["txn_id", "security_id", "ticker", "pi", "ei"])
    sr["public_date"] = DAYS[sr["pi"]]
    sr["entry_date"] = DAYS[sr["ei"]]
    sr["issuer_cik"] = sr["security_id"].str.replace("cik:", "")
    sr["matched"] = True
    sr["match_confidence"] = "high"
    sr["issuer_name"] = sr["ticker"]
    sr = sr.drop(columns=["pi", "ei"])
    secs = pd.DataFrame({"security_id": sr["security_id"], "ticker": sr["ticker"],
                         "exchange": ["NYSE", "Nasdaq", "NYSE", "NYSE", "OTC", "NYSE"]})
    px_rows = []
    for t, close in [("AAA", 20.0), ("BBB", 3.0), ("CCC", 20.0), ("DDD", 20.0), ("EEE", 20.0), ("FFF", 4.0)]:
        for i, d in enumerate(DAYS):
            c = 50.0 if (t == "FFF" and i >= 21) else close
            px_rows.append({"ticker": t, "date": d, "close_nominal": c})
    prices = pd.DataFrame(px_rows)
    cands = sr[["txn_id"]].assign(filer_id="F1", value_point=50_000.0)
    shares = pd.DataFrame([
        ("0000000001", DAYS[0], 100e6, "cover"),    # $20 x 100M = $2B
        ("0000000002", DAYS[0], 500e6, "cover"),
        ("0000000003", DAYS[0], 1e6, "cover"),      # $20M
        ("0000000004", DAYS[19], 100e6, "cover"),   # dated 2 days before entry: not public yet (14-day lag)
        ("0000000005", DAYS[0], 100e6, "cover"),
        ("0000000006", DAYS[0], 100e6, "cover"),    # $4 x 100M = $400M, but price filter fails first
    ], columns=["cik", "end", "shares", "kind"]).assign(accn="x")
    (tmp_path / "staging").mkdir()
    shares.to_parquet(tmp_path / "staging" / "sec_shares.parquet", index=False)
    txns = pd.DataFrame([{"txn_id": "s1", "code": "S", "issuer_cik": "0000000001", "filer_id": "F1",
                          "filed_date": DAYS[25].date()}])
    for name, df in {"calendar": cal, "signal_resolution": sr, "securities": secs, "prices_daily": prices,
                     "signals_insider_candidates": cands, "core_transactions": txns}.items():
        con.register("_d", df)
        con.execute(f"CREATE TABLE {name} AS SELECT * FROM _d")
        con.unregister("_d")
    con.close()
    build_marts(cfg, data_dir=tmp_path)
    con = duckdb.connect(str(tmp_path / "warehouse.duckdb"), read_only=True)
    yield con
    con.close()


def test_universe_reasons(wh):
    got = dict(wh.execute("SELECT txn_id, coalesce(universe_reason, 'PASS') FROM signals_insider_all").fetchall())
    assert got == {"ok": "PASS", "cheap": "price_below_min", "small": "mcap_below_min",
                   "noshares": "mcap_unknown", "otc": "exchange_not_allowed", "jump": "price_below_min"}


def test_price_filter_uses_close_before_entry_not_entry_day(wh):
    # FFF closes at $50 on the entry day itself; the filter must only see the prior $4 close.
    row = wh.execute("SELECT prior_close, prior_close_date FROM signals_insider_all WHERE txn_id='jump'").fetchone()
    assert row[0] == 4.0 and pd.Timestamp(row[1]) == DAYS[20]


def test_only_passing_buys_and_matching_sells(wh):
    assert wh.execute("SELECT signal_id FROM signals_insider").fetchall() == [("ok",)]
    sells = wh.execute("SELECT signal_id, security_id, entry_date FROM signals_insider_sells").fetchall()
    assert len(sells) == 1 and sells[0][1] == "cik:0000000001" and pd.Timestamp(sells[0][2]) == DAYS[26]
