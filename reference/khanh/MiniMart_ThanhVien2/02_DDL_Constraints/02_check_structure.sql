SELECT current_database() AS database_dang_dung, version() AS phien_ban_postgresql;

SELECT schemaname AS schema_name, tablename AS table_name
FROM pg_tables
WHERE schemaname = 'dw'
ORDER BY schemaname, tablename;

SELECT COUNT(*) AS so_bang_dw_ky_vong_12
FROM pg_tables WHERE schemaname = 'dw';

SELECT table_name,
       COUNT(*) FILTER (WHERE constraint_type = 'PRIMARY KEY') AS so_pk,
       COUNT(*) FILTER (WHERE constraint_type = 'FOREIGN KEY') AS so_fk,
       COUNT(*) FILTER (WHERE constraint_type = 'UNIQUE') AS so_unique
FROM information_schema.table_constraints
WHERE table_schema = 'dw'
GROUP BY table_name
ORDER BY table_name;

SELECT 'fact_sales' AS fact, COUNT(*) AS rows FROM dw.fact_sales
UNION ALL SELECT 'fact_campaign_contact', COUNT(*) FROM dw.fact_campaign_contact
UNION ALL SELECT 'fact_coupon_redemption', COUNT(*) FROM dw.fact_coupon_redemption
UNION ALL SELECT 'fact_promotion', COUNT(*) FROM dw.fact_promotion;
