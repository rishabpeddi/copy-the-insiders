# Congress data quality (generated): House PTRs

Source: House Clerk periodic transaction reports (2015 onward). Senate not yet included.

## Documents
| PTR status | count | share |
|---|---:|---:|
| not_downloaded | 4,615 | 59.6% |
| paper_scan_not_parsed | 2,031 | 26.2% |
| parsed | 1,092 | 14.1% |

Paper scans have no text layer; parsing them needs OCR (not done), so they are a coverage gap.

## Transactions
- Parsed transactions: **9,345**
- In scope (purchase or sale of a stock with a ticker): **6,992**
- Matched to a priced security: **4,000 (57.2% of in scope)**

| Unmatched / out-of-scope reason | count | share |
|---|---:|---:|
| no_ticker | 2,177 | 23.3% |
| ticker_not_in_price_source | 1,802 | 19.3% |
| ticker_not_mapped | 968 | 10.4% |
| entry_before_price_history | 191 | 2.0% |
| not_purchase_or_sale | 176 | 1.9% |
| name_mismatch | 31 | 0.3% |

| Match confidence (matched) | count | share |
|---|---:|---:|
| high | 3,911 | 97.8% |
| medium | 60 | 1.5% |
| low | 29 | 0.7% |

| Match method (matched) | count | share |
|---|---:|---:|
| form4_ticker_history | 3,940 | 98.5% |
| sec_current_ticker | 60 | 1.5% |

## By filing year
| year | PTRs | parsed (electronic) | paper scans | in-scope txns | matched |
|---|---:|---:|---:|---:|---:|
| 2015 | 690 | 390 | 300 | 3,013 | 54.5% |
| 2016 | 777 | 450 | 327 | 2,834 | 57.6% |
| 2017 | 803 | 252 | 297 | 1,145 | 63.4% |
| 2018 | 832 | 0 | 299 | 0 |  |
| 2019 | 691 | 0 | 171 | 0 |  |
| 2020 | 735 | 0 | 138 | 0 |  |
| 2021 | 683 | 0 | 118 | 0 |  |
| 2022 | 621 | 0 | 116 | 0 |  |
| 2023 | 469 | 0 | 81 | 0 |  |
| 2024 | 445 | 0 | 51 | 0 |  |
| 2025 | 518 | 0 | 69 | 0 |  |
| 2026 | 474 | 0 | 64 | 0 |  |

## Hand audit
`reports/audit/congress_match_audit_sample.csv`: 100 random matched transactions. Fill `audit_correct`.
