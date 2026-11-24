# Pre-registration: copy-the-insiders

**Status: DRAFT, not tagged.** `prereg.yaml` is the authority; this file explains it. Every rule
change made after dev-period returns were first computed (2026-11-15) is listed in the
[Changelog](#changelog) with a reason that does not refer to returns.

## Question
Does a portfolio that copies (a) open-market purchases by corporate officers and directors and
(b) stock purchases disclosed by members of Congress (House and Senate), entered only after the filing is public,
earn a positive risk-adjusted return after costs?

- **Primary metric:** annualized alpha from regressing daily strategy excess returns on the
  Fama-French 5 factors (2x3) plus momentum, with a 6-month block-bootstrap 95% CI, Holm-adjusted
  across the two groups.
- **Descriptive headline:** return vs. SPY total return (what an investor would compare to).
- **Secondary benchmark:** a monthly sector-ETF clone of the strategy's sector weights
  (SIC → Select Sector SPDR mapping; an approximation).

**Decision rule** (on the primary metric, per group): *beats* if the adjusted CI lower bound > 0;
*rules out a 2%+ edge* if the adjusted CI upper bound < 2%; otherwise **inconclusive**, reported
with the minimum detectable alpha, i.e. the size of edge the test could and could not have detected.

## Periods
| Period | Dates | Use |
|---|---|---|
| dev | 2014-01-01 to 2021-12-31 | Build and debug. Congress data starts in 2015, so its dev run starts at its first signal. |
| test | 2022-01-01 to 2026-06-30 | Primary test. Run once, after `cti prereg tag`. |
| forward | 2026-07-01 to 2028-06-30 | Pre-registered secondary test with a fixed end date. |

Honesty note: the test period is already in the past. The tag proves the rules were fixed
before the code computed any test-period returns. It cannot prove I never saw a market chart
from 2022 to 2026. The forward period is the only fully clean test.

## Rules and rationale
- **Entry**: open of the first trading day after the filing date, which is always after the trade
  became public.
- **Insider filters**: officer or director; open-market purchase (code P); at least $10k; not
  under a 10b5-1 plan (SEC checkbox where it exists, footnote text before April 2023); common
  stock only (title excludes preferred, depositary, warrants, notes, funds, rights, units incl.
  MLP units, options); filed at most 30 days after the trade.
- **Congress filters**: House or Senate PTR purchase of a stock (House asset code ST, or no code with a
  ticker on pre-2019 forms; Senate asset type "Stock"), both chambers in one group; filed at most 90 days after the trade; match confidence medium or high.
- **Universe (both)**: last close before entry ≥ $5; market cap ≥ $300M from SEC share counts
  already public at entry; listed on NYSE (incl. American/Arca), Nasdaq, CBOE or TXSE.
- **Portfolio**: equal weight. A new position gets 1/N of NAV, funded from cash first, then pro
  rata from holdings. Weights drift otherwise, and exit proceeds earn T-bills until the next entry
  or month start. Everything resets to equal weight on the first trading day of each month. Cost
  = 10 bps per side on traded value.
- **Exits**, whichever comes first: 126 trading days after entry; the open after a disclosed sale of
  that stock by any of the position's source filers; delisting.
- **One position per ticker**: a repeat buy adds a source filer but doesn't reset the hold clock.

## Sensitivity runs (each changes one thing from the primary)
| Run | Change | Why |
|---|---|---|
| `costs_stress` | 25 bps per side | Cost uncertainty for small caps |
| `hold_63` | 63-day hold | Shorter holding horizon |
| `rebalance_on_entry_or_exit` | Daily reset to equal weight (the original rule) | Shows what the changed rule does |
| `filing_lag_none` | No filing-lag cutoff | Shows what the cutoff removes |
| `10b5_1_footnote_only` (insider) | Footnote text in every period, ignoring the 2023+ checkbox | The same 10b5-1 rule on both sides of the dev/test boundary |
| `confidence_low` (Congress) | Include low-confidence matches | Shows what dropping them changes |
| `weighting_amount_mid` (Congress) | Weight by the midpoint of the disclosed range | Tests whether bigger disclosed trades do better (replaces the low/mid/high sizing check, which did nothing under equal weighting) |
| `bound_minus_100` / `bound_zero` / `bound_benchmark` | Add unmatched purchases priced at −100% / 0% / SPY over the hold | Survivorship bounds (below) |

## Known measurement issues
- **Survivorship (free prices).** yfinance mostly lacks delisted stocks. 59.4% of dev-period insider
  purchases match a priced security vs 83.3% in the test period (47.5% in 2014 rising to 94.6% in
  2026), so the samples are biased differently. **Plan: CRSP via WRDS before the test run.**
  Without it, the survivorship bounds are reported next to every result. They add unmatched
  purchases (no price data, or a ticker listed after the trade), each included with probability
  equal to that year's universe pass rate among matched purchases (seeded), priced at −100%, 0%,
  or SPY. If the conclusion is the same under all three, the bias doesn't change the answer; if it
  flips, the report says so.
- **10b5-1 classification changes at the dev/test boundary.** The SEC checkbox exists only from April
  2023. Footnote text probably misses some plans before that. The report counts how many purchases
  each method flags and where they disagree, and the `10b5_1_footnote_only` run applies one method
  to both periods.
- **House coverage.** About a quarter of House PTRs are paper scans with no text layer (46% in
  2015, about 13% in 2024). They aren't parsed (OCR is future work). Coverage by year is reported in
  `reports/data_quality_congress.md`, so a cleaner recent sample can't stand in silently for the
  full population.
- **Senate coverage.** Senate eFD PTRs (2012 onward) are HTML tables with a ticker column, so they
  parse cleanly; paper scans are a small share and aren't parsed. eFD doesn't link an amendment to
  the report it amends, so amended transactions are deduplicated against the same senator's
  earlier ones (same trade date, ticker or asset, type and amount; earliest filing wins).
- **Ticker reuse.** 5,419 insider purchases (3.5%) map to a ticker whose current history starts after
  the trade (e.g. SHLD: Sears then, a defense ETF now). They are excluded, never mispriced. For
  Congress, tickers are mapped through the issuer's own Form 4 ticker history at the trade date.
- **Reverse splits missing from yfinance** make some real purchases fail the price check (LENZ,
  AZTR, FLNT). They are lost on free data; CRSP fixes this.
- **Sector clone** uses current SIC codes mapped to sector ETFs, an approximation of GICS.

## Power (dev period, primary configuration; recomputed after the changes below)
From `reports/dev_results/SUMMARY*.md`, yfinance prices (survivors only), 4.49-year test period, 80% power.

| Group | Residual vol (FF5+Mom) | Tracking error vs SPY | MDA, factor alpha | MDA, vs SPY | Test CI half-width |
|---|---:|---:|---:|---:|---:|
| insider | 3.70% (R² 0.97) | 11.47% | **4.9% / yr** | 15.2% / yr | ±3.4% |
| Congress (House + Senate) | 3.48% (R² 0.96) | 5.46% | **4.6% / yr** | 7.2% / yr | ±3.2% |

Factor adjustment cuts the minimum detectable effect by about two-thirds for insiders. Their
tracking error vs SPY was mostly size and value exposure (loadings: SMB +0.66, HML +0.29).

**What the test can and cannot show.** It can reliably detect a true factor alpha of about 5%
a year or more. A smaller true edge, such as the 1–3% that much of the literature reports for insider
buying, will probably come out *inconclusive*, and that does **not** mean the edge is absent. The
`rules_out` rule (adjusted CI upper bound < 2%) can only trigger if the estimate comes in below
about −1.3% to −1.4%, i.e. it can rule out a 2% edge only if the strategy actually lost money
after factor adjustment.

**Dev-period results (descriptive, not a test):**
- Insider primary: factor alpha +2.2% a year [95% CI +0.5%, +5.6%]. It doesn't hold up under
  25 bps costs (+1.2% [−0.3%, +5.0%]) or the survivorship bounds (0%: +0.8% [−0.7%, +3.6%];
  SPY: +1.2% [−0.1%, +3.8%]).
- Congress primary (House + Senate): factor alpha −0.4% [−2.4%, +2.3%]. No variant is distinguishable
  from zero. (House alone, before the Senate was added: −0.6% [−3.3%, +1.7%].)
- The −100% bound (every missing company worthless within the hold) wipes out both groups. That's
  a deliberately extreme worst case, not a plausible outcome.

## Decisions still open before tagging
1. **Hand audits** (you): `reports/audit/match_audit_sample.csv` and
   `reports/audit/congress_match_audit_sample.csv`. Report accuracy with a CI (e.g. 97/100, 95% CI 91–99%).
2. **CRSP/WRDS access**, or proceed with the survivorship bounds as the stated limit.
3. **Senate eFD**: included (decided 2026-11-23, see the changelog).
4. **Joint filings**: several reporting owners on one Form 4 count as separate signals for the same
   security (one position). Confirm.

## Changelog
Dev-period returns were first computed on **2026-11-15** (Phase 4). Rules set before that were
fixed without seeing any returns: filing rules, the security-title pattern, price-check thresholds,
minimum price history, the universe filter and its share-count lags, the exchange list.

| Date | Change | Reason (not returns) |
|---|---|---|
| 2026-11-15 | `portfolio.rebalance`: `on_entry_or_exit` → `monthly_drift`; the old rule kept as a sensitivity run | Investability. No real copier re-equalizes a 400-stock book nearly every day; the old rule generated about half of all turnover. The new rule is what a person following these filings could actually run. |
| 2026-11-15 | Primary metric: return vs SPY → FF5 + momentum alpha; SPY kept as the descriptive headline | Power. Most of the 11.8% tracking error vs SPY is size/value exposure, not stock selection. Chosen on residual volatility measured on dev, not on alpha. |
| 2026-11-15 | Forward period given a fixed end (2028-06-30) as a pre-registered secondary test | More out-of-sample data later without loosening the primary test |
| 2026-11-15 | Filing-lag cutoffs: insiders 30 days, Congress 90 days; no-cutoff sensitivity run | Data quality. Form 4 is due in 2 business days, so very late filings are mostly corrections. The STOCK Act allows 45 days, and twice that keeps legitimate late filers. |
| 2026-11-15 | Congress: low-confidence matches dropped from the primary; included in a sensitivity run | Data quality. A wrong-company match (e.g. ENI matched to Endonovo) is worse than a missing one. |
| 2026-11-15 | Congress sizing check `[low, mid, high]` → amount-weighted sensitivity run | The old check had no effect under equal weighting |
| 2026-11-15 | 10b5-1 footnote-only sensitivity run; 10b5-1 and lag filters moved from SQL to the runner (the same candidates for every run) | Measurement consistency across the dev/test boundary |
| 2026-11-15 | Survivorship-bound runs (−100% / 0% / SPY) | Coverage differs between periods. Shows the bias rather than hiding it. |
| 2026-11-15 | Confirmed: MLP units excluded for both groups; exchanges NYSE (the SEC map includes American/Arca under "NYSE"), Nasdaq, CBOE, TXSE | Different tax and legal structure from common stock; the same rule for both groups |
| 2026-11-15 | Sector clone connected as the secondary benchmark (SIC → sector ETF) | It was specified in the original plan but not yet built |
| 2026-11-23 | Senate PTRs added to the Congress group (`groups.congress.chambers: [house, senate]`), one group with the House; Holm still over two groups | Coverage. The Senate data became available; the original question is about Congress, not one chamber. Merging keeps the number of tests (and so the power) unchanged. Decided before any Senate returns were computed. |
