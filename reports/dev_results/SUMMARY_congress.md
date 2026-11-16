# Dev-period results: House member purchases (generated)

Generated 2026-11-15 19:27. Period: dev, from 2015-01-05 (6.99 years). Prices: yfinance
(survivors only; see `reports/data_quality.md`). prereg sha256 `013a7675bdfc` (not tagged).

**This is the development period. Rules were not changed to improve these numbers, and they say
nothing yet about the test period.**

| scenario | CAGR | SPY CAGR | active return (95% block-bootstrap CI) | Jensen alpha | tracking error | turnover | costs/yr |
|---|---:|---:|---|---:|---:|---:|---:|
| base | 3.93% | 14.85% | -11.10% [-19.99%, -3.50%] | -0.44% | 15.4% | 4.9x | 0.49% |
| base_hold63 | 4.70% | 14.85% | -10.37% [-19.41%, -2.81%] | +0.53% | 15.7% | 7.0x | 0.70% |
| stress | 3.09% | 14.85% | -11.90% [-20.52%, -4.37%] | -1.25% | 15.4% | 5.0x | 1.25% |
| stress_hold63 | 3.48% | 14.85% | -11.54% [-20.19%, -4.04%] | -0.65% | 15.7% | 7.2x | 1.79% |

Active return = mean daily (strategy - SPY) x 252. Jensen alpha adjusts for beta
(0.27 in base) and the T-bill rate. CIs are not yet Holm-adjusted.

## Portfolio sanity (base)
- Buy signals in period: 1,812; positions opened: 781
  (repeat buys of a held stock join the existing position)
- Positions held: 45 on average, 156 at most
- Exits: 497 hold limit, 284 filer sale,
  0 delisting, 0 still open at period end
- Median position return while held: +2.8%
- Max drawdown -19.5%; annual volatility 9.7%
- Delistings priced at last close (free source has no delisting returns): 0

## Power
Tracking error vs SPY is 15.4% a year. Over the 4.49-year
test period, the **minimum detectable alpha at 80% power is 20.4% a year**
(two-sided, alpha = 0.05). Any true alpha much smaller than that will most
likely come out "inconclusive". Record this in PREREG.md before tagging.
