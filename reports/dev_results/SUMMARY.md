# Dev-period results: insider purchases (generated)

Generated 2026-11-15 19:26. Period: dev, from 2014-01-03 (7.99 years). Prices: yfinance
(survivors only; see `reports/data_quality.md`). prereg sha256 `013a7675bdfc` (not tagged).

**This is the development period. Rules were not changed to improve these numbers, and they say
nothing yet about the test period.**

| scenario | CAGR | SPY CAGR | active return (95% block-bootstrap CI) | Jensen alpha | tracking error | turnover | costs/yr |
|---|---:|---:|---|---:|---:|---:|---:|
| base | 14.41% | 14.81% | +0.75% [-5.53%, +9.80%] | -1.16% | 11.8% | 8.9x | 0.89% |
| base_hold63 | 14.12% | 14.81% | +0.52% [-5.75%, +9.29%] | -1.43% | 12.1% | 13.7x | 1.37% |
| stress | 12.85% | 14.81% | -0.63% [-6.78%, +8.52%] | -2.54% | 11.8% | 8.9x | 2.24% |
| stress_hold63 | 11.76% | 14.81% | -1.56% [-7.70%, +7.33%] | -3.52% | 12.1% | 13.8x | 3.44% |

Active return = mean daily (strategy - SPY) x 252. Jensen alpha adjusts for beta
(1.13 in base) and the T-bill rate. CIs are not yet Holm-adjusted.

## Portfolio sanity (base)
- Buy signals in period: 30,237; positions opened: 6,193
  (repeat buys of a held stock join the existing position)
- Positions held: 362 on average, 648 at most
- Exits: 5,421 hold limit, 227 filer sale,
  0 delisting, 545 still open at period end
- Median position return while held: +5.2%
- Max drawdown -45.0%; annual volatility 22.5%
- Delistings priced at last close (free source has no delisting returns): 0

## Power
Tracking error vs SPY is 11.8% a year. Over the 4.49-year
test period, the **minimum detectable alpha at 80% power is 15.6% a year**
(two-sided, alpha = 0.05). Any true alpha much smaller than that will most
likely come out "inconclusive". Record this in PREREG.md before tagging.
