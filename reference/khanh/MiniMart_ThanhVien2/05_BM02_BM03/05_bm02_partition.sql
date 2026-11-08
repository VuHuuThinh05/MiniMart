CREATE SCHEMA IF NOT EXISTS bench;

DO $$
BEGIN
    IF to_regclass('bench.sales_plain') IS NULL THEN
        RAISE EXCEPTION 'Chua co bench.sales_plain. Can chay buoc 13.1 truoc.';
    END IF;
END $$;

DROP INDEX IF EXISTS bench.sales_plain_store_idx;
DROP INDEX IF EXISTS bench.sales_plain_store_day_idx;

DROP TABLE IF EXISTS bench.sales_partitioned CASCADE;

CREATE TABLE bench.sales_partitioned (
    sale_id BIGINT NOT NULL,
    store_key BIGINT NOT NULL,
    source_day INTEGER NOT NULL,
    sales_value NUMERIC(18,2) NOT NULL
) PARTITION BY RANGE (source_day);

DO $$
DECLARE
    k INTEGER;
BEGIN
    FOR k IN 0..12 LOOP
        EXECUTE format(
            'CREATE TABLE bench.sales_p_%s PARTITION OF bench.sales_partitioned FOR VALUES FROM (%s) TO (%s)',
            k + 1,
            k * 28 + 1,
            (k + 1) * 28 + 1
        );
    END LOOP;
END $$;

INSERT INTO bench.sales_partitioned (sale_id, store_key, source_day, sales_value)
SELECT sale_id, store_key, source_day, sales_value
FROM bench.sales_plain;

ANALYZE bench.sales_plain;
ANALYZE bench.sales_partitioned;

DROP TABLE IF EXISTS bench.bm02_runs;

CREATE TABLE bench.bm02_runs (
    model TEXT NOT NULL,
    run_no INTEGER NOT NULL,
    execution_ms NUMERIC NOT NULL,
    plan JSONB NOT NULL,
    PRIMARY KEY (model, run_no)
);

DO $$
DECLARE
    p JSON;
    m TEXT;
    i INTEGER;
BEGIN
    FOR i IN 0..5 LOOP
        FOREACH m IN ARRAY ARRAY['plain', 'partitioned'] LOOP
            IF m = 'plain' THEN
                EXECUTE 'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT SUM(sales_value) FROM bench.sales_plain WHERE store_key = 7 AND source_day BETWEEN 85 AND 112' INTO p;
            ELSE
                EXECUTE 'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT SUM(sales_value) FROM bench.sales_partitioned WHERE store_key = 7 AND source_day BETWEEN 85 AND 112' INTO p;
            END IF;
            IF i > 0 THEN
                INSERT INTO bench.bm02_runs (model, run_no, execution_ms, plan)
                VALUES (m, i, (p->0->>'Execution Time')::NUMERIC, p::JSONB);
            END IF;
        END LOOP;
    END LOOP;
END $$;

SELECT
    model,
    COUNT(*) AS so_luot,
    ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY execution_ms))::NUMERIC, 3) AS trung_vi_ms,
    ROUND(MIN(execution_ms), 3) AS nho_nhat_ms,
    ROUND(MAX(execution_ms), 3) AS lon_nhat_ms
FROM bench.bm02_runs
GROUP BY model
ORDER BY model;

SELECT
    (SELECT COUNT(*) FROM bench.sales_plain) AS dong_plain,
    (SELECT COUNT(*) FROM bench.sales_partitioned) AS dong_partitioned,
    (SELECT SUM(sales_value) FROM bench.sales_plain) AS tien_plain,
    (SELECT SUM(sales_value) FROM bench.sales_partitioned) AS tien_partitioned,
    (SELECT COUNT(*) FROM pg_inherits WHERE inhparent = 'bench.sales_partitioned'::regclass) AS so_phan_vung;
