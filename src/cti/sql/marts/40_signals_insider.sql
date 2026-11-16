-- signals_insider: matched insider purchases with the pre-registered universe filter applied.
-- Every value known at decision time only: price = last close BEFORE entry; shares = latest
-- cover-page count dated at least {shares_lag_days} days before entry.
-- Rows failing the universe are kept with universe_reason so nothing disappears silently.
CREATE OR REPLACE TABLE signals_insider_all AS
WITH m AS (
    SELECT r.*, s.exchange
    FROM signal_resolution r JOIN securities s USING (security_id)
    WHERE r.matched
),
px AS (
    SELECT ticker, date, close_nominal FROM prices_daily
),
shares AS (
    -- cover-page count, or (fallback) weighted-average basic shares from the 10-Q/10-K, which is
    -- published later, hence the longer lag. ASOF takes the latest one already public.
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

CREATE OR REPLACE TABLE signals_insider AS
SELECT a.txn_id AS signal_id, 'buy' AS side, a.security_id, c.filer_id, a.public_date, a.entry_date,
       a.trade_date, c.filing_lag_days, c.is_10b5_1, c.footnote_mentions_10b5_1, c.aff_10b5_1_flag,
       a.ticker, a.issuer_name, c.value_point, a.mcap_usd, a.match_confidence
FROM signals_insider_all a
JOIN signals_insider_candidates c USING (txn_id)
WHERE universe_reason IS NULL OR (universe_reason = 'mcap_unknown' AND '{mcap_unknown}' = 'include');

-- Open-market sales by any filer who has a buy signal, for early exit. 10b5-1 sales count:
-- a sale is a sale. Entry = next trading day after the filing date, like buys.
CREATE OR REPLACE TABLE signals_insider_sells AS
WITH s AS (
    SELECT t.txn_id, 'cik:' || t.issuer_cik AS security_id, t.filer_id,
           CAST(t.filed_date AS TIMESTAMP) AS public_date
    FROM core_transactions t
    SEMI JOIN (SELECT DISTINCT filer_id, security_id FROM signals_insider) b
        ON b.filer_id = t.filer_id AND b.security_id = 'cik:' || t.issuer_cik
    WHERE t.code = 'S'
)
SELECT s.txn_id AS signal_id, 'sell' AS side, s.security_id, s.filer_id, s.public_date,
       c.date AS entry_date
FROM s ASOF JOIN calendar c ON s.public_date < c.date;
