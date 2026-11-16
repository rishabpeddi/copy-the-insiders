"""Write reports/dev_results/SUMMARY.md from the scenario metrics.json files."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from cti.config import REPORTS_DIR, Config

TITLES = {"insider": "insider purchases", "congress": "House member purchases"}


def write_dev_report(cfg: Config, reports_dir: Path = REPORTS_DIR, group: str = "insider") -> Path:
    root = reports_dir / "dev_results"
    ms = {p.parent.name.removeprefix(f"{group}_"): json.loads(p.read_text())
          for p in sorted(root.glob(f"{group}_*/metrics.json"))}
    if not ms:
        raise FileNotFoundError("No dev results. Run `cti run --period dev`.")
    base = ms.get("base") or next(iter(ms.values()))
    pct = lambda x: f"{x:+.2%}" if x is not None else "n/a"  # noqa: E731

    rows = "\n".join(
        f"| {k} | {m['cagr']:.2%} | {m['spy_cagr']:.2%} | {pct(m['active_return_ann'])} "
        f"[{pct(m['active_ci_low'])}, {pct(m['active_ci_high'])}] | {pct(m['jensen_alpha_ann'])} | "
        f"{m['tracking_error_ann']:.1%} | {m['turnover_per_year']:.1f}x | {m['costs_per_year']:.2%} |"
        for k, m in ms.items())
    ex = base["exit_reasons"]
    md = f"""# Dev-period results: {TITLES[group]} (generated)

Generated {dt.datetime.now():%Y-%m-%d %H:%M}. Period: dev, from {base.get('start', '?')} ({base['years']} years). Prices: {cfg['data']['price_source']}
(survivors only; see `reports/data_quality.md`). prereg sha256 `{base['prereg_sha256'][:12]}` (not tagged).

**This is the development period. Rules were not changed to improve these numbers, and they say
nothing yet about the test period.**

| scenario | CAGR | SPY CAGR | active return (95% block-bootstrap CI) | Jensen alpha | tracking error | turnover | costs/yr |
|---|---:|---:|---|---:|---:|---:|---:|
{rows}

Active return = mean daily (strategy - SPY) x 252. Jensen alpha adjusts for beta
({base['beta_vs_spy']:.2f} in base) and the T-bill rate. CIs are not yet Holm-adjusted.

## Portfolio sanity (base)
- Buy signals in period: {base['n_buy_signals']:,}; positions opened: {base['n_positions_opened']:,}
  (repeat buys of a held stock join the existing position)
- Positions held: {base['avg_positions']:.0f} on average, {base['max_positions']} at most
- Exits: {ex.get('hold_limit', 0):,} hold limit, {ex.get('filer_sale', 0):,} filer sale,
  {ex.get('delist', 0):,} delisting, {ex.get('open', 0):,} still open at period end
- Median position return while held: {base['median_position_return']:+.1%}
- Max drawdown {base['max_drawdown']:.1%}; annual volatility {base['ann_vol']:.1%}
- Delistings priced at last close (free source has no delisting returns): {base['n_delisted_last_price']}

## Power
Tracking error vs SPY is {base['tracking_error_ann']:.1%} a year. Over the {base['test_years']}-year
test period, the **minimum detectable alpha at 80% power is {base['mda_test_period']:.1%} a year**
(two-sided, alpha = {cfg['inference']['alpha']}). Any true alpha much smaller than that will most
likely come out "inconclusive". Record this in PREREG.md before tagging.
"""
    out = root / ("SUMMARY.md" if group == "insider" else f"SUMMARY_{group}.md")
    out.write_text(md, encoding="utf-8")
    return out
