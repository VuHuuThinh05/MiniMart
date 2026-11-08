"""Read-only validation of the current integrated publication; no injected errors."""
import json
from datetime import datetime,timezone
from common import ROOT,connect,EVIDENCE
QUERIES={
 'sales_row_count':'SELECT (SELECT count(*) FROM dw.fact_sales)=(SELECT count(*) FROM stg.transaction_data WHERE valid)',
 'rounded_sales_value':'SELECT (SELECT sum(sales_value) FROM dw.fact_sales)=(SELECT sum(round(sales_value,2)) FROM stg.transaction_data WHERE valid)',
 'mart_sales_value':'SELECT (SELECT sum(sales_value) FROM dw.fact_sales)=(SELECT sum(sales_value) FROM mart.sales_detail)',
 'mart_basket_count':'SELECT (SELECT count(DISTINCT basket_key) FROM dw.fact_sales)=(SELECT count(*) FROM mart.basket)',
 'promotion_source_count':'SELECT (SELECT sum(source_row_count) FROM dw.fact_promotion)=(SELECT count(*) FROM stg.causal_data WHERE valid)',
 'promotion_sales_value':'SELECT (SELECT sum(sales_value) FROM mart.promotion_sales)=(SELECT sum(sales_value) FROM dw.fact_sales)',
 'household_scd_ranges':"SELECT NOT EXISTS(SELECT 1 FROM dw.fact_sales f JOIN dw.dim_household h USING(household_key) WHERE f.household_id<>h.household_id OR f.source_day<h.effective_from_day OR f.source_day>=coalesce(h.effective_to_day,2147483647))",
 'source_day_keys':'SELECT NOT EXISTS(SELECT 1 FROM dw.fact_sales f JOIN dw.dim_day d USING(day_key) WHERE f.source_day<>d.source_day)',
 'source_week_keys':'SELECT NOT EXISTS(SELECT 1 FROM dw.fact_sales f JOIN dw.dim_week d USING(week_key) WHERE f.source_week_no<>d.source_week_no)',
 'rfm_snapshot_vs_function':"SELECT NOT EXISTS((SELECT * FROM mart.household_rfm EXCEPT ALL SELECT * FROM mart.rfm_at((SELECT max(day) FROM mart.basket),365)) UNION ALL (SELECT * FROM mart.rfm_at((SELECT max(day) FROM mart.basket),365) EXCEPT ALL SELECT * FROM mart.household_rfm))",
 'one_current_version':'SELECT NOT EXISTS(SELECT household_id FROM dw.dim_household GROUP BY household_id HAVING count(*) FILTER(WHERE is_current)<>1)',
 'response_bounds':'SELECT NOT EXISTS(SELECT 1 FROM mart.campaign WHERE responding_households>contacted_households)',
 'file_balance':'SELECT NOT EXISTS(SELECT 1 FROM audit.batch_file WHERE read_count<>accepted_count+rejected_count+skipped_count)',
 'fk_validated':"SELECT NOT EXISTS(SELECT 1 FROM pg_constraint WHERE connamespace='dw'::regnamespace AND contype='f' AND NOT convalidated)"
}
def main():
 with connect() as c:
  c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
  result={'utc':datetime.now(timezone.utc).isoformat(),'release':c.execute('SELECT version FROM mart.release').fetchone()[0],'engine':c.execute('SELECT version()').fetchone()[0],'checks':[{'check':name,'passed':bool(c.execute(q).fetchone()[0])} for name,q in QUERIES.items()],'totals':dict(zip(['sales_rows','sales_value','households','baskets'],map(str,c.execute('SELECT count(*),sum(sales_value),count(DISTINCT household_id),count(DISTINCT basket_key) FROM dw.fact_sales').fetchone())))}
 out=EVIDENCE;out.mkdir(exist_ok=True);(out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,indent=2))
 if not all(x['passed'] for x in result['checks']):raise SystemExit(1)
if __name__=='__main__':main()
