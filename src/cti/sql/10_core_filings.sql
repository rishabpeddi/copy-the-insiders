-- core_filings: one row per Form 4 / 4-A accession.
-- Input: staging SUBMISSION parquet. A filing that appears in two quarterly files keeps its first.
CREATE OR REPLACE TABLE core_filings AS
SELECT
    ACCESSION_NUMBER                                       AS filing_id,
    'form4'                                                AS source,
    ISSUERCIK                                              AS issuer_cik,
    nullif(upper(trim(ISSUERTRADINGSYMBOL)), '')           AS issuer_ticker,
    ISSUERNAME                                             AS issuer_name,
    CAST(FILING_DATE AS DATE)                              AS filed_date,
    CAST(PERIOD_OF_REPORT AS DATE)                         AS period_of_report,
    DOCUMENT_TYPE                                          AS document_type,
    DOCUMENT_TYPE = '4/A'                                  AS is_amendment,
    -- The 10b5-1 checkbox exists only in filings after the April 2023 rule change.
    CASE upper(trim(CAST(AFF10B5ONE AS VARCHAR)))
        WHEN '1' THEN TRUE WHEN 'TRUE' THEN TRUE
        WHEN '0' THEN FALSE WHEN 'FALSE' THEN FALSE
    END                                                    AS aff_10b5_1_flag,
    QUARTER                                                AS raw_ref
FROM read_parquet('{staging}/form4/SUBMISSION/*.parquet', union_by_name = true)
WHERE DOCUMENT_TYPE IN ('4', '4/A')
QUALIFY row_number() OVER (PARTITION BY ACCESSION_NUMBER ORDER BY QUARTER) = 1;
