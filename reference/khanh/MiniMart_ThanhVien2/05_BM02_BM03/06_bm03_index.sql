DROP INDEX IF EXISTS bench.sales_plain_store_idx;
DROP INDEX IF EXISTS bench.sales_plain_store_day_idx;

ANALYZE bench.sales_plain;

DROP TABLE IF EXISTS bench.bm03_runs;

CREATE TABLE bench.bm03_runs (
    model TEXT NOT NULL,
    run_no INTEGER NOT NULL,
    execution_ms NUMERIC NOT NULL,
    plan JSONB NOT NULL,
    PRIMARY KEY (model, run_no)
);

DO $$
DECLARE
    p JSON;
    i INTEGER;
BEGIN
    FOR i IN 0..5 LOOP
        EXECUTE 'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT SUM(sales_value) FROM bench.sales_plain WHERE store_key = 7 AND source_day BETWEEN 85 AND 112' INTO p;
        IF i > 0 THEN
            INSERT INTO bench.bm03_runs VALUES ('no_index', i, (p->0->>'Execution Time')::NUMERIC, p::JSONB);
        END IF;
    END LOOP;
END $$;

CREATE INDEX sales_plain_store_idx ON bench.sales_plain (store_key);
ANALYZE bench.sales_plain;

DO $$
DECLARE
    p JSON;
    i INTEGER;
BEGIN
    FOR i IN 0..5 LOOP
        EXECUTE 'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT SUM(sales_value) FROM bench.sales_plain WHERE store_key = 7 AND source_day BETWEEN 85 AND 112' INTO p;
        IF i > 0 THEN
            INSERT INTO bench.bm03_runs VALUES ('single_index', i, (p->0->>'Execution Time')::NUMERIC, p::JSONB);
        END IF;
    END LOOP;
END $$;

DROP INDEX bench.sales_plain_store_idx;

CREATE INDEX sales_plain_store_day_idx ON bench.sales_plain (store_key, source_day);
ANALYZE bench.sales_plain;

DO $$
DECLARE
    p JSON;
    i INTEGER;
BEGIN
    FOR i IN 0..5 LOOP
        EXECUTE 'EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT SUM(sales_value) FROM bench.sales_plain WHERE store_key = 7 AND source_day BETWEEN 85 AND 112' INTO p;
        IF i > 0 THEN
            INSERT INTO bench.bm03_runs VALUES ('composite_index', i, (p->0->>'Execution Time')::NUMERIC, p::JSONB);
        END IF;
    END LOOP;
END $$;

SELECT
    model,
    COUNT(*) AS so_luot,
    ROUND((PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY execution_ms))::NUMERIC, 3) AS trung_vi_ms,
    ROUND(MIN(execution_ms), 3) AS nho_nhat_ms,
    ROUND(MAX(execution_ms), 3) AS lon_nhat_ms
FROM bench.bm03_runs
GROUP BY model
ORDER BY CASE model
    WHEN 'no_index' THEN 1
    WHEN 'single_index' THEN 2
    WHEN 'composite_index' THEN 3
END;

SELECT
    indexname,
    pg_size_pretty(pg_relation_size((schemaname || '.' || indexname)::REGCLASS)) AS kich_thuoc
FROM pg_indexes
WHERE schemaname = 'bench'
    AND tablename = 'sales_plain'
ORDER BY indexname;
