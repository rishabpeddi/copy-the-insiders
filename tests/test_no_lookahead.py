"""Look-ahead checks: the engine must never use information from the future."""

from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd
import pytest

from cti.backtest.engine import EngineConfig, LookAheadError, run
from helpers import cal


def random_world(seed: int, n_days: int = 60, n_secs: int = 8):
    rng = np.random.default_rng(seed)
    days = cal(n_days)
    rows = []
    for k in range(n_secs):
        close = 50.0
        for d in days:
            o = close * np.exp(rng.normal(0, 0.01))
            close = o * np.exp(rng.normal(0, 0.02))
            rows.append({"security_id": f"S{k}", "date": d, "open": o, "close": close,
                         "delist_return": None})
    sigs = []
    for j in range(25):
        e = int(rng.integers(1, n_days))
        sigs.append({"signal_id": f"g{j}", "side": "buy" if rng.random() < 0.8 else "sell",
                     "security_id": f"S{int(rng.integers(n_secs))}", "filer_id": f"F{int(rng.integers(5))}",
                     "public_date": days[e] - dt.timedelta(days=1), "entry_date": days[e]})
    return days, pd.DataFrame(rows), pd.DataFrame(sigs)


@pytest.mark.parametrize("seed", range(20))
def test_scrambling_future_prices_never_changes_the_past(seed):
    days, px, sig = random_world(seed)
    cfg = EngineConfig(hold_trading_days=7, cost_bps_per_side=10.0)
    base = run(sig, px, days, cfg).daily

    cut = days[len(days) // 2]
    rng = np.random.default_rng(seed + 1000)
    future = px["date"] > cut
    shuffled = px.copy()
    shuffled.loc[future, "open"] = rng.permutation(shuffled.loc[future, "open"].to_numpy())
    shuffled.loc[future, "close"] = shuffled.loc[future, "open"] * rng.uniform(0.5, 1.5, future.sum())
    after = run(sig, shuffled, days, cfg).daily

    past = base["date"] <= cut
    pd.testing.assert_frame_equal(base[past], after[past])
    assert not base[~past]["nav"].equals(after[~past]["nav"])  # sanity: the change did matter


def test_dropping_future_signals_never_changes_the_past():
    days, px, sig = random_world(7)
    cfg = EngineConfig(hold_trading_days=7)
    cut = days[30]
    base = run(sig, px, days, cfg).daily
    trimmed = run(sig[pd.to_datetime(sig["entry_date"]).dt.date <= cut], px, days, cfg).daily
    pd.testing.assert_frame_equal(base[base["date"] <= cut], trimmed[trimmed["date"] <= cut])


@pytest.mark.parametrize("lag_days", [0, -1])
def test_entry_on_or_before_public_date_is_rejected(lag_days):
    d = cal(3)
    sig = pd.DataFrame([{"signal_id": "bad", "side": "buy", "security_id": "A", "filer_id": "F",
                         "public_date": d[1], "entry_date": d[1] + dt.timedelta(days=lag_days)}])
    px = pd.DataFrame([{"security_id": "A", "date": x, "open": 1.0, "close": 1.0} for x in d])
    with pytest.raises(LookAheadError):
        run(sig, px, d, EngineConfig())


@pytest.mark.parametrize("seed", range(10))
def test_monthly_drift_scrambling_future_prices_never_changes_the_past(seed):
    days, px, sig = random_world(seed, n_days=90)
    cfg = EngineConfig(hold_trading_days=7, cost_bps_per_side=10.0, rebalance="monthly_drift")
    base = run(sig, px, days, cfg).daily
    cut = days[45]
    future = px["date"] > cut
    shuffled = px.copy()
    rng = np.random.default_rng(seed)
    shuffled.loc[future, "close"] = shuffled.loc[future, "close"] * rng.uniform(0.5, 1.5, future.sum())
    after = run(sig, shuffled, days, cfg).daily
    pd.testing.assert_frame_equal(base[base["date"] <= cut], after[after["date"] <= cut])
