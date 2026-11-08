-- Dependencies: src adapter views over the integrated dw schema.
-- All source families are mapped in 04_source_views.sql; sales_base handles product attributes.
CREATE OR REPLACE VIEW mart.sales_base AS
SELECT t.*, COALESCE(NULLIF(BTRIM(p.department),''),'Chưa rõ') AS department,
 COALESCE(NULLIF(BTRIM(p.commodity_desc),''),'Chưa rõ') AS commodity_desc,
 p.brand, p.sub_commodity_desc
FROM src.transaction_data t LEFT JOIN src.product p USING(product_id);

CREATE MATERIALIZED VIEW IF NOT EXISTS mart.sales_detail AS SELECT * FROM mart.sales_base WITH NO DATA;
CREATE INDEX IF NOT EXISTS sales_detail_filter ON mart.sales_detail(week_no,store_id,department);
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.basket AS
SELECT basket_id, household_key, store_id, day, week_no, SUM(sales_value) AS sales_value, COUNT(*) AS line_count
FROM mart.sales_base GROUP BY basket_id,household_key,store_id,day,week_no WITH NO DATA;
CREATE UNIQUE INDEX IF NOT EXISTS basket_key ON mart.basket(basket_id);
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.sales_week_department AS
SELECT week_no, department, SUM(sales_value) AS sales_value, COUNT(DISTINCT basket_id) AS baskets
FROM mart.sales_base GROUP BY week_no,department WITH NO DATA;
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.household_rfm AS
WITH bounds AS (SELECT MAX(day) AS cutoff FROM src.transaction_data),
a AS (SELECT household_key, MAX(day) AS last_day, COUNT(DISTINCT basket_id) AS frequency,
 SUM(sales_value) AS monetary FROM src.transaction_data CROSS JOIN bounds
 WHERE day BETWEEN cutoff-364 AND cutoff GROUP BY household_key),
u AS (SELECT household_key FROM src.transaction_data UNION SELECT household_key FROM src.campaign_table
 UNION SELECT household_key FROM src.coupon_redempt UNION SELECT household_key FROM src.hh_demographic),
b AS (SELECT u.household_key, cutoff AS cutoff_day, cutoff-a.last_day AS recency,
 COALESCE(a.frequency,0) AS frequency, COALESCE(a.monetary,0) AS monetary,
 d.household_key IS NOT NULL AS has_demographic,
 COALESCE(d.age_desc,'Chưa có thông tin') AS age_desc,
 COALESCE(d.income_desc,'Chưa có thông tin') AS income_desc
 FROM u CROSS JOIN bounds LEFT JOIN a USING(household_key) LEFT JOIN src.hh_demographic d USING(household_key)),
c AS (SELECT *,CASE WHEN frequency=0 THEN 0 WHEN recency<=30 THEN 5 WHEN recency<=60 THEN 4 WHEN recency<=90 THEN 3 WHEN recency<=180 THEN 2 ELSE 1 END AS r_score,
 CASE WHEN frequency=0 THEN 0 WHEN frequency>=52 THEN 5 WHEN frequency>=26 THEN 4 WHEN frequency>=12 THEN 3 WHEN frequency>=4 THEN 2 ELSE 1 END AS f_score,
 CASE WHEN frequency=0 THEN 0 WHEN monetary>=2000 THEN 5 WHEN monetary>=1000 THEN 4 WHEN monetary>=500 THEN 3 WHEN monetary>=100 THEN 2 ELSE 1 END AS m_score FROM b)
SELECT *,CASE WHEN frequency=0 THEN 'Không mua trong cửa sổ' WHEN r_score>=4 AND f_score>=4 AND m_score>=4 THEN 'Giá trị cao'
 WHEN r_score<=2 AND f_score>=3 THEN 'Có nguy cơ rời bỏ' WHEN r_score>=4 AND f_score>=3 THEN 'Mua thường xuyên'
 WHEN r_score>=4 THEN 'Mua gần đây' ELSE 'Cần theo dõi' END AS segment FROM c WITH NO DATA;

