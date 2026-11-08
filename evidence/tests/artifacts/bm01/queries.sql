-- Direct
SELECT week_no,department,SUM(sales_value) AS sales_value,COUNT(DISTINCT basket_id) AS baskets FROM bench.sales_snapshot GROUP BY week_no,department ORDER BY week_no,department;
-- Materialized
SELECT week_no,department,sales_value,baskets FROM bench.sales_week_department ORDER BY week_no,department;
