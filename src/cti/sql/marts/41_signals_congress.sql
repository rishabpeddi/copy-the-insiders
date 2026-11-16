-- signals_congress: matched House member stock purchases with the same pre-registered universe
-- filter as insiders (price and market cap known before entry; allowed exchanges).
-- Skipped cleanly if congress_resolution hasn't been built yet (see cti/build.py).
CREATE OR REPLACE TABLE signals_congress_all AS
WITH m AS (
    SELECT r.*, e.exchange
    FROM congress_resolution r
    LEFT JOIN sec_exchange e ON e.cik = r.issuer_cik
    WHERE r.matched AND r.txn_type = 'P'
),
px AS (SELECT ticker, date, close_nominal FROM prices_daily),
shares AS (
    SELECT cik, kind AS shares_kind, "end" AS shares_date, shares,
           "end" + CASE kind WHEN 'cover' THEN INTERVAL {shares_lag_days} DAY
                             ELSE INTERVAL {shares_fallback_lag_days} DAY END AS available
    FROM read_parquet('{staging}/sec_shares.parquet')
),
with_px AS (
    SELECT m.*, px.close_nominal AS prior_close, px.date AS prior_close_date
    FROM m ASOF LEFT JOIN px ON m.ticker = px.ticker AND m.entry_date > px.date
),
with_sh AS (
    SELECT w.*, sh.shares, sh.shares_date, sh.shares_kind
    FROM with_px w ASOF LEFT JOIN shares sh ON w.issuer_cik = sh.cik AND w.entry_date > sh.available
)
SELECT
    *,
    CASE WHEN date_diff('day', shares_date, entry_date) <= {shares_max_age_days}
         THEN shares * prior_close END AS mcap_usd,
    CASE
        WHEN exchange IS NULL OR exchange NOT IN ({exchanges})             THEN 'exchange_not_allowed'
        WHEN prior_close IS NULL OR prior_close < {min_price}              THEN 'price_below_min'
        WHEN shares IS NULL OR date_diff('day', shares_date, entry_date) > {shares_max_age_days}
                                                                           THEN 'mcap_unknown'
        WHEN shares * prior_close < {min_mcap_usd}                         THEN 'mcap_below_min'
    END AS universe_reason
FROM with_sh;

CREATE OR REPLACE TABLE signals_congress AS
SELECT txn_id AS signal_id, 'buy' AS side, security_id, filer_id, public_date, entry_date,
       ticker, issuer_name, amount_low, amount_high,
       CASE WHEN amount_high IS NULL THEN amount_low ELSE (amount_low + amount_high) / 2 END AS amount_mid,
       mcap_usd, match_confidence
FROM signals_congress_all
WHERE universe_reason IS NULL OR (universe_reason = 'mcap_unknown' AND '{mcap_unknown}' = 'include');

-- Sales by the same member (household) of a held security trigger early exit, like insiders.
CREATE OR REPLACE TABLE signals_congress_sells AS
SELECT r.txn_id AS signal_id, 'sell' AS side, r.security_id, r.filer_id, r.public_date, r.entry_date
FROM congress_resolution r
SEMI JOIN (SELECT DISTINCT filer_id, security_id FROM signals_congress) b
    ON b.filer_id = r.filer_id AND b.security_id = r.security_id
WHERE r.matched AND r.txn_type = 'S';
