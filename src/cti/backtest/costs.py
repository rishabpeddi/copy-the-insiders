"""Transaction costs: a flat rate in basis points per side, charged on traded value."""

from __future__ import annotations


def cost_rate(bps_per_side: float) -> float:
    return bps_per_side / 10_000.0


def trade_cost(turnover: float, bps_per_side: float) -> float:
    """Cost of trading `turnover` dollars (sum of |buys| + |sells|)."""
    if turnover < 0:
        raise ValueError("turnover must be non-negative")
    return turnover * cost_rate(bps_per_side)
