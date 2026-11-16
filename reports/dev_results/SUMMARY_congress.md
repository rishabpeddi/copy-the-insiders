# Dev-period results: House member purchases (generated)

Generated 2026-11-15 20:32. Period: dev, from 2015-01-05 (6.99 years).
Prices: yfinance (survivors only; see the data-quality reports and the survivorship
bounds below). prereg sha256 `84eb4c83f512` (not tagged).

**Development period only. Rules were fixed for reasons other than these returns (see the PREREG.md
changelog), and these numbers say nothing yet about the test period.**

## Results
Primary metric: **Fama-French 5-factor + momentum alpha** (annualized, 95% block-bootstrap CI).
"vs SPY" is the descriptive headline; "vs sector clone" is a secondary benchmark. CIs are not yet
Holm-adjusted across the two groups.

| scenario | CAGR | SPY CAGR | FF5+Mom alpha | vs SPY | vs sector clone | turnover | costs/yr | signals |
|---|---:|---:|---|---|---|---:|---:|---:|
| primary | 12.76% | 14.85% | -0.60% [-3.29%, +1.73%] | -1.64% [-5.56%, +3.19%] | -0.43% [-3.75%, +5.18%] | 7.1x | 0.71% | 8,021 |
| bound_benchmark | 13.06% | 14.85% | -0.47% [-2.82%, +1.58%] | -1.43% [-4.78%, +2.82%] | -0.40% [-3.19%, +4.66%] | 6.8x | 0.68% | 8,021 + 563 synthetic positions |
| bound_minus_100 | -22.89% | 14.85% | -36.83% [-45.47%, -30.12%] | -39.86% [-48.68%, -31.87%] | -39.08% [-47.64%, -30.35%] | 7.7x | 0.77% | 8,021 + 563 synthetic positions |
| bound_zero | 10.82% | 14.85% | -0.45% [-2.87%, +1.85%] | -3.93% [-7.05%, +0.09%] | -2.90% [-5.45%, +1.89%] | 6.8x | 0.68% | 8,021 + 563 synthetic positions |
| confidence_low | 12.69% | 14.85% | -0.67% [-3.36%, +1.63%] | -1.70% [-5.61%, +3.09%] | -0.47% [-3.78%, +5.11%] | 7.1x | 0.71% | 8,032 |
| costs_stress | 11.53% | 14.85% | -1.70% [-4.28%, +0.75%] | -2.74% [-6.56%, +2.20%] | -1.53% [-4.74%, +4.20%] | 7.1x | 1.77% | 8,021 |
| filing_lag_none | 12.26% | 14.85% | -1.02% [-3.59%, +1.38%] | -2.06% [-6.02%, +2.91%] | -0.87% [-4.36%, +5.21%] | 7.0x | 0.70% | 9,229 |
| hold_63 | 12.95% | 14.85% | -0.15% [-3.06%, +2.13%] | -1.55% [-5.29%, +2.63%] | +0.70% [-2.18%, +5.24%] | 11.3x | 1.13% | 8,021 |
| rebalance_on_entry_or_exit | 13.37% | 14.85% | -0.40% [-2.87%, +1.88%] | -0.95% [-4.80%, +3.77%] | -0.68% [-3.85%, +4.24%] | 9.6x | 0.96% | 8,021 |
| weighting_amount_mid | 13.60% | 14.85% | +0.30% [-2.63%, +3.67%] | -1.10% [-4.30%, +3.40%] | +1.08% [-1.58%, +6.64%] | 9.6x | 0.96% | 8,021 |

Each sensitivity run changes one thing from `primary`. `bound_*` runs add a sample of unmatched
purchases (no price data, mostly delisted companies), priced at -100% / 0% / SPY over the hold.

## Power: what the test can and cannot show
- Factor-model residual volatility (dev, primary): **3.53%** a year (R² 0.96).
  Tracking error vs SPY, for comparison: 5.67%.
- Over the 4.49-year test period, the 95% CI on factor alpha will be roughly ±3.27% around
  the estimate.
- **Minimum detectable alpha (80% power): 4.67% a year**
  (vs SPY: 7.50%).
- The test can reliably detect a true alpha of about 4.67% or more. An
  "inconclusive" result would NOT show that smaller edges are absent. The `rules_out` rule (CI upper
  bound < 2%) can only trigger if the point estimate comes in below about -1.27%.

## Portfolio (primary)
- Factor loadings: mkt_rf +0.96, smb +0.19, hml +0.10, rmw -0.01, cma -0.03, mom -0.08
- Signals before filters: 9,244; removed by filing lag: 1,212, low confidence: 11, synthetic unmatched: 0; kept 8,021
- Positions opened: 3,275; held 184 on average (332 max);
  average cash weight 3.3%
- Exits: 1,909 hold limit, 1,166 filer sale, 0 delisting,
  200 open at period end
- Max drawdown -37.5%; volatility 18.7%; beta vs SPY 1.01
