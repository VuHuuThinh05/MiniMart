CREATE SCHEMA IF NOT EXISTS bench;

CREATE TABLE IF NOT EXISTS bench.sales_plain (
    sale_id BIGINT NOT NULL,
    store_key BIGINT NOT NULL,
    source_day INTEGER NOT NULL,
    sales_value NUMERIC(18,2) NOT NULL
);

TRUNCATE TABLE bench.sales_plain;

INSERT INTO bench.sales_plain (
    sale_id,
    store_key,
    source_day,
    sales_value
)
SELECT
    i,
    (i % 50) + 1,
    (i % 364) + 1,
    ((i % 5000) + 100)::NUMERIC / 100
FROM generate_series(1, 520000) AS gs(i);

ANALYZE bench.sales_plain;

SELECT
    COUNT(*) AS so_dong,
    MIN(source_day) AS ngay_dau,
    MAX(source_day) AS ngay_cuoi
FROM bench.sales_plain;
