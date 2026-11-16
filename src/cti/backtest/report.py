"""Write reports/dev_results/SUMMARY[_congress].md from the scenario metrics.json files."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from statistics import NormalDist

from cti.config import REPORTS_DIR, Config

TITLES = {"insider": "insider purchases", "congress": "House member purchases"}


def _pct(x, signed: bool = True) -> str:
    if x is None:
        return "n/a"
    return f"{x:+.2%}" if signed else f"{x:.2%}"


def _ci(m: dict, k: str, lo: str, hi: str) -> str:
    if m.get(k) is None:
        return "n/a"
    return f"{_pct(m[k])} [{_pct(m[lo])}, {_pct(m[hi])}]"


def write_dev_report(cfg: Config, reports_dir: Path = REPORTS_DIR, group: str = "insider") -> Path:
    root = reports_dir / "dev_results"
    ms = {}
    for p in sorted(root.glob(f"{group}_*/metrics.json")):
        m = json.loads(p.read_text())
        if "scenario_spec" in m:  # skip results from the earlier, pre-changelog runner
            ms[m["scenario"]] = m
    if "primary" not in ms:
        raise FileNotFoundError(f"No primary dev result for {group}. Run `cti run --period dev --group {group}`.")
    base = ms["primary"]
    order = ["primary"] + sorted(k for k in ms if k != "primary")

    rows = []
    for k in order:
        m = ms[k]
        f = m["signal_filters"]
        syn = f" + {f['synthetic_unmatched']:,} synthetic" if f.get("synthetic_unmatched") else ""
        rows.append(
            f"| {k} | {m['cagr']:.2%} | {m['spy_cagr']:.2%} | {_ci(m, 'ff_alpha_ann', 'ff_ci_low', 'ff_ci_high')} | "
            f"{_ci(m, 'active_return_ann', 'active_ci_low', 'active_ci_high')} | "
            f"{_ci(m, 'active_vs_clone_ann', 'clone_ci_low', 'clone_ci_high')} | "
            f"{m['turnover_per_year']:.1f}x | {m['costs_per_year']:.2%} | {f['kept']:,}{syn} |")

    alpha = float(cfg["inference"]["alpha"])
    z = NormalDist().inv_cdf(1 - alpha / 2)
    rv, ty = base.get("ff_resid_vol_ann"), base["test_years"]
    half = z * rv / ty ** 0.5 if rv else None
    f = base["signal_filters"]
    drops = ", ".join(f"{k.replace('_', ' ')}: {v:,}" for k, v in f.items() if k not in ("kept", "before"))
    betas = ", ".join(f"{k} {v:+.2f}" for k, v in (base.get("ff_betas") or {}).items())
    ex = base["exit_reasons"]
    t51 = base.get("tenb51_counts")
    t51_txt = ""
    if t51:
        t51_txt = ("\n## 10b5-1 classification (universe-passing purchases in this period)\n"
                   + "\n".join(f"- {k.replace('_', ' ')}: {v:,}" for k, v in t51.items())
                   + "\n\nThe primary rule uses the SEC checkbox where it exists (April 2023 onward) and footnote "
                     "text before that. The `10b5_1_footnote_only` run uses footnote text in every period.\n")

    md = f"""# Dev-period results: {TITLES[group]} (generated)

Generated {dt.datetime.now():%Y-%m-%d %H:%M}. Period: dev, from {base['start']} ({base['years']} years).
Prices: {cfg['data']['price_source']} (survivors only; see the data-quality reports and the survivorship
bounds below). prereg sha256 `{base['prereg_sha256'][:12]}` (not tagged).

**Development period only. Rules were fixed for reasons other than these returns (see the PREREG.md
changelog), and these numbers say nothing yet about the test period.**

## Results
Primary metric: **Fama-French 5-factor + momentum alpha** (annualized, 95% block-bootstrap CI).
"vs SPY" is the descriptive headline; "vs sector clone" is a secondary benchmark. CIs are not yet
Holm-adjusted across the two groups.

| scenario | CAGR | SPY CAGR | FF5+Mom alpha | vs SPY | vs sector clone | turnover | costs/yr | signals |
|---|---:|---:|---|---|---|---:|---:|---:|
{chr(10).join(rows)}

Each sensitivity run changes one thing from `primary`. `bound_*` runs add a sample of unmatched
purchases (no price data, mostly delisted companies), priced at -100% / 0% / SPY over the hold.

## Power: what the test can and cannot show
- Factor-model residual volatility (dev, primary): **{_pct(rv, False)}** a year (R² {base.get('ff_r2', 0):.2f}).
  Tracking error vs SPY, for comparison: {_pct(base['tracking_error_ann'], False)}.
- Over the {ty}-year test period, the 95% CI on factor alpha will be roughly ±{_pct(half, False)} around
  the estimate.
- **Minimum detectable alpha (80% power): {_pct(base.get('mda_ff_test_period'), False)} a year**
  (vs SPY: {_pct(base['mda_spy_test_period'], False)}).
- The test can reliably detect a true alpha of about {_pct(base.get('mda_ff_test_period'), False)} or more. An
  "inconclusive" result would NOT show that smaller edges are absent. The `rules_out` rule (CI upper
  bound < 2%) can only trigger if the point estimate comes in below about {_pct(0.02 - half if half else None)}.

## Portfolio (primary)
- Factor loadings: {betas}
- Signals before filters: {f['before']:,}; removed by {drops}; kept {f['kept']:,}
- Positions opened: {base['n_positions_opened']:,}; held {base['avg_positions']:.0f} on average ({base['max_positions']} max);
  average cash weight {base['avg_cash_weight']:.1%}
- Exits: {ex.get('hold_limit', 0):,} hold limit, {ex.get('filer_sale', 0):,} filer sale, {ex.get('delist', 0):,} delisting,
  {ex.get('open', 0):,} open at period end
- Max drawdown {base['max_drawdown']:.1%}; volatility {base['ann_vol']:.1%}; beta vs SPY {base['beta_vs_spy']:.2f}
{t51_txt}"""
    out = root / ("SUMMARY.md" if group == "insider" else f"SUMMARY_{group}.md")
    out.write_text(md, encoding="utf-8")
    return out
