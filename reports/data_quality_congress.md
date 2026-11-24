# Congress data quality (generated): House and Senate PTRs

Sources: House Clerk periodic transaction reports (2015 onward) and Senate eFD periodic transaction
reports (2012 onward). Both chambers form one Congress group.

## By chamber
| chamber | PTRs | paper scans | in-scope txns | matched | matched purchases |
|---|---:|---:|---:|---:|---:|
| house | 7,738 | 2,031 | 45,524 | 37,129 (81.6%) | 18,451 |
| senate | 2,138 | 308 | 10,060 | 7,718 (76.7%) | 3,909 |

## Documents
| PTR status | count | share |
|---|---:|---:|
| parsed | 7,533 | 76.3% |
| paper_scan_not_parsed | 2,339 | 23.7% |
| not_downloaded | 4 | 0.0% |

Paper scans have no text layer; parsing them needs OCR (not done), so they are a coverage gap.

## Transactions
- Parsed transactions: **69,847**
- In scope (purchase or sale of a stock with a ticker): **55,584**
- Matched to a priced security: **44,847 (80.7% of in scope)**

| Unmatched / out-of-scope reason | count | share |
|---|---:|---:|
| not_stock_asset_type | 9,330 | 13.4% |
| ticker_not_mapped | 5,290 | 7.6% |
| ticker_not_in_price_source | 4,561 | 6.5% |
| no_ticker | 4,244 | 6.1% |
| entry_before_price_history | 725 | 1.0% |
| not_purchase_or_sale | 689 | 1.0% |
| name_mismatch | 160 | 0.2% |
| entry_after_calendar_end | 1 | 0.0% |

| Match confidence (matched) | count | share |
|---|---:|---:|
| high | 41,496 | 92.5% |
| medium | 2,964 | 6.6% |
| low | 387 | 0.9% |

| Match method (matched) | count | share |
|---|---:|---:|
| form4_ticker_history | 41,883 | 93.4% |
| sec_current_ticker | 2,964 | 6.6% |

## By filing year
| year | PTRs | parsed (electronic) | paper scans | in-scope txns | matched |
|---|---:|---:|---:|---:|---:|
| 2014 | 91 | 90 | 0 | 514 | 73.0% |
| 2015 | 851 | 550 | 300 | 3,915 | 63.7% |
| 2016 | 979 | 614 | 363 | 3,606 | 70.1% |
| 2017 | 1,022 | 688 | 334 | 3,909 | 74.3% |
| 2018 | 1,067 | 718 | 349 | 4,239 | 71.3% |
| 2019 | 921 | 698 | 223 | 5,215 | 77.2% |
| 2020 | 914 | 743 | 171 | 7,420 | 80.6% |
| 2021 | 828 | 688 | 140 | 5,081 | 84.3% |
| 2022 | 740 | 605 | 135 | 3,366 | 84.5% |
| 2023 | 584 | 488 | 96 | 4,090 | 82.6% |
| 2024 | 574 | 509 | 65 | 2,717 | 90.8% |
| 2025 | 685 | 595 | 90 | 7,290 | 94.0% |
| 2026 | 620 | 547 | 73 | 4,222 | 87.6% |

## Electronic vs paper filers
504 members filed PTRs: 365 electronic only, 78 paper only,
61 both. 23.7% of all PTRs are paper. The 10 most frequent filers account for
17.6% of PTRs, so a few members drive much of the sample. Members with the highest paper share:

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
| BURR, RICHARD M (Senate) | 63 | 100% |
| MARCHANT, KENNY (TX24) | 60 | 100% |
| FRELINGHUYSEN, RODNEY P. (NJ11) | 58 | 100% |
| UPTON, FRED (MI06) | 58 | 100% |
| POLIS, JARED (CO02) | 56 | 100% |

Paper filers' trades are missing from every result. If they trade differently, the House result
describes electronic filers, not all members.

## Hand audit
`reports/audit/congress_match_audit_sample.csv`: 100 random matched transactions. Fill `audit_correct`.
