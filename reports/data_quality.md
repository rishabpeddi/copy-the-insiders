# Data quality (generated)

Generated 2026-11-15 15:29 by `cti resolve`. Price source: **yfinance**
(survivors only: see "Survivorship" below). Calendar: 3,258 trading days, 2013-12-02 to 2026-11-13.

## Insider purchase candidates -> securities
- Candidate transactions (after filing rules): **1,948**
- Matched to a priced security: **1,659 (85.2%)**
- Issuers: 671; with a priced ticker: 577 (86.0%)

| Match confidence (matched) | count | share |
|---|---:|---:|
| high | 1,501 | 90.5% |
| low | 87 | 5.2% |
| medium | 71 | 4.3% |

| Match method (matched) | count | share |
|---|---:|---:|
| cik_and_filing_ticker | 1,583 | 95.4% |
| cik_current_ticker | 58 | 3.5% |
| filing_ticker | 18 | 1.1% |

| Unmatched reason | count | share |
|---|---:|---:|
| ticker_not_in_price_source | 211 | 10.8% |
| no_ticker_candidates | 34 | 1.7% |
| price_mismatch | 23 | 1.2% |
| no_price_on_entry_date | 21 | 1.1% |

## Match rate by filing quarter
| quarter | candidates | matched |
|---|---:|---:|
| 2024Q1 | 1,948 | 85.2% |

## Tickers shared by more than one CIK
0 tickers. These may be share classes, parent/subsidiary filers, or ticker reuse; check
them in the audit. None.

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
