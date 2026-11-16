# Dev-period results: insider purchases (generated)

Generated 2026-11-15 19:06. Period: dev (8.0 years). Prices: yfinance
(survivors only; see `reports/data_quality.md`). prereg sha256 `29c7463aad29` (not tagged).

**This is the development period. Rules were not changed to improve these numbers, and they say
nothing yet about the test period.**

| scenario | CAGR | SPY CAGR | active return (95% block-bootstrap CI) | Jensen alpha | tracking error | turnover | costs/yr |
|---|---:|---:|---|---:|---:|---:|---:|
| base | 14.41% | 14.66% | +0.87% [-5.56%, +9.75%] | -1.02% | 11.8% | 8.9x | 0.89% |
| base_hold63 | 14.11% | 14.66% | +0.64% [-5.77%, +9.30%] | -1.28% | 12.1% | 13.7x | 1.37% |
| stress | 12.85% | 14.66% | -0.51% [-6.82%, +8.49%] | -2.39% | 11.8% | 8.9x | 2.24% |
| stress_hold63 | 11.75% | 14.66% | -1.44% [-7.75%, +7.34%] | -3.37% | 12.1% | 13.8x | 3.44% |

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
