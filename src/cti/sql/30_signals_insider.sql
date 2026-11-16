-- signals_insider_candidates: insider purchases that pass the pre-registered filing rules.
-- Every threshold comes from prereg.yaml via {placeholders}; nothing is hard-coded here.
--
-- The 10b5-1 exclusion and the filing-lag cutoff are NOT applied here: they are carried as flags
-- and applied by the backtest runner, so their sensitivity variants (footnote-only 10b5-1
-- classification in every period; no lag cutoff) use exactly the same candidate set.
CREATE OR REPLACE TABLE signals_insider_candidates AS
SELECT
    txn_id,
    filing_id,
    filer_id,
    issuer_cik,
    issuer_ticker,
    issuer_name,
    security_title,
    trade_date,
    price                     AS reported_price,
    filed_date                AS public_date,
    value_point,
    is_10b5_1,                                   -- primary: checkbox where it exists, else footnote
    footnote_mentions_10b5_1,                    -- sensitivity: footnote text only, every period
    aff_10b5_1_flag,
    is_10b5_1_method,
    date_diff('day', trade_date, filed_date) AS filing_lag_days
FROM core_transactions
WHERE code IN ({insider_codes})
  AND (({insider_officer} AND is_officer) OR ({insider_director} AND is_director))
  AND value_point >= {insider_min_value_usd}
  AND NOT regexp_matches(lower(coalesce(security_title, '')), '{insider_title_exclude}');