-- Recipient denominator and redeemed-recipient numerator share campaign + household.
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.campaign AS
WITH contacts AS (SELECT DISTINCT campaign,household_key FROM src.campaign_table),
red AS (SELECT r.campaign,r.household_key,COUNT(*) AS events
 FROM src.coupon_redempt r JOIN src.campaign_desc d USING(campaign)
 WHERE r.day BETWEEN d.start_day AND d.end_day GROUP BY r.campaign,r.household_key),
a AS (SELECT c.campaign,COUNT(*) AS contacted_households,COUNT(r.household_key) AS responding_households,
 COALESCE(SUM(r.events),0) AS eligible_redemption_events FROM contacts c LEFT JOIN red r USING(campaign,household_key) GROUP BY c.campaign),
b AS (SELECT campaign,COUNT(*) AS all_redemption_events,COUNT(DISTINCT household_key) AS all_redeeming_households FROM src.coupon_redempt GROUP BY campaign)
SELECT d.*,COALESCE(a.contacted_households,0) AS contacted_households,
 COALESCE(a.responding_households,0) AS responding_households,
 COALESCE(a.eligible_redemption_events,0) AS eligible_redemption_events,
 100.0*a.responding_households/NULLIF(a.contacted_households,0) AS response_pct,
 COALESCE(b.all_redemption_events,0) AS all_redemption_events,
 COALESCE(b.all_redeeming_households,0) AS all_redeeming_households
FROM src.campaign_desc d LEFT JOIN a USING(campaign) LEFT JOIN b USING(campaign) WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS mart.campaign_phase AS
WITH bounds AS (SELECT MIN(day) lo,MAX(day) hi FROM src.transaction_data),
periods AS (SELECT d.campaign,v.phase,GREATEST(v.lo,b.lo) lo,LEAST(v.hi,b.hi) hi
 FROM src.campaign_desc d CROSS JOIN bounds b
 CROSS JOIN LATERAL (VALUES ('Trước',d.start_day-28,d.start_day-1),('Trong',d.start_day,d.end_day),('Sau',d.end_day+1,d.end_day+28)) v(phase,lo,hi)),
contacts AS (SELECT DISTINCT campaign,household_key FROM src.campaign_table)
SELECT p.campaign,p.phase,p.lo AS start_day,p.hi AS end_day,GREATEST(p.hi-p.lo+1,0) AS observed_days,
 COUNT(DISTINCT c.household_key) AS contacted_households,COALESCE(SUM(b.sales_value),0) AS sales_value,
 COUNT(b.basket_id) AS baskets,
 COALESCE(SUM(b.sales_value),0)/NULLIF(COUNT(DISTINCT c.household_key)*GREATEST(p.hi-p.lo+1,0),0) AS sales_per_household_day
FROM periods p LEFT JOIN contacts c USING(campaign)
LEFT JOIN mart.basket b ON b.household_key=c.household_key AND b.day BETWEEN p.lo AND p.hi
GROUP BY p.campaign,p.phase,p.lo,p.hi WITH NO DATA;

-- Collapse multiple promotion rows before joining at product-store-week grain.
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.promotion_keys AS
SELECT product_id,store_id,week_no,SUM(source_row_count) AS source_rows,
 BOOL_OR(COALESCE(display,'0')<>'0') AS has_display,
 BOOL_OR(COALESCE(mailer,'0')<>'0') AS has_mailer
FROM src.causal_data GROUP BY product_id,store_id,week_no WITH NO DATA;
CREATE UNIQUE INDEX IF NOT EXISTS promotion_keys_key ON mart.promotion_keys(product_id,store_id,week_no);
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.promotion_sales AS
WITH s AS (SELECT product_id,store_id,week_no,department,SUM(sales_value) AS sales_value,COUNT(*) AS transaction_rows
 FROM mart.sales_base GROUP BY product_id,store_id,week_no,department)
