# copy-the-insiders

**Question.** If you had copied every open-market purchase by corporate insiders, or by members
of Congress, the day after it became public, would you have beaten the market after costs?

**Answer.** Not yet known. The rules are pre-registered in [`prereg/prereg.yaml`](prereg/prereg.yaml)
and the test period is code-locked until that file is tagged.

## Run it
SEC requires a contact User-Agent. In PowerShell: `$env:SEC_USER_AGENT = "Your Name you@example.com"`;
in bash: `export SEC_USER_AGENT="Your Name you@example.com"`. Then:
```bash
uv sync
```
```bash
uv run cti all
```
`cti all` is the same as `make all`: ingest Form 4 data, build tables, run tests. Use
`uv run cti all --skip-ingest` to rebuild from data already downloaded.

| Command | What it does |
|---|---|
| `cti ingest form4 --start 2014Q1 --end 2026Q2` | Download SEC insider datasets to `data/raw` (with checksums) and stage them as Parquet |
| `cti build` | Run the SQL models in `src/cti/sql` into `data/warehouse.duckdb` |
| `cti ingest reference` | Treasury bills, SEC CIK→ticker map, SPY + 11 sector ETFs |
| `cti ingest prices` | Prices for every ticker the candidates could map to (only new tickers unless `--refetch`) |
| `cti resolve` | Match candidates to securities; writes `calendar`, `securities`, `signal_resolution`, `prices_daily`, `reference_returns` and `reports/data_quality.md` |
| `cti prereg hash` | Print the config hash |
| `cti prereg tag` | Commit and tag the pre-registration (`prereg-v1`); then `git push --tags` |
| `cti run --period dev` | Dev-period backtest (Phase 4) |
| `cti run --period test --final` | The one-time test run; refuses unless the config matches the tag |

## Status
- [x] Phase 0: repo, config, lock, CI
- [x] Phase 1 (partial): Form 4 downloader and staging; core SQL models
- [x] Phase 2: prices (yfinance prototype), SPY + sector ETFs, Treasury bills, trading calendar,
      CIK/ticker resolution with confidence + price check, `reports/data_quality.md`
- [x] Phase 3: backtest engine with hand-calculated fixture tests and a look-ahead test
- [ ] Phase 2 follow-up: hand-audit `reports/audit/match_audit_sample.csv`; full 2014–2026 ingest
- [ ] Phases 4–7

## Limits
See [`prereg/PREREG.md`](prereg/PREREG.md#known-measurement-issues-record-before-the-test-run).
