"""Versioned source contracts. CSV business IDs remain numeric for this dataset adapter."""
TABLES = {
 'product': [('product_id','bigint'),('manufacturer','bigint'),('department','text'),('brand','text'),('commodity_desc','text'),('sub_commodity_desc','text'),('curr_size_of_product','text')],
 'hh_demographic': [(x,'text') for x in ['age_desc','marital_status_code','income_desc','homeowner_desc','hh_comp_desc','household_size_desc','kid_category_desc']]+[('household_key','bigint')],
 'campaign_desc':[('description','text'),('campaign','integer'),('start_day','integer'),('end_day','integer')],
 'campaign_table':[('description','text'),('household_key','bigint'),('campaign','integer')],
 'coupon':[('coupon_upc','text'),('product_id','bigint'),('campaign','integer')],
 'coupon_redempt':[('household_key','bigint'),('day','integer'),('coupon_upc','text'),('campaign','integer')],
 'transaction_data':[(x,'numeric' if x in ['quantity','sales_value','retail_disc','coupon_disc','coupon_match_disc'] else 'bigint' if x in ['household_key','basket_id','product_id'] else 'integer') for x in ['household_key','basket_id','day','product_id','quantity','sales_value','store_id','retail_disc','trans_time','week_no','coupon_disc','coupon_match_disc']],
 'causal_data':[('product_id','bigint'),('store_id','integer'),('week_no','integer'),('display','text'),('mailer','text')]
}
KEYS={'product':['product_id'],'hh_demographic':['household_key'],'campaign_desc':['campaign'], 'campaign_table':['household_key','campaign']}
REQUIRED={t:[c for c,k in cols if k!='text'] for t,cols in TABLES.items()}
REQUIRED['coupon']+=['coupon_upc'];REQUIRED['coupon_redempt']+=['coupon_upc']
REQUIRED['causal_data']+=['display','mailer']
DEMO_COLS=['age_desc','marital_status_code','income_desc','homeowner_desc','hh_comp_desc','household_size_desc','kid_category_desc']
MARTS=['demographic_history','demographic','contact','redemption','sales_detail','basket','sales_week_department','household_rfm','campaign','campaign_phase','promotion_keys','promotion_sales']
VERSION='integrated-etl-v1'
