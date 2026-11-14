-- core_transactions: non-derivative Form 4 transactions, one row per (transaction, reporting owner).
--
-- Duplicates and amendments: a 4/A usually restates transactions already reported. A transaction
-- is identified by (owner, issuer, trade date, code, shares, price). We keep the EARLIEST filing
-- that reported it, because that is when it became public; later restatements are flagged as
-- duplicates in core_transactions_dropped, not deleted silently.
CREATE OR REPLACE TABLE _txn_all AS
WITH owners AS (
    SELECT DISTINCT
        ACCESSION_NUMBER,
        RPTOWNERCIK                                         AS filer_id,
        RPTOWNERNAME                                        AS filer_name,
        coalesce(RPTOWNER_RELATIONSHIP, '')                 AS relationship,
        RPTOWNER_TITLE                                      AS filer_title
    FROM read_parquet('{staging}/form4/REPORTINGOWNER/*.parquet', union_by_name = true)
),
footnote_10b5_1 AS (
    SELECT DISTINCT ACCESSION_NUMBER
    FROM read_parquet('{staging}/form4/FOOTNOTES/*.parquet', union_by_name = true)
    WHERE regexp_matches(lower(FOOTNOTE_TXT), '10b5\s*-?\s*1')
),
nd AS (
    SELECT DISTINCT ON (ACCESSION_NUMBER, NONDERIV_TRANS_SK)
        ACCESSION_NUMBER,
        NONDERIV_TRANS_SK,
        SECURITY_TITLE,
        CAST(TRANS_DATE AS DATE)                            AS trade_date,
        TRANS_CODE                                          AS code,
        TRANS_ACQUIRED_DISP_CD                              AS acq_disp,
        TRY_CAST(TRANS_SHARES AS DOUBLE)                    AS shares,
        TRY_CAST(TRANS_PRICEPERSHARE AS DOUBLE)             AS price
    FROM read_parquet('{staging}/form4/NONDERIV_TRANS/*.parquet', union_by_name = true)
)
SELECT
    f.filing_id || ':' || nd.NONDERIV_TRANS_SK || ':' || o.filer_id   AS txn_id,
    f.filing_id,
    f.filed_date,
    f.is_amendment,
    f.issuer_cik,
    f.issuer_ticker,
    f.issuer_name,
    o.filer_id,
    o.filer_name,
    o.filer_title,
    contains(lower(o.relationship), 'officer')              AS is_officer,
    contains(lower(o.relationship), 'director')             AS is_director,
    nd.SECURITY_TITLE                                       AS security_title,
    nd.trade_date,
    nd.code,
    CASE WHEN nd.code = 'P' THEN 'buy' WHEN nd.code = 'S' THEN 'sell' END AS side,
    nd.shares,
    nd.price,
    nd.shares * nd.price                                    AS value_point,
    f.aff_10b5_1_flag,
    (fn.ACCESSION_NUMBER IS NOT NULL)                       AS footnote_mentions_10b5_1,
    coalesce(f.aff_10b5_1_flag, FALSE) OR (fn.ACCESSION_NUMBER IS NOT NULL) AS is_10b5_1,
    CASE
        WHEN f.aff_10b5_1_flag IS NOT NULL THEN 'checkbox'
        WHEN fn.ACCESSION_NUMBER IS NOT NULL THEN 'footnote'
        ELSE 'none'
    END                                                     AS is_10b5_1_method
FROM nd
JOIN core_filings f ON f.filing_id = nd.ACCESSION_NUMBER
JOIN owners o ON o.ACCESSION_NUMBER = nd.ACCESSION_NUMBER
LEFT JOIN footnote_10b5_1 fn ON fn.ACCESSION_NUMBER = nd.ACCESSION_NUMBER;

CREATE OR REPLACE TABLE core_transactions AS
SELECT * EXCLUDE (dup_rank) FROM (
    SELECT *, row_number() OVER (
        PARTITION BY filer_id, issuer_cik, trade_date, code, shares, price
        ORDER BY filed_date, is_amendment, filing_id) AS dup_rank
    FROM _txn_all
) WHERE dup_rank = 1;

CREATE OR REPLACE TABLE core_transactions_dropped AS
SELECT a.*, 'duplicate_of_earlier_filing' AS drop_reason
FROM _txn_all a ANTI JOIN core_transactions c USING (txn_id);

DROP TABLE _txn_all;
