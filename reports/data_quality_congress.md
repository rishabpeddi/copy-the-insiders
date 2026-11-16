# Congress data quality (generated): House PTRs

Source: House Clerk periodic transaction reports (2015 onward). Senate not yet included.

## Documents
| PTR status | count | share |
|---|---:|---:|
| parsed | 5,707 | 73.8% |
| paper_scan_not_parsed | 2,031 | 26.2% |

Paper scans have no text layer; parsing them needs OCR (not done), so they are a coverage gap.

## Transactions
- Parsed transactions: **55,830**
- In scope (purchase or sale of a stock with a ticker): **45,524**
- Matched to a priced security: **37,129 (81.6% of in scope)**

| Unmatched / out-of-scope reason | count | share |
|---|---:|---:|
| not_stock_asset_type | 6,221 | 11.1% |
| ticker_not_mapped | 4,319 | 7.7% |
| no_ticker | 3,525 | 6.3% |
| ticker_not_in_price_source | 3,510 | 6.3% |
| not_purchase_or_sale | 560 | 1.0% |
| entry_before_price_history | 469 | 0.8% |
| name_mismatch | 97 | 0.2% |

| Match confidence (matched) | count | share |
|---|---:|---:|
| high | 34,366 | 92.6% |
| medium | 2,555 | 6.9% |
| low | 208 | 0.6% |

| Match method (matched) | count | share |
|---|---:|---:|
| form4_ticker_history | 34,574 | 93.1% |
| sec_current_ticker | 2,555 | 6.9% |

## By filing year
| year | PTRs | parsed (electronic) | paper scans | in-scope txns | matched |
|---|---:|---:|---:|---:|---:|
| 2015 | 690 | 390 | 300 | 3,013 | 64.7% |
| 2016 | 777 | 450 | 327 | 2,834 | 69.6% |
| 2017 | 803 | 506 | 297 | 2,878 | 73.4% |
| 2018 | 832 | 533 | 299 | 3,261 | 70.9% |
| 2019 | 691 | 520 | 171 | 4,317 | 76.7% |
| 2020 | 735 | 597 | 138 | 6,139 | 78.7% |
| 2021 | 683 | 565 | 118 | 4,767 | 84.1% |
| 2022 | 621 | 505 | 116 | 2,865 | 84.4% |
| 2023 | 469 | 388 | 81 | 3,489 | 81.4% |
| 2024 | 445 | 394 | 51 | 2,142 | 93.2% |
| 2025 | 518 | 449 | 69 | 6,743 | 95.2% |
| 2026 | 474 | 410 | 64 | 3,076 | 96.0% |

## Electronic vs paper filers
421 members filed PTRs: 289 electronic only, 76 paper only,
56 both. 26.2% of all PTRs are paper. The 10 most frequent filers account for
21.3% of PTRs, so a few members drive much of the sample. Members with the highest paper share:

| member | PTRs | paper |
|---|---:|---:|
| ROGERS, HAROLD DALLAS (KY05) | 141 | 100% |
| MCCAUL, MICHAEL T. (TX10) | 140 | 100% |
| KHANNA, ROHIT (CA17) | 121 | 100% |
| DELANEY, JOHN K. (MD06) | 100 | 100% |
| RENACCI, JAMES B. (OH16) | 96 | 100% |
| SCHRADER, KURT (OR05) | 96 | 100% |
| FLEISCHMANN, CHARLES J. "CHUCK" (TN03) | 89 | 100% |
| ROE, DAVID P. (TN01) | 72 | 100% |
| BLACK, DIANE (TN06) | 65 | 100% |
| LAMBORN, DOUG (CO05) | 64 | 100% |
| MARCHANT, KENNY (TX24) | 60 | 100% |
| FRELINGHUYSEN, RODNEY P. (NJ11) | 58 | 100% |
| UPTON, FRED (MI06) | 58 | 100% |
| POLIS, JARED (CO02) | 56 | 100% |
| KELLY, MIKE (PA03) | 51 | 100% |

Paper filers' trades are missing from every result. If they trade differently, the House result
describes electronic filers, not all members.

## Hand audit
`reports/audit/congress_match_audit_sample.csv`: 100 random matched transactions. Fill `audit_correct`.
