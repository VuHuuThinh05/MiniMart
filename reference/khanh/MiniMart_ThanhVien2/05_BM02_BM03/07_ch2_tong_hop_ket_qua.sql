SELECT
    current_database() AS database_name,
    current_setting('server_version') AS postgres_version,
    (SELECT COUNT(*) FROM pg_tables WHERE schemaname = 'dw') AS so_bang_dw,
    (SELECT COUNT(*)
     FROM pg_constraint c
     JOIN pg_namespace n ON n.oid = c.connamespace
     WHERE n.nspname = 'dw' AND c.contype = 'p') AS so_khoa_chinh,
    (SELECT COUNT(*)
     FROM pg_constraint c
     JOIN pg_namespace n ON n.oid = c.connamespace
     WHERE n.nspname = 'dw' AND c.contype = 'f') AS so_khoa_ngoai,
    (SELECT COUNT(*) FROM pg_inherits
     WHERE inhparent = 'bench.sales_partitioned'::regclass) AS so_phan_vung;

SELECT
    (SELECT COUNT(*) FROM bench.sales_plain) AS dong_bang_thuong,
    (SELECT COUNT(*) FROM bench.sales_partitioned) AS dong_bang_phan_vung,
    (SELECT SUM(sales_value) FROM bench.sales_plain) AS doanh_so_bang_thuong,
    (SELECT SUM(sales_value) FROM bench.sales_partitioned) AS doanh_so_bang_phan_vung,
    CASE
        WHEN (SELECT COUNT(*) FROM bench.sales_plain)
           = (SELECT COUNT(*) FROM bench.sales_partitioned)
         AND (SELECT SUM(sales_value) FROM bench.sales_plain)
           = (SELECT SUM(sales_value) FROM bench.sales_partitioned)
        THEN 'PASS'
        ELSE 'FAIL'
    END AS doi_soat;

SELECT
    'BM02' AS bai_do,
    model AS cau_hinh,
    COUNT(*) AS so_luot,
    ROUND(
        (PERCENTILE_CONT(0.5)
         WITHIN GROUP (ORDER BY execution_ms))::NUMERIC, 3
    ) AS trung_vi_ms,
    ROUND(MIN(execution_ms), 3) AS nho_nhat_ms,
    ROUND(MAX(execution_ms), 3) AS lon_nhat_ms
FROM bench.bm02_runs
GROUP BY model

UNION ALL

SELECT
    'BM03' AS bai_do,
    model AS cau_hinh,
    COUNT(*) AS so_luot,
    ROUND(
        (PERCENTILE_CONT(0.5)
         WITHIN GROUP (ORDER BY execution_ms))::NUMERIC, 3
    ) AS trung_vi_ms,
    ROUND(MIN(execution_ms), 3) AS nho_nhat_ms,
    ROUND(MAX(execution_ms), 3) AS lon_nhat_ms
FROM bench.bm03_runs
GROUP BY model
ORDER BY bai_do, cau_hinh;
