# Dev-period results: House member purchases (generated)

Generated 2026-11-15 20:19. Period: dev, from 2015-01-05 (6.99 years).
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
| primary | 13.43% | 14.85% | +0.23% [-2.74%, +3.02%] | -0.98% [-5.13%, +4.39%] | n/a | 7.1x | 0.71% | 7,962 |
| bound_benchmark | 13.59% | 14.85% | -0.09% [-2.01%, +1.53%] | -0.97% [-3.56%, +2.26%] | n/a | 6.5x | 0.65% | 7,962 + 1,352 synthetic |
| bound_minus_100 | -44.85% | 14.85% | -67.66% [-80.65%, -55.23%] | -72.99% [-86.49%, -60.11%] | n/a | 8.6x | 0.86% | 7,962 + 1,352 synthetic |
| bound_zero | 9.16% | 14.85% | -0.12% [-2.15%, +1.89%] | -5.80% [-8.54%, -2.72%] | n/a | 6.6x | 0.66% | 7,962 + 1,352 synthetic |
| confidence_low | 13.16% | 14.85% | -0.11% [-2.80%, +2.46%] | -1.17% [-5.19%, +3.88%] | n/a | 7.1x | 0.71% | 7,973 |
| costs_stress | 12.19% | 14.85% | -0.87% [-3.74%, +2.03%] | -2.08% [-6.13%, +3.39%] | n/a | 7.1x | 1.78% | 7,962 |
| filing_lag_none | 12.91% | 14.85% | -0.40% [-3.05%, +2.33%] | -1.35% [-5.35%, +3.97%] | n/a | 7.0x | 0.70% | 9,163 |
| hold_63 | 13.67% | 14.85% | +0.78% [-2.47%, +3.57%] | -0.81% [-4.83%, +4.04%] | n/a | 11.3x | 1.13% | 7,962 |
| rebalance_on_entry_or_exit | 25.66% | 14.85% | +10.14% [+2.41%, +21.17%] | +9.47% [+1.34%, +21.12%] | n/a | 9.8x | 0.98% | 7,962 |
| weighting_amount_mid | 14.27% | 14.85% | +1.12% [-2.23%, +5.49%] | -0.42% [-4.09%, +5.20%] | n/a | 9.6x | 0.96% | 7,962 |

Each sensitivity run changes one thing from `primary`. `bound_*` runs add a sample of unmatched
purchases (no price data, mostly delisted companies), priced at -100% / 0% / SPY over the hold.

## Power: what the test can and cannot show
- Factor-model residual volatility (dev, primary): **5.26%** a year (R² 0.92).
  Tracking error vs SPY, for comparison: 6.96%.
- Over the 4.49-year test period, the 95% CI on factor alpha will be roughly ±4.87% around
  the estimate.
- **Minimum detectable alpha (80% power): 6.96% a year**
  (vs SPY: 9.20%).
- The test can reliably detect a true alpha of about 6.96% or more. An
  "inconclusive" result would NOT show that smaller edges are absent. The `rules_out` rule (CI upper
  bound < 2%) can only trigger if the point estimate comes in below about -2.87%.

## Portfolio (primary)
- Factor loadings: mkt_rf +0.95, smb +0.20, hml +0.10, rmw -0.03, cma -0.03, mom -0.08
- Signals before filters: 9,178; removed by filing lag: 1,205, low confidence: 11, synthetic unmatched: 0; kept 7,962
- Positions opened: 3,266; held 183 on average (333 max);
  average cash weight 3.3%
- Exits: 1,902 hold limit, 1,163 filer sale, 0 delisting,
  201 open at period end
- Max drawdown -37.6%; volatility 19.1%; beta vs SPY 1.01
