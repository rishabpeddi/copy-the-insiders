"""Benchmarks: SPY total return, and a monthly sector-matched ETF clone.

The clone answers "was the strategy just a sector bet?": at each month start it holds sector
ETFs in the same weights as the strategy's holdings (by sector) on the prior trading day, with
any cash weight in T-bills.
"""

from __future__ import annotations

import pandas as pd


def buy_and_hold_nav(total_returns: pd.Series, start_nav: float = 1.0) -> pd.Series:
    """NAV from daily total returns (index = date)."""
    return start_nav * (1.0 + total_returns.fillna(0.0)).cumprod()


def sector_clone_nav(strategy_sector_weights: pd.DataFrame, etf_returns: pd.DataFrame,
                     cash_returns: pd.Series, start_nav: float = 1.0) -> pd.Series:
    """
    strategy_sector_weights: index=date, columns=sector ETF tickers, values = weight of NAV held in
        that sector at the close of that date (rows need not sum to 1; the rest is cash).
    etf_returns: index=date, columns=same tickers, daily total returns.
    Weights are reset on the first trading day of each month using the PREVIOUS day's weights,
    then drift with returns until the next reset.
    """
    dates = etf_returns.index
    w_prev = strategy_sector_weights.reindex(dates).ffill().shift(1).fillna(0.0)
    month = pd.Series(pd.DatetimeIndex(dates).to_period("M"), index=dates)
    is_reset = month.ne(month.shift(1))

    nav = start_nav
    holdings = pd.Series(0.0, index=etf_returns.columns)
    cash = start_nav
    out = []
    for d in dates:
        if is_reset[d]:
            target = w_prev.loc[d].reindex(etf_returns.columns).fillna(0.0)
            holdings = target * nav
            cash = nav - holdings.sum()
        holdings = holdings * (1.0 + etf_returns.loc[d].fillna(0.0))
        cash = cash * (1.0 + float(cash_returns.get(d, 0.0)))
        nav = holdings.sum() + cash
        out.append(nav)
    return pd.Series(out, index=dates, name="clone_nav")
