-- signals_insider_candidates: insider purchases that pass the pre-registered filing rules.
-- Every threshold comes from prereg.yaml via {placeholders}; nothing is hard-coded here.
-- Security resolution, the universe filter and entry dates (trading calendar) are applied in
-- Phase 2 / 40_universe_filters.sql once prices and the calendar exist.
CREATE OR REPLACE TABLE signals_insider_candidates AS
SELECT
    txn_id,
    filing_id,
    filer_id,
    issuer_cik,
    issuer_ticker,
    trade_date,
    filed_date                AS public_date,
    value_point,
    is_10b5_1_method
FROM core_transactions
WHERE code IN ({insider_codes})
  AND (({insider_officer} AND is_officer) OR ({insider_director} AND is_director))
  AND (NOT {insider_exclude_10b5_1} OR NOT is_10b5_1)
  AND value_point >= {insider_min_value_usd};
