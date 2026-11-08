-- Read-only examples; same published marts as Streamlit.
-- Sales totals: distinct baskets/households recalculated for the selected set.
SELECT ROUND(SUM(sales_value),2) AS sales_usd,
 COUNT(DISTINCT basket_id) AS baskets,COUNT(DISTINCT household_key) AS households,
 ROUND(SUM(sales_value)/NULLIF(COUNT(DISTINCT basket_id),0),2) AS selected_value_per_basket
FROM mart.sales_detail WHERE week_no BETWEEN 1 AND 102;

-- One week for hand-checking: expected 5211.16 / 142 / 36.70 on supplied data.
SELECT week_no,ROUND(SUM(sales_value),2),COUNT(DISTINCT basket_id),
 ROUND(SUM(sales_value)/NULLIF(COUNT(DISTINCT basket_id),0),2)
FROM mart.sales_detail WHERE week_no=1 GROUP BY week_no;

-- RFM: proposed thresholds documented in docs/KPI.md.
SELECT segment,COUNT(*) AS households,SUM(monetary) AS recorded_value
FROM mart.rfm_at(711,365) GROUP BY segment ORDER BY households DESC;

-- Repeat purchases in window, not inter-period retention.
SELECT COUNT(*) FILTER(WHERE frequency>=2)*100.0/
 NULLIF(COUNT(*) FILTER(WHERE frequency>=1),0) AS repeat_purchase_pct
FROM mart.rfm_at(711,365);

SELECT campaign,contacted_households,responding_households,response_pct,
 eligible_redemption_events,all_redemption_events
FROM mart.campaign ORDER BY campaign;

SELECT * FROM mart.campaign_phase WHERE campaign=1;

SELECT promotion_status,SUM(sales_value),SUM(transaction_rows)
FROM mart.promotion_sales GROUP BY promotion_status;

SELECT * FROM audit.checks WHERE run_id=(SELECT version FROM mart.release);
