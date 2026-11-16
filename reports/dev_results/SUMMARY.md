# Dev-period results: insider purchases (generated)

Generated 2026-11-15 20:17. Period: dev, from 2014-01-03 (7.99 years).
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
| primary | 13.51% | 14.81% | +2.16% [+0.53%, +5.62%] | -0.15% [-6.35%, +8.94%] | n/a | 6.2x | 0.62% | 29,650 |
| 10b5_1_footnote_only | 13.51% | 14.81% | +2.16% [+0.53%, +5.62%] | -0.15% [-6.35%, +8.94%] | n/a | 6.2x | 0.62% | 29,650 |
| bound_benchmark | 13.62% | 14.81% | -0.01% [-0.88%, +1.22%] | -0.90% [-2.57%, +1.74%] | n/a | 5.7x | 0.57% | 29,650 + 18,726 synthetic |
| bound_minus_100 | -78.92% | 14.81% | -154.32% [-167.24%, -133.74%] | -165.02% [-178.03%, -144.74%] | n/a | 11.6x | 1.16% | 29,650 + 18,726 synthetic |
| bound_zero | 2.97% | 14.81% | -0.97% [-1.93%, +0.68%] | -12.12% [-15.98%, -7.34%] | n/a | 6.0x | 0.60% | 29,650 + 18,726 synthetic |
| costs_stress | 12.40% | 14.81% | +1.17% [-0.34%, +4.78%] | -1.13% [-7.20%, +8.12%] | n/a | 6.2x | 1.56% | 29,650 |
| filing_lag_none | 13.75% | 14.81% | +2.34% [+0.66%, +5.69%] | +0.04% [-6.15%, +8.98%] | n/a | 6.2x | 0.62% | 30,237 |
| hold_63 | 12.75% | 14.81% | +1.59% [-0.18%, +5.01%] | -0.85% [-7.33%, +8.20%] | n/a | 10.6x | 1.06% | 29,650 |
| rebalance_on_entry_or_exit | 14.18% | 14.81% | +2.69% [+1.05%, +6.68%] | +0.56% [-5.73%, +9.79%] | n/a | 8.9x | 0.89% | 29,650 |

Each sensitivity run changes one thing from `primary`. `bound_*` runs add a sample of unmatched
purchases (no price data, mostly delisted companies), priced at -100% / 0% / SPY over the hold.

## Power: what the test can and cannot show
- Factor-model residual volatility (dev, primary): **3.70%** a year (R² 0.97).
  Tracking error vs SPY, for comparison: 11.47%.
- Over the 4.49-year test period, the 95% CI on factor alpha will be roughly ±3.42% around
  the estimate.
- **Minimum detectable alpha (80% power): 4.89% a year**
  (vs SPY: 15.16%).
- The test can reliably detect a true alpha of about 4.89% or more. An
  "inconclusive" result would NOT show that smaller edges are absent. The `rules_out` rule (CI upper
  bound < 2%) can only trigger if the point estimate comes in below about -1.42%.

## Portfolio (primary)
- Factor loadings: mkt_rf +1.00, smb +0.66, hml +0.29, rmw -0.04, cma -0.12, mom -0.13
- Signals before filters: 32,009; removed by filing lag: 608, 10b5 1: 1,751, synthetic unmatched: 0; kept 29,650
- Positions opened: 6,051; held 354 on average (637 max);
  average cash weight 1.6%
- Exits: 5,319 hold limit, 194 filer sale, 0 delisting,
  538 open at period end
- Max drawdown -43.5%; volatility 22.0%; beta vs SPY 1.11

## 10b5-1 classification (universe-passing purchases in this period)
- flagged by primary rule: 1,772
- flagged by footnote text: 1,772
- primary only (checkbox, no footnote): 0
- footnote only (footnote, checkbox says no): 0
- purchases in period: 32,009

The primary rule uses the SEC checkbox where it exists (April 2023 onward) and footnote text before that. The `10b5_1_footnote_only` run uses footnote text in every period.
