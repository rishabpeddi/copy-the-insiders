import numpy as np
import pytest

from cti.stats.bootstrap import block_bootstrap_ci
from cti.stats.multiple import holm
from cti.stats.power import minimum_detectable_alpha


def test_holm_matches_textbook_example():
    # p = [0.01, 0.04, 0.03] -> sorted 0.01*3=0.03, 0.03*2=0.06, max(0.06, 0.04*1)=0.06
    assert np.allclose(holm([0.01, 0.04, 0.03]), [0.03, 0.06, 0.06])


def test_mda_scales_with_root_years():
    a = minimum_detectable_alpha(0.10, 4)
    b = minimum_detectable_alpha(0.10, 16)
    assert a == pytest.approx(2 * b)
    assert a == pytest.approx((1.959964 + 0.841621) * 0.10 / 2, rel=1e-5)


def test_bootstrap_ci_covers_true_mean_and_is_reproducible():
    rng = np.random.default_rng(1)
    x = rng.normal(0.0004, 0.01, 1000)  # ~10%/yr alpha
    r1 = block_bootstrap_ci(x, reps=2000, seed=5)
    r2 = block_bootstrap_ci(x, reps=2000, seed=5)
    assert r1 == r2
    point, lo, hi = r1
    assert lo < point < hi
