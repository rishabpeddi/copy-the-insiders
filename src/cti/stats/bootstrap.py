"""Moving-block bootstrap CI for annualized alpha (mean active return).

Daily active returns are resampled in contiguous blocks of `block_months` (~21 trading days per
month) so autocorrelation and volatility clustering within a block are preserved.
"""

from __future__ import annotations

import numpy as np

TRADING_DAYS = 252


def block_bootstrap_ci(active_daily: np.ndarray, block_months: int = 6, reps: int = 10_000,
                       alpha: float = 0.05, seed: int = 0) -> tuple[float, float, float]:
    """Return (point, ci_low, ci_high) for annualized mean active return."""
    x = np.asarray(active_daily, dtype=float)
    x = x[~np.isnan(x)]
    n = len(x)
    block = max(1, min(n, block_months * 21))
    if n < 2:
        raise ValueError("need at least 2 observations")
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    starts = rng.integers(0, n - block + 1, size=(reps, n_blocks))
    idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(reps, -1)[:, :n]
    means = x[idx].mean(axis=1) * TRADING_DAYS
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(x.mean() * TRADING_DAYS), float(lo), float(hi)
