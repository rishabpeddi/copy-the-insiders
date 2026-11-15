"""Security resolution, price adapter reshaping, calendar and T-bill math. No network."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cti.ingest.prices import add_derived, reshape_yfinance
from cti.ingest.raw import save_raw
from cti.ingest.reference import build_calendar, next_trading_day_after, parse_sec_tickers, tbill_daily_returns
from cti.resolve.securities import normalize_ticker, resolve


@pytest.mark.parametrize("raw,expected", [
    ("AAPL", "AAPL"), (" aapl ", "AAPL"), ("NYSE:NYCB", "NYCB"), ("GEF,GEF.B", "GEF"),
    ("(CALX)", "CALX"), ("[ NONE ]", None), ("N/A", None), ("NONE", None), ("BRK.B", "BRK-B"),
    ("BCDA;BCDAW", "BCDA"), ("BBXIA/B", "BBXIA"), (None, None), (float("nan"), None), ("", None),
    ("$TSLA", "TSLA"), ("123", None),
])
def test_normalize_ticker(raw, expected):
    assert normalize_ticker(raw) == expected


def test_calendar_next_trading_day_skips_weekends_and_is_strictly_after():
    cal = build_calendar(pd.to_datetime(["2024-01-05", "2024-01-08", "2024-01-09"]))  # Fri, Mon, Tue
    out = next_trading_day_after(pd.to_datetime(["2024-01-05", "2024-01-06", "2024-01-08", "2024-01-09"]), cal)
    assert list(out[:3].dt.strftime("%m-%d")) == ["01-08", "01-08", "01-09"]
    assert pd.isna(out.iloc[3])  # past the end of the calendar


def test_tbill_uses_previous_rate_and_calendar_days():
    cal = build_calendar(pd.to_datetime(["2024-01-05", "2024-01-08", "2024-01-09"]))
    dtb3 = pd.Series([3.6, 7.2, 99.0], index=pd.to_datetime(["2024-01-05", "2024-01-08", "2024-01-09"]))
    r = tbill_daily_returns(dtb3, cal)
    assert r.iloc[0] == 0.0
    assert r.iloc[1] == pytest.approx(0.036 * 3 / 360)  # Fri rate, 3 calendar days
    assert r.iloc[2] == pytest.approx(0.072 * 1 / 360)  # Mon rate; Tue's rate isn't known yet


def test_reshape_yfinance_and_split_adjustment():
    idx = pd.to_datetime(["2024-06-07", "2024-06-10", "2024-06-11"])
    wide = pd.concat({
        "NVDA": pd.DataFrame({"Open": [119.8, 120.4, 121.8], "High": 1.0, "Low": 1.0,
                              "Close": [120.9, 121.8, 120.9], "Adj Close": [120.5, 121.4, 120.5],
                              "Volume": 1, "Dividends": 0.0, "Stock Splits": [0.0, 10.0, 0.0]}, index=idx),
        "DEAD": pd.DataFrame({"Open": np.nan, "Close": np.nan, "Adj Close": np.nan}, index=idx),
    }, axis=1)
    long = add_derived(reshape_yfinance(wide, ["NVDA", "DEAD"]))
    assert set(long["ticker"]) == {"NVDA"}
    nominal = long.set_index("date")["close_nominal"]
    assert nominal.iloc[0] == pytest.approx(1209.0)   # pre-split quote was 10x
    assert nominal.iloc[1] == pytest.approx(121.8)    # split day is already post-split
    assert long["adj_open"].iloc[0] == pytest.approx(119.8 * 120.5 / 120.9)


def test_parse_sec_tickers_pads_cik():
    raw = b'{"fields":["cik","name","ticker","exchange"],"data":[[320193,"Apple Inc.","AAPL","Nasdaq"]]}'
    df = parse_sec_tickers(raw)
    assert df.loc[0, "cik"] == "0000320193" and df.loc[0, "ticker"] == "AAPL"


def test_raw_snapshots_are_immutable(tmp_path):
    save_raw("x", "a.txt", b"one", tag="20260101", data_dir=tmp_path)
    save_raw("x", "a.txt", b"one", tag="20260101", data_dir=tmp_path)  # identical: fine
    with pytest.raises(RuntimeError, match="immutable"):
        save_raw("x", "a.txt", b"two", tag="20260101", data_dir=tmp_path)


# --- end-to-end resolution on a hand-built world -------------------------------------------------

DAYS = pd.bdate_range("2024-01-01", periods=10)


def _px(ticker, close, split_on=None):
    df = pd.DataFrame({"ticker": ticker, "date": DAYS, "open": close, "high": close, "low": close,
                       "close": close, "adj_close": close, "volume": 1, "dividend": 0.0, "split": 0.0})
    if split_on is not None:
        df.loc[split_on, "split"] = 2.0
    return df


def _cand(txn, cik, ticker, trade_i, public_i, price, name="Co"):
    return {"txn_id": txn, "issuer_cik": cik, "issuer_ticker": ticker, "issuer_name": name,
            "trade_date": DAYS[trade_i], "public_date": DAYS[public_i], "reported_price": price}


@pytest.fixture
def world():
    prices = add_derived(pd.concat([
        _px("SPY", 400.0), _px("AAA", 10.0), _px("BBB", 50.0, split_on=5), _px("CCC", 20.0),
    ], ignore_index=True))
    sec_map = pd.DataFrame({"cik": ["0000000001", "0000000002", "0000000004"],
                            "name": ["A", "B", "D"], "ticker": ["AAA", "BBB", "DDD"],
                            "exchange": ["Nasdaq", "NYSE", "Nasdaq"]})
    cands = pd.DataFrame([
        _cand("t1", "0000000001", "AAA", 1, 2, 10.5),          # cik+filing agree, price within 5%  -> high
        _cand("t2", "0000000002", "BBB", 1, 2, 100.0),         # pre-split: nominal close 100        -> high
        _cand("t3", "0000000003", "CCC", 1, 2, 21.0),          # not in SEC map, filing ticker only   -> medium
        _cand("t4", "0000000003", "CCC", 1, 2, 90.0),          # 4.5x the quote                      -> price_mismatch
        _cand("t5", "0000000004", "DDD", 1, 2, 5.0),           # SEC ticker not priced               -> not in source
        _cand("t6", "0000000005", "NONE", 1, 2, 5.0),          # nothing to go on                    -> no candidates
        _cand("t7", "0000000001", "AAA", 1, 9, 10.0),          # filed on last calendar day          -> after end
        _cand("t8", "0000000003", "CCC", 1, 2, 30.0),          # 1.5x: inside 2x but outside 25%     -> low
    ])
    cal = build_calendar(DAYS)
    return resolve(cands, sec_map, prices, cal, tight_pct=0.25, max_ratio=2.0, min_history_days=5)


def test_resolution_outcomes(world):
    secs, res = world
    r = res.set_index("txn_id")
    assert r.loc["t1", "match_confidence"] == "high" and r.loc["t1", "match_method"] == "cik_and_filing_ticker"
    assert r.loc["t2", "match_confidence"] == "high"
    assert r.loc["t2", "close_nominal_at_trade"] == pytest.approx(100.0)
    assert r.loc["t3", "match_confidence"] == "medium" and r.loc["t3", "match_method"] == "filing_ticker"
    assert r.loc["t8", "match_confidence"] == "low"
    assert r.loc["t4", "unmatched_reason"] == "price_mismatch"
    assert r.loc["t5", "unmatched_reason"] == "ticker_not_in_price_source"
    assert r.loc["t6", "unmatched_reason"] == "no_ticker_candidates"
    assert r.loc["t7", "unmatched_reason"] == "entry_after_calendar_end"
    assert set(secs["security_id"]) == {f"cik:000000000{i}" for i in range(1, 6)}


def test_every_candidate_is_matched_or_has_a_reason(world):
    _, res = world
    assert len(res) == 8
    assert (res["matched"] ^ res["unmatched_reason"].notna()).all()
    assert res.loc[res["matched"], "match_confidence"].notna().all()


def test_entry_is_strictly_after_public_date(world):
    _, res = world
    m = res[res["matched"]]
    assert (pd.to_datetime(m["entry_date"]) > pd.to_datetime(m["public_date"])).all()


def test_one_day_stub_history_does_not_count_as_priced():
    # yfinance returns a single-row stub for many delisted tickers; it must not block the fallback
    # or turn a delisting into a fake "missing price" glitch.
    stub = _px("GONE", 5.0).tail(1)
    prices = add_derived(pd.concat([_px("SPY", 400.0), stub], ignore_index=True))
    sec_map = pd.DataFrame({"cik": ["0000000009"], "name": ["G"], "ticker": ["GONE"], "exchange": ["NYSE"]})
    cands = pd.DataFrame([_cand("s1", "0000000009", "GONE", 1, 2, 5.0)])
    _, res = resolve(cands, sec_map, prices, build_calendar(DAYS), 0.25, 2.0, min_history_days=5)
    assert res.loc[0, "unmatched_reason"] == "ticker_not_in_price_source"


def test_reused_ticker_listed_after_the_trade_is_flagged():
    # "OLD" was a different company's ticker; today's prices for it start after the purchase.
    later = _px("OLD", 10.0).iloc[5:]
    prices = add_derived(pd.concat([_px("SPY", 400.0), later], ignore_index=True))
    sec_map = pd.DataFrame({"cik": ["0000000008"], "name": ["X"], "ticker": ["ZZZ"], "exchange": ["NYSE"]})
    cands = pd.DataFrame([_cand("r1", "0000000008", "OLD", 1, 2, 10.0)])
    _, res = resolve(cands, sec_map, prices, build_calendar(DAYS), 0.25, 2.0, min_history_days=3)
    assert res.loc[0, "unmatched_reason"] == "entry_before_price_history"
