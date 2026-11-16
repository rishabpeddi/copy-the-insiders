"""Factor-model alpha, scenario construction, and per-scenario signal filters."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from cti.backtest.runner import Scenario, _filters, scenarios
from cti.config import load_config
from cti.ingest.factors import parse_french_csv
from cti.stats.factor_model import FACTORS, fit, mda


def _factors(n=1500, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2015-01-01", periods=n)
    f = pd.DataFrame(rng.normal(0, 0.008, (n, len(FACTORS))), columns=FACTORS, index=dates)
    f["rf"] = 0.0001
    return f


def test_factor_alpha_and_loadings_are_recovered():
    f = _factors()
    rng = np.random.default_rng(1)
    r = f["rf"] + 0.0002 + 1.2 * f["mkt_rf"] + 0.5 * f["smb"] - 0.3 * f["hml"] + rng.normal(0, 0.004, len(f))
    out = fit(r, f.reset_index(names="date"), reps=500, seed=3)
    assert out.betas["mkt_rf"] == pytest.approx(1.2, abs=0.05)
    assert out.betas["smb"] == pytest.approx(0.5, abs=0.05)
    assert out.ci_low < 0.0002 * 252 < out.ci_high
    assert out.resid_vol_ann == pytest.approx(0.004 * np.sqrt(252), rel=0.1)
    assert mda(out, 4) == pytest.approx((1.959964 + 0.841621) * out.resid_vol_ann / 2, rel=1e-4)


def test_factor_adjustment_shrinks_the_noise_that_spy_comparisons_carry():
    # A small-cap tilt with zero alpha: lots of tracking error vs the market, little residual risk.
    f = _factors(seed=4)
    rng = np.random.default_rng(5)
    r = f["rf"] + 1.0 * f["mkt_rf"] + 0.9 * f["smb"] + rng.normal(0, 0.002, len(f))
    out = fit(r, f.reset_index(names="date"), reps=200)
    te = (r - f["rf"] - f["mkt_rf"]).std() * np.sqrt(252)
    assert out.resid_vol_ann < te / 3


def test_parse_french_csv_handles_prose_around_the_table():
    import io
    import zipfile
    text = ("This file was created by CMPT_ME_BEME_RETS using the 202609 CRSP database.\n\n"
            ",Mkt-RF,SMB,HML,RMW,CMA,RF\n20260929,   -0.21,   -0.03,   -0.50,   -0.26,   -0.43,    0.01\n"
            "20260930,   -0.26,    0.10,   -0.88,   -0.35,    0.19,    0.01\n\nCopyright 2026\n")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("x.csv", text)
    df = parse_french_csv(buf.getvalue())
    assert list(df.columns) == ["date", "mkt_rf", "smb", "hml", "rmw", "cma", "rf"]
    assert len(df) == 2 and df.loc[0, "hml"] == pytest.approx(-0.005)


def test_each_sensitivity_changes_one_thing():
    cfg = load_config()
    ins = {s.name: s for s in scenarios(cfg, "insider")}
    con = {s.name: s for s in scenarios(cfg, "congress")}
    assert "primary" in ins and "10b5_1_footnote_only" in ins and "weighting_amount_mid" not in ins
    assert "confidence_low" in con and "weighting_amount_mid" in con and "10b5_1_footnote_only" not in con
    base = Scenario()
    for s in list(ins.values()) + list(con.values()):
        diffs = [k for k in base.__dataclass_fields__ if k != "name" and getattr(s, k) != getattr(base, k)]
        assert len(diffs) <= 1, (s.name, diffs)


def test_filters_apply_prereg_cutoffs():
    cfg = load_config()
    df = pd.DataFrame({"filing_lag_days": [2, 31, 400, 5], "is_10b5_1": [False, False, False, True],
                       "footnote_mentions_10b5_1": [True, False, False, False]})
    primary, d = _filters(df, cfg, "insider", Scenario())
    assert len(primary) == 1 and d["filing_lag"] == 2 and d["10b5_1"] == 1   # row 0 kept: checkbox says no
    foot, _ = _filters(df, cfg, "insider", Scenario(tenb51="footnote_only"))
    assert len(foot) == 1 and foot.index[0] == 3                              # footnote-only flips which is out
    nolag, _ = _filters(df, cfg, "insider", Scenario(filing_lag="none"))
    assert len(nolag) == 3
    c = pd.DataFrame({"filing_lag_days": [10, 120], "match_confidence": ["low", "high"]})
    assert len(_filters(c, cfg, "congress", Scenario())[0]) == 0               # low dropped, >90 days dropped
    assert len(_filters(c, cfg, "congress", Scenario(min_confidence="low", filing_lag="none"))[0]) == 2


def test_survivorship_bound_groups_repeat_buys_into_issuer_episodes():
    from cti.backtest.runner import _synthetic
    cfg = load_config()
    cal = list(pd.bdate_range("2020-01-01", periods=300))
    um = pd.DataFrame({"signal_id": ["a", "b", "c", "d"], "issuer_key": ["X", "X", "X", "Y"],
                       "filer_id": ["F1", "F2", "F3", "F4"], "entry_date": [cal[10], cal[12], cal[200], cal[10]],
                       "public_date": [cal[9], cal[11], cal[199], cal[9]], "filing_lag_days": 1,
                       "is_10b5_1": False, "footnote_mentions_10b5_1": False})
    inp = {"group": "insider", "calendar": cal, "unmatched": um, "pass_rate": {2020: 1.0},
           "spy": pd.Series(0.001, index=pd.DatetimeIndex(cal))}
    sig, px = _synthetic(inp, cfg, Scenario(bound="minus_100"), hold=126)
    # X: a and b share one episode (within 126 days); c starts a new one. Y is its own episode.
    assert sig["security_id"].nunique() == 3
    assert sig.loc[sig["signal_id"] == "synthetic:a", "security_id"].iloc[0] == \
        sig.loc[sig["signal_id"] == "synthetic:b", "security_id"].iloc[0]
    first = px[px["security_id"] == sig["security_id"].iloc[0]]
    assert first["delist_return"].min() == -1.0 and len(first) == 127
