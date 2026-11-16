"""Factor-adjusted alpha: OLS of strategy excess returns on FF5 + momentum, with a block-bootstrap CI.

The bootstrap resamples contiguous blocks of days (returns and factors together) and re-fits the
regression each time, so the CI reflects autocorrelation and the factor loadings' uncertainty.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from cti.stats.bootstrap import TRADING_DAYS
from cti.stats.power import minimum_detectable_alpha

FACTORS = ["mkt_rf", "smb", "hml", "rmw", "cma", "mom"]


@dataclass
class FactorFit:
    alpha_ann: float
    ci_low: float
    ci_high: float
    resid_vol_ann: float
    r2: float
    betas: dict
    n_days: int


def _ols(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    return np.linalg.lstsq(X, y, rcond=None)[0]


def fit(strategy_returns: pd.Series, factors: pd.DataFrame, block_months: int = 6, reps: int = 10_000,
        alpha: float = 0.05, seed: int = 0) -> FactorFit:
    f = factors.set_index("date") if "date" in factors.columns else factors
    df = pd.concat([strategy_returns.rename("r"), f[FACTORS + ["rf"]]], axis=1, join="inner").dropna()
    if len(df) < 60:
        raise ValueError(f"only {len(df)} days overlap with factor data")
    y = (df["r"] - df["rf"]).to_numpy()
    X = np.column_stack([np.ones(len(df)), df[FACTORS].to_numpy()])
    b = _ols(y, X)
    resid = y - X @ b
    r2 = 1 - resid.var() / y.var()

    n = len(y)
    block = max(1, min(n, block_months * 21))
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(n / block))
    alphas = np.empty(reps)
    for k in range(reps):
        starts = rng.integers(0, n - block + 1, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n]
        alphas[k] = _ols(y[idx], X[idx])[0]
    lo, hi = np.quantile(alphas * TRADING_DAYS, [alpha / 2, 1 - alpha / 2])
    return FactorFit(alpha_ann=float(b[0] * TRADING_DAYS), ci_low=float(lo), ci_high=float(hi),
                     resid_vol_ann=float(resid.std(ddof=X.shape[1]) * np.sqrt(TRADING_DAYS)), r2=float(r2),
                     betas={k: float(v) for k, v in zip(FACTORS, b[1:], strict=True)}, n_days=n)


def mda(fit_: FactorFit, years: float, alpha: float = 0.05) -> float:
    """Minimum detectable factor alpha over `years`, from the residual volatility."""
    return minimum_detectable_alpha(fit_.resid_vol_ann, years, alpha=alpha)
