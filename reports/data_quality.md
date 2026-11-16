# Data quality (generated)

Generated 2026-11-15 20:09 by `cti resolve`. Price source: **yfinance**
(survivors only: see "Survivorship" below). Calendar: 3,258 trading days, 2013-12-02 to 2026-11-13.

## Insider purchase candidates -> securities
- Candidate transactions (after filing rules): **163,611**
- Matched to a priced security: **111,214 (68.0%)**
- Issuers: 7,667; with a priced ticker: 4,937 (64.4%)

| period | dates | candidates | matched |
|---|---|---:|---:|
| dev | 2014-01-01 to 2021-12-31 | 107,338 | 59.7% |
| test | 2022-01-01 to 2026-06-30 | 53,495 | 83.4% |
| forward | 2026-07-01 to 2028-06-30 | 2,778 | 93.2% |

If the match rate differs a lot between dev and test, the two samples are biased differently
(older periods lose more delisted companies), and dev results won't predict test results.

| Match confidence (matched) | count | share |
|---|---:|---:|
| high | 101,846 | 91.6% |
| medium | 6,160 | 5.5% |
| low | 3,208 | 2.9% |

| Match method (matched) | count | share |
|---|---:|---:|
| cik_and_filing_ticker | 104,777 | 94.2% |
| filing_ticker | 3,406 | 3.1% |
| cik_current_ticker | 3,031 | 2.7% |

| Unmatched reason | count | share |
|---|---:|---:|
| ticker_not_in_price_source | 42,749 | 26.1% |
| entry_before_price_history | 5,652 | 3.5% |
| price_mismatch | 2,416 | 1.5% |
| no_ticker_candidates | 1,576 | 1.0% |
| no_price_on_entry_date | 4 | 0.0% |

## Match rate by filing quarter
| quarter | candidates | matched |
|---|---:|---:|
| 2014Q1 | 2,710 | 50.2% |
| 2014Q2 | 3,969 | 45.3% |
| 2014Q3 | 2,905 | 54.4% |
| 2014Q4 | 3,910 | 44.8% |
| 2015Q1 | 2,833 | 49.7% |
| 2015Q2 | 3,318 | 45.8% |
| 2015Q3 | 4,695 | 52.2% |
| 2015Q4 | 4,141 | 52.3% |
| 2016Q1 | 5,016 | 54.0% |
| 2016Q2 | 3,215 | 54.8% |
| 2016Q3 | 3,036 | 50.3% |
| 2016Q4 | 3,181 | 57.4% |
| 2017Q1 | 2,269 | 59.1% |
| 2017Q2 | 3,182 | 54.0% |
| 2017Q3 | 2,619 | 61.0% |
| 2017Q4 | 2,551 | 61.8% |
| 2018Q1 | 2,728 | 66.1% |
| 2018Q2 | 3,234 | 60.9% |
| 2018Q3 | 2,733 | 59.9% |
| 2018Q4 | 4,528 | 63.1% |
| 2019Q1 | 2,239 | 60.0% |
| 2019Q2 | 3,841 | 62.1% |
| 2019Q3 | 3,532 | 65.8% |
| 2019Q4 | 2,536 | 64.1% |
| 2020Q1 | 6,643 | 71.2% |
| 2020Q2 | 3,651 | 70.0% |
| 2020Q3 | 3,316 | 68.5% |
| 2020Q4 | 2,385 | 68.6% |
| 2021Q1 | 2,511 | 69.8% |
| 2021Q2 | 2,866 | 73.0% |
| 2021Q3 | 3,200 | 71.9% |
| 2021Q4 | 3,845 | 68.9% |
| 2022Q1 | 4,307 | 72.7% |
| 2022Q2 | 4,963 | 75.5% |
| 2022Q3 | 3,459 | 76.0% |
| 2022Q4 | 3,881 | 69.8% |
| 2023Q1 | 2,780 | 78.0% |
| 2023Q2 | 3,711 | 77.4% |
| 2023Q3 | 2,634 | 80.8% |
| 2023Q4 | 3,316 | 85.8% |
| 2024Q1 | 2,051 | 85.6% |
| 2024Q2 | 2,393 | 83.1% |
| 2024Q3 | 2,049 | 89.6% |
| 2024Q4 | 2,203 | 89.3% |
| 2025Q1 | 2,345 | 91.9% |
| 2025Q2 | 2,402 | 91.8% |
| 2025Q3 | 2,584 | 93.5% |
| 2025Q4 | 3,026 | 95.9% |
| 2026Q1 | 2,369 | 95.5% |
| 2026Q2 | 3,022 | 95.2% |
| 2026Q3 | 2,778 | 93.2% |

## Tickers shared by more than one CIK
145 tickers. These may be share classes, parent/subsidiary filers, or ticker reuse; check
them in the audit. ACET, ACI, ACTU, ADT, AERO, AESI, AI, AKTS, AMR, ANGI, APA, APC, APO, APP, ARIS, ARRY, AX, AXNX, AXON, AXP, BEAT, BEEP, BETR, BG, BGC, BHVN, BID, BIOA, BMR, BNY

## Survivorship
`ticker_not_in_price_source` is mostly companies that were delisted, acquired, or renamed with no
history kept by the free source. Those are exactly the cases survivorship bias hides, so this
number is a lower bound on the bias problem, not noise. Final results need CRSP or a vendor that
covers delistings.

## Hand audit
`reports/audit/match_audit_sample.csv` has 100 random matched transactions (seed
20260101). Fill `audit_correct` (y/n) for each one by checking that the
ticker belongs to the issuer on the trade date. Unmatched rows with reasons:
`reports/audit/unmatched.csv`.
