SELECT 'dw_tables' AS check_name,
       COUNT(*) AS actual_count,
       CASE WHEN COUNT(*) = 12 THEN 'PASS' ELSE 'FAIL' END AS result
FROM pg_tables WHERE schemaname = 'dw';

SELECT 'fact_sales_lineage' AS check_name,
       COUNT(*) AS invalid_groups
FROM (
    SELECT file_id, source_row_no
    FROM dw.fact_sales
    GROUP BY file_id, source_row_no HAVING COUNT(*) > 1
) q
UNION ALL
SELECT 'campaign_contact_grain', COUNT(*) FROM (
    SELECT household_id, campaign_key
    FROM dw.fact_campaign_contact
    GROUP BY household_id, campaign_key HAVING COUNT(*) > 1
) q
UNION ALL
SELECT 'coupon_redemption_lineage', COUNT(*) FROM (
    SELECT file_id, source_row_no
    FROM dw.fact_coupon_redemption
    GROUP BY file_id, source_row_no HAVING COUNT(*) > 1
) q
UNION ALL
SELECT 'promotion_grain', COUNT(*) FROM (
    SELECT product_key, store_key, week_key, display_code, mailer_code
    FROM dw.fact_promotion
    GROUP BY product_key, store_key, week_key, display_code, mailer_code
    HAVING COUNT(*) > 1
) q
UNION ALL
SELECT 'coupon_product_grain', COUNT(*) FROM (
    SELECT coupon_key, product_key
    FROM dw.bridge_coupon_product
    GROUP BY coupon_key, product_key HAVING COUNT(*) > 1
) q;

SELECT COUNT(*) AS so_cap_chong_lan
FROM dw.dim_household a
JOIN dw.dim_household b
  ON a.household_id = b.household_id
 AND a.household_key < b.household_key
 AND a.effective_from_day < COALESCE(b.effective_to_day, 2147483647)
 AND b.effective_from_day < COALESCE(a.effective_to_day, 2147483647);

SELECT COUNT(*) AS so_ho_nhieu_phien_ban_current
FROM (
    SELECT household_id
    FROM dw.dim_household
    WHERE is_current
    GROUP BY household_id HAVING COUNT(*) > 1
) q;
