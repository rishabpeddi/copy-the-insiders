"""Portfolios small enough to calculate by hand. Each expected number is worked out in the comments."""

from __future__ import annotations

import pandas as pd
import pytest

from cti.backtest.engine import EngineConfig, run
from helpers import cal, prices, signal, signals

NO_COST = EngineConfig(hold_trading_days=2, cost_bps_per_side=0.0)


def navs(result) -> list[float]:
    return [round(x, 10) for x in result.daily["nav"]]


def test_one_stock():
    # Enter A at d1 open (10). Hold 2 days -> exit at d3 open (12).
    # d1 close 11 -> 1.1; d2 close 12 -> 1.2; d3 open exit 12 -> 1.2 cash.
    px = prices([("A", 1, 10, 11), ("A", 2, 11, 12), ("A", 3, 12, 15), ("A", 4, 15, 15)])
    sig = signals(signal("s1", "buy", "A", "F", 1, 5))
    r = run(sig, px, cal(5), NO_COST)
    assert navs(r) == [1.0, 1.1, 1.2, 1.2, 1.2]
    assert r.positions.loc[0, "exit_reason"] == "hold_limit"
    assert list(r.daily["n_positions"]) == [0, 1, 1, 0, 0]


def test_two_overlapping_rebalance_on_entry():
    # d1: A in at 10, 100% A. d1 close 10 -> 1.0.
    # d2 open: A 10 (value 1.0); B enters; rebalance to 0.5 / 0.5.
    #   A close 12 -> 0.6, B open 20 close 22 -> 0.55. NAV 1.15.
    # d3: A open 12 close 12 -> 0.6; B open 22 close 11 -> 0.275. NAV 0.875.
    cfg = EngineConfig(hold_trading_days=10, cost_bps_per_side=0.0)
    px = prices([("A", 1, 10, 10), ("A", 2, 10, 12), ("A", 3, 12, 12),
                 ("B", 2, 20, 22), ("B", 3, 22, 11)])
    sig = signals(signal("s1", "buy", "A", "F1", 1, 4), signal("s2", "buy", "B", "F2", 2, 4))
    r = run(sig, px, cal(4), cfg)
    assert navs(r) == [1.0, 1.0, 1.15, 0.875]
    assert r.daily.loc[2, "turnover"] == pytest.approx(1.0)  # sell 0.5 A + buy 0.5 B


def test_filer_sale_triggers_exit_only_for_that_filer():
    # A bought by F1 at d1 open 10. F2 (not a source) sells -> ignored. F1's sale enters d3 -> exit d3 open 12.
    # d1 close 10 -> 1.0; d2 close 11 -> 1.1; d3 open 12 -> 1.2 sold.
    cfg = EngineConfig(hold_trading_days=10, cost_bps_per_side=0.0)
    px = prices([("A", 1, 10, 10), ("A", 2, 10, 11), ("A", 3, 12, 13), ("A", 4, 13, 13)])
    sig = signals(signal("b1", "buy", "A", "F1", 1, 5),
                  signal("x2", "sell", "A", "F2", 2, 5),
                  signal("x1", "sell", "A", "F1", 3, 5))
    r = run(sig, px, cal(5), cfg)
    assert navs(r) == [1.0, 1.0, 1.1, 1.2, 1.2]
    assert r.positions.loc[0, "exit_reason"] == "filer_sale"
    assert r.positions.loc[0, "exit_date"] == cal(5)[3]


def test_delisting_applies_delist_return():
    # A at d1 open 10, close 10. d2 open 10 close 8 -> 0.8, then delist return -50% -> 0.4 cash.
    cfg = EngineConfig(hold_trading_days=10, cost_bps_per_side=0.0)
    px = prices([("A", 1, 10, 10), ("A", 2, 10, 8, -0.5), ("B", 3, 1, 1)])
    sig = signals(signal("s1", "buy", "A", "F", 1, 4))
    r = run(sig, px, cal(4), cfg)
    assert navs(r) == [1.0, 1.0, 0.4, 0.4]
    assert r.positions.loc[0, "exit_reason"] == "delist"


