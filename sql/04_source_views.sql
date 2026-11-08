-- Stable business IDs presented to the legacy dashboard; never expose SCD surrogate as household identity.
-- basket_id below is the composite basket_key, intentionally TEXT. Original ID remains in dw.fact_sales.
CREATE OR REPLACE VIEW src.transaction_data AS
SELECT f.household_id::bigint household_key,f.basket_key basket_id,f.source_day AS day,p.product_id::bigint product_id,
f.quantity,f.sales_value,s.store_id::integer store_id,f.retail_disc,f.trans_time::integer trans_time,f.source_week_no week_no,f.coupon_disc,f.coupon_match_disc
FROM dw.fact_sales f JOIN dw.dim_product p USING(product_key) JOIN dw.dim_store s USING(store_key);
CREATE OR REPLACE VIEW src.product AS SELECT product_id::bigint product_id,manufacturer,department,brand,commodity_desc,sub_commodity_desc,curr_size_of_product FROM dw.dim_product;
CREATE OR REPLACE VIEW src.campaign_desc AS SELECT description,campaign_id::integer campaign,start_day,end_day FROM dw.dim_campaign;
CREATE OR REPLACE VIEW src.campaign_table AS SELECT d.description,f.household_id::bigint household_key,d.campaign_id::integer campaign FROM dw.fact_campaign_contact f JOIN dw.dim_campaign d USING(campaign_key);
CREATE OR REPLACE VIEW src.coupon_redempt AS SELECT f.household_id::bigint household_key,f.source_day AS day,c.coupon_upc,d.campaign_id::integer campaign FROM dw.fact_coupon_redemption f JOIN dw.dim_campaign d USING(campaign_key) JOIN dw.dim_coupon c USING(coupon_key);
CREATE OR REPLACE VIEW src.hh_demographic AS
SELECT household_id::bigint household_key,age_desc,marital_status_code,income_desc,homeowner_desc,hh_comp_desc,household_size_desc,kid_category_desc FROM dw.dim_household
WHERE has_demographics AND (SELECT max(source_day) FROM dw.fact_sales)>=effective_from_day AND (effective_to_day IS NULL OR (SELECT max(source_day) FROM dw.fact_sales)<effective_to_day);
CREATE OR REPLACE VIEW src.demographic_history AS SELECT household_id::bigint household_key,has_demographics,age_desc,income_desc,effective_from_day,effective_to_day FROM dw.dim_household;
CREATE OR REPLACE VIEW src.causal_data AS SELECT p.product_id::bigint product_id,s.store_id::integer store_id,w.source_week_no week_no,f.display_code display,f.mailer_code mailer,f.source_row_count
FROM dw.fact_promotion f JOIN dw.dim_product p USING(product_key) JOIN dw.dim_store s USING(store_key) JOIN dw.dim_week w USING(week_key);
CREATE OR REPLACE VIEW src.coupon AS SELECT c.coupon_upc,p.product_id::bigint product_id,d.campaign_id::integer campaign FROM dw.bridge_coupon_product b JOIN dw.dim_coupon c USING(coupon_key) JOIN dw.dim_campaign d USING(campaign_key) JOIN dw.dim_product p USING(product_key);
-- Aggregate lineage is a view: one accepted staging row maps to exactly one aggregate.
CREATE OR REPLACE VIEW audit.promotion_lineage AS
SELECT f.promotion_key,s.file_id,s.source_row_no FROM stg.causal_data s JOIN dw.dim_product p ON p.product_id=s.product_id::text
JOIN dw.dim_store d ON d.store_id=s.store_id::text JOIN dw.dim_week w ON w.source_week_no=s.week_no
JOIN dw.fact_promotion f ON (f.product_key,f.store_key,f.week_key,f.display_code,f.mailer_code)=(p.product_key,d.store_key,w.week_key,s.display,s.mailer) WHERE s.valid;
CREATE OR REPLACE VIEW audit.bridge_lineage AS
SELECT c.coupon_key,p.product_key,s.file_id,s.source_row_no FROM stg.coupon s JOIN dw.dim_campaign d ON d.campaign_id=s.campaign::text
JOIN dw.dim_coupon c ON c.campaign_key=d.campaign_key AND c.coupon_upc=s.coupon_upc
JOIN dw.dim_product p ON p.product_id=s.product_id::text WHERE s.valid;
