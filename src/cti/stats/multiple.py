"""Holm step-down adjustment for multiple hypotheses."""

from __future__ import annotations

import numpy as np


def holm(pvalues) -> np.ndarray:
    """Holm-adjusted p-values, in the original order."""
    p = np.asarray(pvalues, dtype=float)
    m = len(p)
    order = np.argsort(p)
    adj = np.empty(m)
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (m - rank) * p[idx])
        adj[idx] = min(1.0, running)
    return adj


def holm_alpha(alpha: float, m: int) -> list[float]:
    """Per-step thresholds alpha/m, alpha/(m-1), ..., alpha. With m=2 groups the strictest is alpha/2,
    which is what the adjusted (1 - alpha/2) confidence interval for the decision rule uses."""
    return [alpha / (m - k) for k in range(m)]
