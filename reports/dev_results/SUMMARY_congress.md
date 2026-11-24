# Dev-period results: House member purchases (generated)

Generated 2026-11-24 00:36. Period: dev, from 2014-02-03 (7.91 years).
Prices: yfinance (survivors only; see the data-quality reports and the survivorship
bounds below). prereg sha256 `e0471c17d986` (not tagged).

**Development period only. Rules were fixed for reasons other than these returns (see the PREREG.md
changelog), and these numbers say nothing yet about the test period.**

## Results
Primary metric: **Fama-French 5-factor + momentum alpha** (annualized, 95% block-bootstrap CI).
"vs SPY" is the descriptive headline; "vs sector clone" is a secondary benchmark. CIs are not yet
Holm-adjusted across the two groups.

| scenario | CAGR | SPY CAGR | FF5+Mom alpha | vs SPY | vs sector clone | turnover | costs/yr | signals |
|---|---:|---:|---|---|---|---:|---:|---:|
| primary | 13.22% | 15.35% | -0.35% [-2.44%, +2.26%] | -1.64% [-4.66%, +3.20%] | +0.16% [-3.08%, +4.92%] | 6.9x | 0.69% | 10,173 |
| bound_benchmark | 13.46% | 15.35% | -0.32% [-2.11%, +1.93%] | -1.50% [-4.05%, +2.64%] | +0.19% [-2.62%, +4.23%] | 6.7x | 0.67% | 10,173 + 683 synthetic positions |
| bound_minus_100 | -23.45% | 15.35% | -37.40% [-45.22%, -29.93%] | -41.03% [-48.63%, -32.76%] | -39.50% [-47.75%, -31.27%] | 7.5x | 0.75% | 10,173 + 683 synthetic positions |
| bound_zero | 11.18% | 15.35% | -0.05% [-2.00%, +2.24%] | -4.03% [-6.32%, -0.17%] | -2.36% [-4.97%, +1.41%] | 6.7x | 0.67% | 10,173 + 683 synthetic positions |
| confidence_low | 13.13% | 15.35% | -0.43% [-2.47%, +2.09%] | -1.73% [-4.74%, +3.07%] | +0.16% [-3.08%, +4.86%] | 6.9x | 0.69% | 10,240 |
| costs_stress | 12.02% | 15.35% | -1.41% [-3.45%, +1.26%] | -2.71% [-5.68%, +2.19%] | -0.90% [-4.09%, +3.91%] | 6.9x | 1.72% | 10,173 |
| filing_lag_none | 12.69% | 15.35% | -0.79% [-2.75%, +1.86%] | -2.09% [-5.14%, +2.91%] | -0.31% [-3.72%, +4.90%] | 6.9x | 0.69% | 11,494 |
| hold_63 | 13.89% | 15.35% | +0.52% [-2.08%, +3.55%] | -1.13% [-4.12%, +3.38%] | +1.28% [-1.70%, +5.38%] | 11.1x | 1.11% | 10,173 |
| rebalance_on_entry_or_exit | 13.88% | 15.35% | -0.08% [-2.00%, +2.42%] | -0.92% [-3.92%, +3.94%] | +0.12% [-3.09%, +4.36%] | 9.4x | 0.94% | 10,173 |
| weighting_amount_mid | 13.67% | 15.35% | +0.45% [-3.05%, +4.13%] | -1.36% [-4.48%, +3.38%] | +2.26% [-1.61%, +7.27%] | 9.2x | 0.92% | 10,173 |

Each sensitivity run changes one thing from `primary`. `bound_*` runs add a sample of unmatched
purchases (no price data, mostly delisted companies), priced at -100% / 0% / SPY over the hold.

## Power: what the test can and cannot show
- Factor-model residual volatility (dev, primary): **3.48%** a year (R² 0.96).
  Tracking error vs SPY, for comparison: 5.46%.
- Over the 4.49-year test period, the 95% CI on factor alpha will be roughly ±3.21% around
  the estimate.
- **Minimum detectable alpha (80% power): 4.59% a year**
  (vs SPY: 7.22%).
- The test can reliably detect a true alpha of about 4.59% or more. An
  "inconclusive" result would NOT show that smaller edges are absent. The `rules_out` rule (CI upper
  bound < 2%) can only trigger if the point estimate comes in below about -1.21%.

## Portfolio (primary)
- Factor loadings: mkt_rf +0.97, smb +0.18, hml +0.10, rmw -0.02, cma -0.03, mom -0.07
- Signals before filters: 11,567; removed by filing lag: 1,327, low confidence: 67, synthetic unmatched: 0; kept 10,173
- Positions opened: 3,754; held 186 on average (364 max);
  average cash weight 3.0%
- Exits: 2,154 hold limit, 1,378 filer sale, 0 delisting,
  222 open at period end
- Max drawdown -38.2%; volatility 18.3%; beta vs SPY 1.02
