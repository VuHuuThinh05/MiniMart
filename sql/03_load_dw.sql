-- Idempotent dimension and fact loading. Source numeric IDs are stable business IDs.
INSERT INTO dw.dim_product(product_id,manufacturer,department,brand,commodity_desc,sub_commodity_desc,curr_size_of_product)
SELECT product_id::text,manufacturer::text,department,brand,commodity_desc,sub_commodity_desc,curr_size_of_product FROM stg.product WHERE valid
ON CONFLICT(product_id) DO NOTHING;
INSERT INTO dw.dim_campaign(campaign_id,description,start_day,end_day)
SELECT campaign::text,description,start_day,end_day FROM stg.campaign_desc WHERE valid ON CONFLICT(campaign_id) DO NOTHING;
INSERT INTO dw.dim_store(store_id)
SELECT store_id::text FROM stg.transaction_data WHERE valid UNION SELECT store_id::text FROM stg.causal_data WHERE valid ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_week(source_week_no)
SELECT week_no FROM stg.transaction_data WHERE valid UNION SELECT week_no FROM stg.causal_data WHERE valid ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_day(source_day)
SELECT day FROM stg.transaction_data WHERE valid UNION SELECT day FROM stg.coupon_redempt WHERE valid
UNION SELECT start_day FROM stg.campaign_desc WHERE valid UNION SELECT end_day FROM stg.campaign_desc WHERE valid ON CONFLICT DO NOTHING;
INSERT INTO dw.dim_household(household_id,has_demographics,age_desc,marital_status_code,income_desc,homeowner_desc,hh_comp_desc,household_size_desc,kid_category_desc,change_reason)
SELECT u.household_key::text,d.household_key IS NOT NULL,d.age_desc,d.marital_status_code,d.income_desc,d.homeowner_desc,d.hh_comp_desc,d.household_size_desc,d.kid_category_desc,'Baseline static CSV; effective from 0 is an explicit assumption'
FROM (SELECT household_key FROM stg.transaction_data WHERE valid UNION SELECT household_key FROM stg.campaign_table WHERE valid
UNION SELECT household_key FROM stg.coupon_redempt WHERE valid UNION SELECT household_key FROM stg.hh_demographic WHERE valid) u
LEFT JOIN stg.hh_demographic d ON d.household_key=u.household_key AND d.valid
WHERE NOT EXISTS(SELECT 1 FROM dw.dim_household h WHERE h.household_id=u.household_key::text);
INSERT INTO dw.dim_coupon(campaign_key,coupon_upc)
SELECT d.campaign_key,u.coupon_upc FROM (SELECT campaign,coupon_upc FROM stg.coupon WHERE valid UNION SELECT campaign,coupon_upc FROM stg.coupon_redempt WHERE valid) u
JOIN dw.dim_campaign d ON d.campaign_id=u.campaign::text ON CONFLICT DO NOTHING;
INSERT INTO dw.bridge_coupon_product
SELECT DISTINCT c.coupon_key,p.product_key FROM stg.coupon s JOIN dw.dim_campaign d ON d.campaign_id=s.campaign::text
JOIN dw.dim_coupon c ON c.campaign_key=d.campaign_key AND c.coupon_upc=s.coupon_upc
JOIN dw.dim_product p ON p.product_id=s.product_id::text WHERE s.valid ON CONFLICT DO NOTHING;
INSERT INTO dw.fact_sales(file_id,source_row_no,household_key,household_id,product_key,store_key,day_key,week_key,source_day,source_week_no,basket_id,basket_key,trans_time,quantity,sales_value,retail_disc,coupon_disc,coupon_match_disc)
SELECT s.file_id,s.source_row_no,h.household_key,h.household_id,p.product_key,st.store_key,d.day_key,w.week_key,s.day,s.week_no,s.basket_id::text,
s.household_key||':'||s.basket_id||':'||s.day||':'||s.store_id,s.trans_time::text,s.quantity,round(s.sales_value,2),round(s.retail_disc,2),round(s.coupon_disc,2),round(s.coupon_match_disc,2)
FROM stg.transaction_data s JOIN dw.dim_household h ON h.household_id=s.household_key::text AND s.day>=h.effective_from_day AND (h.effective_to_day IS NULL OR s.day<h.effective_to_day)
JOIN dw.dim_product p ON p.product_id=s.product_id::text JOIN dw.dim_store st ON st.store_id=s.store_id::text
JOIN dw.dim_day d ON d.source_day=s.day JOIN dw.dim_week w ON w.source_week_no=s.week_no
WHERE s.valid ON CONFLICT(file_id,source_row_no) DO NOTHING;
INSERT INTO dw.fact_campaign_contact(file_id,source_row_no,household_key,household_id,campaign_key)
SELECT DISTINCT ON(h.household_id,d.campaign_key) s.file_id,s.source_row_no,h.household_key,h.household_id,d.campaign_key
FROM stg.campaign_table s JOIN dw.dim_campaign d ON d.campaign_id=s.campaign::text
JOIN dw.dim_household h ON h.household_id=s.household_key::text AND d.start_day>=h.effective_from_day AND (h.effective_to_day IS NULL OR d.start_day<h.effective_to_day)
WHERE s.valid ORDER BY h.household_id,d.campaign_key,s.file_id,s.source_row_no ON CONFLICT DO NOTHING;
INSERT INTO dw.fact_coupon_redemption(file_id,source_row_no,household_key,household_id,day_key,source_day,campaign_key,coupon_key)
SELECT s.file_id,s.source_row_no,h.household_key,h.household_id,dy.day_key,s.day,d.campaign_key,c.coupon_key
FROM stg.coupon_redempt s JOIN dw.dim_campaign d ON d.campaign_id=s.campaign::text
JOIN dw.dim_coupon c ON c.campaign_key=d.campaign_key AND c.coupon_upc=s.coupon_upc
JOIN dw.dim_day dy ON dy.source_day=s.day JOIN dw.dim_household h ON h.household_id=s.household_key::text AND s.day>=h.effective_from_day AND (h.effective_to_day IS NULL OR s.day<h.effective_to_day)
WHERE s.valid ON CONFLICT(file_id,source_row_no) DO NOTHING;
-- Recompute aggregate counts from immutable accepted staging, never += on replay.
INSERT INTO dw.fact_promotion(product_key,store_key,week_key,display_code,mailer_code,has_display,has_mailer,source_row_count)
SELECT p.product_key,d.store_key,w.week_key,s.display,s.mailer,s.display<>'0',s.mailer<>'0',count(*)
FROM stg.causal_data s JOIN dw.dim_product p ON p.product_id=s.product_id::text
JOIN dw.dim_store d ON d.store_id=s.store_id::text JOIN dw.dim_week w ON w.source_week_no=s.week_no
WHERE s.valid GROUP BY p.product_key,d.store_key,w.week_key,s.display,s.mailer
ON CONFLICT(product_key,store_key,week_key,display_code,mailer_code) DO UPDATE SET source_row_count=excluded.source_row_count,has_display=excluded.has_display,has_mailer=excluded.has_mailer;
ANALYZE dw.fact_sales;
ANALYZE dw.fact_promotion;
ANALYZE dw.dim_household;
