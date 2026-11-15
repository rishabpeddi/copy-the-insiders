# Data quality (generated)

Generated 2026-11-15 17:16 by `cti resolve`. Price source: **yfinance**
(survivors only: see "Survivorship" below). Calendar: 3,258 trading days, 2013-12-02 to 2026-11-13.

## Insider purchase candidates -> securities
- Candidate transactions (after filing rules): **154,240**
- Matched to a priced security: **104,667 (67.9%)**
- Issuers: 7,630; with a priced ticker: 4,910 (64.4%)

| period | dates | candidates | matched |
|---|---|---:|---:|
| dev | 2014-01-01 to 2021-12-31 | 100,886 | 59.4% |
| test | 2022-01-01 to 2026-06-30 | 50,633 | 83.3% |
| forward | 2026-07-01 to now | 2,721 | 93.1% |

If the match rate differs a lot between dev and test, the two samples are biased differently
(older periods lose more delisted companies), and dev results won't predict test results.

| Match confidence (matched) | count | share |
|---|---:|---:|
| high | 95,624 | 91.4% |
| medium | 5,889 | 5.6% |
| low | 3,154 | 3.0% |

| Match method (matched) | count | share |
|---|---:|---:|
| cik_and_filing_ticker | 98,539 | 94.1% |
| filing_ticker | 3,167 | 3.0% |
| cik_current_ticker | 2,961 | 2.8% |

| Unmatched reason | count | share |
|---|---:|---:|
| ticker_not_in_price_source | 40,253 | 26.1% |
| entry_before_price_history | 5,419 | 3.5% |
| price_mismatch | 2,301 | 1.5% |
| no_ticker_candidates | 1,596 | 1.0% |
| no_price_on_entry_date | 4 | 0.0% |

## Match rate by filing quarter
| quarter | candidates | matched |
|---|---:|---:|
| 2014Q1 | 2,663 | 49.9% |
| 2014Q2 | 3,738 | 42.5% |
| 2014Q3 | 2,671 | 53.2% |
| 2014Q4 | 3,574 | 46.7% |
| 2015Q1 | 2,748 | 50.0% |
| 2015Q2 | 3,143 | 45.2% |
| 2015Q3 | 4,531 | 51.4% |
| 2015Q4 | 3,865 | 52.0% |
| 2016Q1 | 4,779 | 53.6% |
| 2016Q2 | 3,028 | 53.9% |
| 2016Q3 | 2,785 | 48.1% |
| 2016Q4 | 2,775 | 54.5% |
| 2017Q1 | 2,037 | 56.7% |
| 2017Q2 | 3,001 | 52.2% |
| 2017Q3 | 2,574 | 61.1% |
| 2017Q4 | 2,470 | 61.1% |
| 2018Q1 | 2,624 | 65.4% |
| 2018Q2 | 2,903 | 64.6% |
| 2018Q3 | 2,372 | 63.4% |
| 2018Q4 | 4,115 | 61.5% |
| 2019Q1 | 1,994 | 60.1% |
| 2019Q2 | 3,542 | 63.4% |
| 2019Q3 | 3,385 | 66.5% |
| 2019Q4 | 2,304 | 66.2% |
| 2020Q1 | 6,328 | 70.9% |
| 2020Q2 | 3,371 | 69.9% |
| 2020Q3 | 3,212 | 68.7% |
| 2020Q4 | 2,307 | 68.8% |
| 2021Q1 | 2,463 | 69.5% |
| 2021Q2 | 2,742 | 71.8% |
| 2021Q3 | 3,118 | 71.8% |
| 2021Q4 | 3,724 | 68.7% |
| 2022Q1 | 3,885 | 70.1% |
| 2022Q2 | 4,796 | 74.8% |
| 2022Q3 | 3,196 | 74.5% |
| 2022Q4 | 3,495 | 71.1% |
| 2023Q1 | 2,620 | 77.7% |
| 2023Q2 | 3,491 | 79.2% |
| 2023Q3 | 2,447 | 80.1% |
| 2023Q4 | 3,122 | 85.2% |
| 2024Q1 | 1,938 | 85.2% |
| 2024Q2 | 2,300 | 84.1% |
| 2024Q3 | 2,012 | 89.4% |
| 2024Q4 | 2,180 | 89.5% |
| 2025Q1 | 2,155 | 91.2% |
| 2025Q2 | 2,356 | 91.6% |
| 2025Q3 | 2,531 | 93.4% |
| 2025Q4 | 2,952 | 96.1% |
| 2026Q1 | 2,303 | 95.7% |
| 2026Q2 | 2,854 | 95.1% |
| 2026Q3 | 2,721 | 93.1% |

## Tickers shared by more than one CIK
144 tickers. These may be share classes, parent/subsidiary filers, or ticker reuse; check
them in the audit. ACET, ACI, ACTU, ADT, AERO, AESI, AI, AKTS, AMR, ANGI, APA, APC, APO, APP, ARIS, ARRY, AX, AXNX, AXON, AXP, BEAT, BETR, BG, BGC, BH, BHVN, BID, BIOA, BMR, BNY

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