def test_missing_delist_return_uses_prereg_no_price_rule():
    # A's prices stop at d2 with no delisting return: the pre-registered no_price rule (-100%) applies.
    cfg = EngineConfig(hold_trading_days=10, cost_bps_per_side=0.0, no_price_delist_return=-1.0)
    px = prices([("A", 1, 10, 10), ("A", 2, 10, 10), ("B", 3, 1, 1)])
    r = run(signals(signal("s1", "buy", "A", "F", 1, 4)), px, cal(4), cfg)
    assert navs(r) == [1.0, 1.0, 0.0, 0.0]


def test_costs_only_flat_prices():
    # 10 bps. d1 open: turnover 1.0, cost 0.001 -> position 0.999.
    # d3 open exit: turnover 0.999, cost 0.000999 -> cash 0.998001.
    cfg = EngineConfig(hold_trading_days=2, cost_bps_per_side=10.0)
    px = prices([("A", d, 10, 10) for d in range(5)])
    r = run(signals(signal("s1", "buy", "A", "F", 1, 5)), px, cal(5), cfg)
    assert navs(r) == [1.0, 0.999, 0.999, 0.998001, 0.998001]
    assert r.daily["cost_paid"].sum() == pytest.approx(0.001999)


def test_cash_accrues_only_when_uninvested():
    # 1% per day on cash. d0 cash -> 1.01. d1 fully invested in flat A -> 1.01. d2 flat -> 1.01.
    # d3 exit at open -> cash 1.01 * 1.01 = 1.0201.
    cfg = EngineConfig(hold_trading_days=2, cost_bps_per_side=0.0)
    px = prices([("A", d, 10, 10) for d in range(4)])
    cash = pd.Series(0.01, index=pd.to_datetime(cal(4)))
    r = run(signals(signal("s1", "buy", "A", "F", 1, 4)), px, cal(4), cfg, cash_returns=cash)
    assert navs(r) == [1.01, 1.01, 1.01, 1.0201]


def test_repeat_buy_does_not_reset_hold_clock():
    # Second buy of A on d2 adds a source; exit still at d1 + 2 = d3.
    px = prices([("A", d, 10, 10) for d in range(5)])
    sig = signals(signal("s1", "buy", "A", "F1", 1, 5), signal("s2", "buy", "A", "F2", 2, 5))
    r = run(sig, px, cal(5), NO_COST)
    assert len(r.positions) == 1
    assert r.positions.loc[0, "exit_date"] == cal(5)[3]
    assert r.positions.loc[0, "source_signal_ids"] == ["s1", "s2"]


def test_entry_without_price_is_skipped_and_logged():
    px = prices([("B", 0, 1, 1), ("B", 2, 1, 1)])
    r = run(signals(signal("s1", "buy", "A", "F", 1, 3)), px, cal(3), NO_COST)
    assert r.skipped_signals.loc[0, "reason"] == "no_price_on_entry"
    assert navs(r) == [1.0, 1.0, 1.0]


def test_gross_return_is_the_stocks_own_return_while_held():
    # A enters d1 at open 10, exits d3 at open 12 -> +20% regardless of portfolio weights.
    px = prices([("A", 1, 10, 11), ("A", 2, 11, 12), ("A", 3, 12, 15), ("A", 4, 15, 15),
                 ("B", 1, 5, 5), ("B", 2, 5, 5), ("B", 3, 5, 5), ("B", 4, 5, 5)])
    sig = signals(signal("s1", "buy", "A", "F", 1, 5), signal("s2", "buy", "B", "G", 2, 5))
    r = run(sig, px, cal(5), NO_COST)
    a = r.positions.set_index("security_id").loc["A"]
    assert a["gross_return"] == pytest.approx(0.2)