SELECT s.*,CASE WHEN p.product_id IS NULL THEN 'Không có bản ghi quảng bá'
 WHEN has_display AND has_mailer THEN 'Trưng bày và quảng cáo'
 WHEN has_display THEN 'Có trưng bày' WHEN has_mailer THEN 'Có quảng cáo'
 ELSE 'Có bản ghi nhưng không đánh dấu' END AS promotion_status
FROM s LEFT JOIN mart.promotion_keys p USING(product_id,store_id,week_no) WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS mart.demographic_history AS SELECT * FROM src.demographic_history WITH NO DATA;
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.demographic AS SELECT * FROM src.hh_demographic WITH NO DATA;
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.contact AS SELECT DISTINCT campaign,household_key FROM src.campaign_table WITH NO DATA;
CREATE MATERIALIZED VIEW IF NOT EXISTS mart.redemption AS SELECT * FROM src.coupon_redempt WITH NO DATA;

CREATE OR REPLACE FUNCTION mart.rfm_at(as_of_day integer,window_days integer)
RETURNS TABLE(household_key bigint,cutoff_day integer,recency integer,frequency bigint,monetary numeric,has_demographic boolean,age_desc text,income_desc text,r_score integer,f_score integer,m_score integer,segment text)
LANGUAGE SQL STABLE AS $rfm$
WITH bounds AS (SELECT as_of_day AS cutoff),
a AS (SELECT household_key, MAX(day) AS last_day, COUNT(DISTINCT basket_id) AS frequency,
 SUM(sales_value) AS monetary FROM mart.basket CROSS JOIN bounds
 WHERE day BETWEEN cutoff-window_days+1 AND cutoff GROUP BY household_key),
u AS (SELECT household_key FROM mart.basket UNION SELECT household_key FROM mart.contact
 UNION SELECT household_key FROM mart.redemption UNION SELECT household_key FROM mart.demographic),
b AS (SELECT u.household_key, cutoff AS cutoff_day, cutoff-a.last_day AS recency,
 COALESCE(a.frequency,0) AS frequency, COALESCE(a.monetary,0) AS monetary,
 COALESCE(d.has_demographics,false) AS has_demographic,
 COALESCE(d.age_desc,'Chưa có thông tin') AS age_desc,
 COALESCE(d.income_desc,'Chưa có thông tin') AS income_desc
 FROM u CROSS JOIN bounds LEFT JOIN a USING(household_key) LEFT JOIN mart.demographic_history d ON d.household_key=u.household_key AND cutoff>=d.effective_from_day AND (d.effective_to_day IS NULL OR cutoff<d.effective_to_day)),
c AS (SELECT *,CASE WHEN frequency=0 THEN 0 WHEN recency<=30 THEN 5 WHEN recency<=60 THEN 4 WHEN recency<=90 THEN 3 WHEN recency<=180 THEN 2 ELSE 1 END AS r_score,
 CASE WHEN frequency=0 THEN 0 WHEN frequency>=52 THEN 5 WHEN frequency>=26 THEN 4 WHEN frequency>=12 THEN 3 WHEN frequency>=4 THEN 2 ELSE 1 END AS f_score,
 CASE WHEN frequency=0 THEN 0 WHEN monetary>=2000 THEN 5 WHEN monetary>=1000 THEN 4 WHEN monetary>=500 THEN 3 WHEN monetary>=100 THEN 2 ELSE 1 END AS m_score FROM b)
SELECT *,CASE WHEN frequency=0 THEN 'Không mua trong cửa sổ' WHEN r_score>=4 AND f_score>=4 AND m_score>=4 THEN 'Giá trị cao'
 WHEN r_score<=2 AND f_score>=3 THEN 'Có nguy cơ rời bỏ' WHEN r_score>=4 AND f_score>=3 THEN 'Mua thường xuyên'
 WHEN r_score>=4 THEN 'Mua gần đây' ELSE 'Cần theo dõi' END AS segment FROM c
$rfm$;
