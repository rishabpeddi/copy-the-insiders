# Pre-registration: copy-the-insiders

**Status: DRAFT, not tagged.** `prereg.yaml` is the authority; this file explains it.

## Question
Does a portfolio that copies (a) open-market purchases by corporate officers/directors and
(b) stock purchases disclosed by members of Congress, entered only after the filing is public,
beat SPY total return and a sector-matched ETF clone after costs?

## Periods
| Period | Dates | Use |
|---|---|---|
| dev | 2014-01-01 to 2021-12-31 | Build and debug. Rules may change here. |
| test | 2022-01-01 to 2026-06-30 | Run once, after `cti prereg tag`. |
| forward | 2026-07-01 onward | Truly out of sample, updated monthly. |

Honesty note: the test period is already in the past. The tag proves the rules were fixed
before the code computed any test-period returns. It cannot prove I never saw a market chart
from 2022 to 2026. The forward period is the only fully clean test.

## Rules and rationale
- **Entry**: open of the first trading day after the filing date. That is always after the
  trade became public, and it avoids fetching EDGAR acceptance timestamps.
- **Rebalancing**: back to equal weight on any day a position opens or closes. Cost =
  bps × turnover, where turnover = Σ|target − current| computed on pre-cost equity; the cost is
  then taken pro rata from the new targets.
- **Exits**: whichever comes first: (1) the open `hold_trading_days` trading days after entry,
  (2) the open after a sale by any source filer of that position is disclosed, or (3) delisting
  (the delisting return is applied at that day's close).
- **One position per ticker**: a repeat buy while the ticker is held adds that filer to the
  position's sources but does not reset the hold clock.
- **Cash** earns the T-bill return.

## Known measurement issues (record before the test run)
- The SEC's structured `AFF10B5ONE` flag only exists for filings since the April 2023 rule.
  Before that, the 10b5-1 exclusion relies on searching footnote text for "10b5-1", which
  misses some plans. Report how many purchases each method excludes.
- Free price data mostly leaves out delisted stocks. Final results must use CRSP or a vendor
  that includes delistings, or disclose the bias and estimate its size.
  **Measured (full 2014–2026 ingest, yfinance):** 59.4% of dev-period purchases match a priced
  security vs 83.3% in the test period (47.5% in 2014 up to 94.6% in 2026). The missing
  companies are disproportionately ones that later delisted, so the dev sample is tilted toward
  survivors more than the test sample. On free data, dev and test results are not comparable.
- Ticker reuse is common. 5,419 purchases (3.5%) map to a ticker whose current price history
  starts after the trade (e.g. SHLD: Sears Holdings then, a defense ETF since 2023). These are
  excluded as `entry_before_price_history`, never priced with the wrong company.

## Open decisions to settle before tagging
Found by ingesting 2024Q1 for real (2,015 candidate purchases across 688 issuers that quarter):
1. **Late filings.** Some purchases are filed years after the trade (the oldest trade date in
   2024Q1 is 2019-06-07). Form 4 is due within 2 business days. Proposal: add
   `groups.insider.max_filing_lag_days: 30` and drop older trades.
2. **Obvious data-entry errors.** One MYCB purchase computes to $3.6 trillion (shares × price).
   Phase 2 now compares each reported price with that day's quoted close (`resolution` in
   prereg.yaml): beyond 2x either way is unmatched as `price_mismatch`, and within ±25% earns
   medium/high confidence. **Review these two numbers.** Note that the price check does not catch a
   wrong *share count*, so a value cap or a check against shares outstanding may still be needed.
4. **Non-common securities.** Preferred, depositary, warrant, unit and fund purchases are now
   excluded by `security_title_exclude_regex` (67 of 2,015 candidates in 2024Q1). Review the pattern.
   It also drops MLP "common units"; keep or allow them?
5. **Funds and OTC listings.** Some issuers are funds (e.g. TAKMX) or trade OTC. The
   `us_listed_common` universe filter (Phase 4) should require an exchange of NYSE, Nasdaq or
   NYSE American from the SEC ticker map. Confirm that list.
6. **Reverse splits missing from yfinance.** Several real purchases fail the price check because
   yfinance has no record of the split (LENZ, AZTR, FLNT, STME, DHY). This goes away with CRSP;
   with free data, those signals are lost (conservative, but they're the small caps).
3. **Multiple owners on one filing.** Joint filings list several reporting owners for one trade.
   They currently count as separate signals (same security, so one position). Confirm that's intended.

## Minimum detectable alpha (fill in after Phase 4/5 dev runs, before tagging)
| Group | Tracking error (ann.) | MDA at 80% power (4.5-year test) |
|---|---|---|
| insider | 11.8% (dev, base, yfinance) | **15.6% / year** |
| congress | TBD | TBD |

**What this means.** With an 11.8% tracking error, a 4.5-year test can only reliably detect an
alpha of about 16% a year. A realistic insider-buying alpha of a few percent a year will almost
certainly come out *inconclusive*, and the `rules_out` rule (`adj_ci_high < 0.02`) needs a CI
about ±2% wide, which this test cannot produce. Options to decide **before tagging**:
1. Accept that "inconclusive" is the likely outcome and say so up front (valid, honest).
2. Lower tracking error with a closer benchmark: an equal-weight or small/mid-cap index, or the
   sector clone, instead of SPY as the primary. (Dev: beta 1.13, ~360 mostly small/mid stocks.)
3. Weight positions by signal strength or cap the number of names. Fewer names usually
   *raises* tracking error, though, so this rarely helps power.
4. Lengthen the evaluation by counting the forward period too (from 2026-07-01).

Dev results (not a test of anything): CAGR 14.4% vs SPY 14.7%; active return +0.9%/yr
[95% CI −5.6%, +9.8%]; beta-adjusted alpha −1.0%/yr; 25 bps costs turn both negative.
Full table: `reports/dev_results/SUMMARY.md`.
Turnover is 8.9× a year, about half of it from re-equalizing weights on every entry/exit day
(nearly every day). That's the pre-registered rule working as written; it costs ~0.9%/yr at 10 bps.
