"""Minimum detectable alpha: the smallest annual alpha a test of this length can reliably detect."""

from __future__ import annotations

from statistics import NormalDist


def minimum_detectable_alpha(tracking_error_annual: float, years: float, alpha: float = 0.05,
                             power: float = 0.80, two_sided: bool = True) -> float:
    """MDA = (z_{1-a/2} + z_{power}) * TE / sqrt(years). Assumes roughly i.i.d. active returns,
    so treat it as optimistic when returns are autocorrelated."""
    if years <= 0 or tracking_error_annual < 0:
        raise ValueError("years must be > 0 and tracking error >= 0")
    z = NormalDist().inv_cdf
    z_a = z(1 - alpha / 2) if two_sided else z(1 - alpha)
    return (z_a + z(power)) * tracking_error_annual / years ** 0.5
