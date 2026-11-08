"""T01-T19 executable acceptance on an isolated fixture database.
Refuses nonempty real data. Set MINIMART_TEST_ONLY=1 only on postgres_test.
"""
import os,sys,json,uuid,traceback
from pathlib import Path
from decimal import Decimal
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
os.environ['EVIDENCE_DIR']=str(Path(__file__).resolve().parents[1]/'evidence/tests/artifacts')
from common import ROOT,connect
from etl import run_pipeline,publish
from make_fixture import generate,write
from scd import household_change
if os.getenv('MINIMART_TEST_ONLY')!='1':raise RuntimeError('Use compose test service; never run against the demo DB')
results=[]
out=ROOT/'evidence/tests';out.mkdir(parents=True,exist_ok=True)
def check(i,title,ok,actual=None):
 results.append(dict(test_id=i,title=title,status='PASS' if ok else 'FAIL',actual=str(actual)))
 if not ok:raise AssertionError(f'{i}: {title}: {actual}')
def scalar(c,q,p=()):return c.execute(q,p).fetchone()[0]
def same(c,q):
 a,b=c.execute(q).fetchone();return a==b

def main():
 with connect(autocommit=True) as c:
  if scalar(c,"SELECT to_regclass('dw.fact_sales')"):
   if scalar(c,'SELECT count(*) FROM dw.fact_sales')>100:raise RuntimeError('Non-fixture database: refusing test reset')
   # Also verify fixture origin; numeric size alone is not sufficient to authorize cleanup.
   if scalar(c,"SELECT count(*) FROM audit.source_file WHERE filename NOT IN ('product.csv','hh_demographic.csv','campaign_desc.csv','campaign_table.csv','coupon.csv','coupon_redempt.csv','transaction_data.csv','causal_data.csv','late_fixture.csv','invalid_fixture.csv')"):
    raise RuntimeError('Unknown input files: refusing test reset')
  for schema in ['mart','src','dw','stg','raw','audit','dev_src','bench']:
   c.execute('DROP SCHEMA IF EXISTS '+schema+' CASCADE')
 data=generate(ROOT/'fixtures/base')
 run=run_pipeline(ROOT/'fixtures/base')
 with connect(autocommit=True) as c:
  check('T01','8 CSV, row counts and manifest',scalar(c,'SELECT count(*) FROM audit.source_file')==8 and scalar(c,'SELECT sum(row_count) FROM audit.source_file')==sum(map(len,data.values())))
  check('T02','12 DW tables and 17 FK',scalar(c,"SELECT count(*) FROM pg_constraint WHERE contype='f' AND connamespace='dw'::regnamespace")==17 and scalar(c,"SELECT count(*) FROM information_schema.tables WHERE table_schema='dw' AND table_type='BASE TABLE'")==12)
  check('T03','Source rounded = fact = mart',same(c,'SELECT (SELECT sum(round(sales_value,2)) FROM stg.transaction_data WHERE valid),(SELECT sum(sales_value) FROM dw.fact_sales)') and same(c,'SELECT (SELECT sum(sales_value) FROM dw.fact_sales),(SELECT sum(sales_value) FROM mart.sales_detail)'))
  check('T04','Composite baskets and stable households',c.execute('SELECT count(DISTINCT basket_id),count(DISTINCT household_key) FROM mart.sales_detail').fetchone()==(4,2))
  check('T05','Household without demographics retained',scalar(c,'SELECT count(*) FROM mart.household_rfm WHERE NOT has_demographic')==1)
  check('T06','Multi-product coupon does not multiply redemptions',scalar(c,'SELECT count(*) FROM dw.bridge_coupon_product')==2 and scalar(c,'SELECT eligible_redemption_events FROM mart.campaign WHERE campaign=1')==1 and scalar(c,'SELECT response_pct FROM mart.campaign WHERE campaign=1')==50)
  check('T07','Promotion rolled up without fanout, unknown retained',same(c,'SELECT (SELECT sum(sales_value) FROM mart.promotion_sales),(SELECT sum(sales_value) FROM dw.fact_sales)') and scalar(c,"SELECT count(*) FROM mart.promotion_sales WHERE promotion_status='Không có bản ghi quảng bá'")>0)
  base=c.execute('SELECT count(*),sum(sales_value) FROM dw.fact_sales').fetchone();version=scalar(c,'SELECT version FROM mart.release');wm=c.execute('SELECT * FROM audit.watermark').fetchall()
 run2=run_pipeline(ROOT/'fixtures/base')
 with connect(autocommit=True) as c:
  check('T08','Replay does not change fact or published version',c.execute('SELECT count(*),sum(sales_value) FROM dw.fact_sales').fetchone()==base and scalar(c,'SELECT version FROM mart.release')==version and scalar(c,'SELECT status FROM audit.runs WHERE run_id=%s',(run2,))=='SKIPPED')
 # Real failure injection after fact loading, before publication.
 try:run_pipeline(ROOT/'fixtures/base',force=True,fail_at='before-publish')
 except RuntimeError:pass
 else:raise AssertionError('Failure injection did not fail')
 invalid=[dict(data['transaction_data'][0],basket_id=998,sales_value='not-money'),dict(data['transaction_data'][0],basket_id=999,product_id=999)]
 write(ROOT/'fixtures/invalid_fixture.csv','transaction_data',invalid)
 try:run_pipeline(sales_batch=ROOT/'fixtures/invalid_fixture.csv')
 except ValueError:pass
 else:raise AssertionError('Invalid file unexpectedly published')
 with connect(autocommit=True) as c:
  check('T09','Rejected rows retained; failed runs preserve watermark/release',scalar(c,'SELECT version FROM mart.release')==version and c.execute('SELECT * FROM audit.watermark').fetchall()==wm and scalar(c,'SELECT count(*) FROM audit.rejects')==2)
  r=uuid.uuid4().hex;c.execute("INSERT INTO audit.runs(run_id,status) VALUES(%s,'RUNNING')",(r,))
  with c.transaction():
   household_change(c,'1',100,{'income_desc':'50-74K'},'fixture-change-100')
   # Retroactive event splits the older interval without overlap.
   household_change(c,'1',95,{'income_desc':'40-49K'},'fixture-change-95')
   manifest=scalar(c,'SELECT manifest_hash FROM audit.release_meta WHERE version=(SELECT version FROM mart.release)')
   publish(c,r,manifest)
  intervals=c.execute("SELECT effective_from_day,effective_to_day FROM dw.dim_household WHERE household_id='1' ORDER BY effective_from_day").fetchall()
  attrs=c.execute("SELECT DISTINCT f.source_day,h.income_desc FROM dw.fact_sales f JOIN dw.dim_household h USING(household_key) WHERE f.household_id='1' ORDER BY 1").fetchall()
  check('T10','SCD intervals, boundary and rekey',intervals==[(0,95),(95,100),(100,None)] and attrs==[(90,'35-49K'),(100,'50-74K')],(intervals,attrs))
  # Query exactly the dashboard formulas with actual parameter filters.
  query='SELECT sum(sales_value),count(DISTINCT basket_id),count(DISTINCT household_key) FROM mart.sales_detail WHERE week_no BETWEEN %s AND %s AND department=ANY(%s)'
  got=c.execute(query,(15,15,['GROCERY'])).fetchone()
  check('T11','Dashboard SQL filters, empty campaign denominator and as-of demographic',got==(Decimal('45'),2,2) and scalar(c,'SELECT response_pct FROM mart.campaign WHERE campaign=2') is None and scalar(c,'SELECT income_desc FROM mart.rfm_at(99,10) WHERE household_key=1')=='40-49K',got)
  # Benchmark execution follows after the behavioral tests; fixture BM01 is not production timing.
  # A selected household includes every line of each selected basket.
  sampled=scalar(c,'SELECT count(*) FROM mart.sales_detail WHERE household_key=1')
  check('T13','Whole-household sampling preserves basket lines',sampled==3 and scalar(c,"SELECT count(*) FROM mart.sales_detail WHERE basket_id='1:102:100:1'")==2)
  check('T14','Multiple SCD versions counted as one household',scalar(c,"SELECT count(*) FROM dw.dim_household WHERE household_id='1'")==3 and scalar(c,'SELECT count(*) FROM mart.household_rfm WHERE household_key=1')==1)
  check('T15','Equal R/F/M values get equal scores',scalar(c,'SELECT count(*) FROM (SELECT recency,frequency,monetary FROM mart.rfm_at(100,1) GROUP BY 1,2,3 HAVING count(DISTINCT (r_score,f_score,m_score))>1) a')==0)
  check('T16','Bridge EXISTS filter preserves sales sum',same(c,'SELECT (SELECT sum(f.sales_value) FROM dw.fact_sales f WHERE EXISTS(SELECT 1 FROM dw.bridge_coupon_product b WHERE b.product_key=f.product_key)),(SELECT sum(sales_value) FROM dw.fact_sales)'))
  check('T17','Campaign periods clip bounds and keep nonbuying contacts',c.execute("SELECT observed_days,contacted_households FROM mart.campaign_phase WHERE campaign=1 AND phase='Trước'").fetchone()==(5,2) and scalar(c,"SELECT observed_days FROM mart.campaign_phase WHERE campaign=1 AND phase='Sau'")==0)
  promo=c.execute('SELECT sum(source_row_count),(SELECT count(*) FROM audit.promotion_lineage) FROM dw.fact_promotion').fetchone()
 run_pipeline(ROOT/'fixtures/base',allow_rejects=True,force=True)
 with connect(autocommit=True) as c:
  check('T18','Replay aggregate source counts and lineage remain stable',c.execute('SELECT sum(source_row_count),(SELECT count(*) FROM audit.promotion_lineage) FROM dw.fact_promotion').fetchone()==promo== (3,3))
  before=scalar(c,'SELECT sum(sales_value) FROM mart.sales_detail')
 late=[dict(data['transaction_data'][0],basket_id=777,day=90,sales_value='7.50')]
 write(ROOT/'fixtures/late_fixture.csv','transaction_data',late)
 run_pipeline(sales_batch=ROOT/'fixtures/late_fixture.csv',allow_rejects=True)
 with connect(autocommit=True) as c:
  late_attr=scalar(c,"SELECT h.income_desc FROM dw.fact_sales f JOIN dw.dim_household h USING(household_key) WHERE f.basket_id='777'")
  check('T19','Late fact uses historical version and refreshes mart/RFM',scalar(c,'SELECT sum(sales_value) FROM mart.sales_detail')==before+Decimal('7.50') and late_attr=='35-49K' and scalar(c,'SELECT frequency FROM mart.rfm_at(110,365) WHERE household_key=1')==3 and scalar(c,"SELECT max_day FROM audit.watermark WHERE source_name='sales'")==110)
  check('EXTRA_SCD_REPLAY','SCD event replay is idempotent',not household_change(c,'1',100,{'income_desc':'50-74K'},'fixture-change-100'))
  check('EXTRA_BATCH_BALANCE','read=accepted+rejected+skipped',scalar(c,'SELECT count(*) FROM audit.batch_file WHERE read_count<>accepted_count+rejected_count+skipped_count')==0)
  check('EXTRA_CENT_RULE','Round each source row to 2 decimals before aggregation',scalar(c,"SELECT sales_value FROM dw.fact_sales WHERE basket_id='101'")==Decimal('10.01'))
  try:
   with c.transaction():c.execute("INSERT INTO dw.dim_household(household_id,effective_from_day) VALUES('1',96)")
  except Exception:blocked=True
  else:blocked=False
  check('EXTRA_SCD_OVERLAP','Database exclusion rejects overlapping intervals',blocked)
  from product_update import change
  pk=scalar(c,"SELECT product_key FROM dw.dim_product WHERE product_id='1'")
  with c.transaction():
   changed=change(c,'1',{'brand':'Fixture Type1'},'fixture-product-type1')
   replay=change(c,'1',{'brand':'Fixture Type1'},'fixture-product-type1')
  check('EXTRA_PRODUCT_TYPE1','Type1 preserves product key and event replay',changed and not replay and scalar(c,"SELECT product_key FROM dw.dim_product WHERE product_id='1'")==pk)
 from benchmark import main as bm01
 from benchmark_design import main as bm_design
 bm01();bm_design()
 check('T12','BM01 fixture and BM02/BM03 synthetic: equality gates and raw plans',True,'See evidence/tests/artifacts; not production dashboard timings')

if __name__=='__main__':
 error=None
 try:main()
 except Exception as exc:error=str(exc);traceback.print_exc()
 finally:
  try:
   with connect() as c:engine=c.execute('SELECT version()').fetchone()[0]
  except Exception:engine='unavailable'
  report={'utc':datetime.now(timezone.utc).isoformat(),'engine':engine,'copy_mode':os.getenv('MINIMART_COPY_MODE','copy'),'scope':'Synthetic isolated fixture; not acceptance of all eight production CSVs. BM01 uses the tiny fixture; BM02/BM03 use 520000 synthetic rows.','tests':results,'error':error}
  (out/'integration.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report,ensure_ascii=False,indent=2))
 if error:sys.exit(1)
