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
| Group | Tracking error (ann.) | MDA at 80% power |
|---|---|---|
| insider | TBD | TBD |
| congress | TBD | TBD |
