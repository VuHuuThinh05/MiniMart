"""CSV -> durable raw/stg/reject -> atomic DW + mart + watermark publication.
One immutable baseline per source. Additional immutable sales batches are explicit.
Source correction/replacement is deliberately blocked rather than appended silently.
"""
import argparse,csv,hashlib,json,time,uuid,contextlib,os,re,tempfile,itertools
from pathlib import Path
from common import ROOT,connect,EVIDENCE
from model import TABLES,REQUIRED,KEYS,MARTS,VERSION
from psycopg import sql


def digest(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
 return h.hexdigest()


DEFAULT_CAUSAL_LIMIT = 2_000_000
PATCH_VERSION = 'demo-prefix-v1'


def prepare_causal_sample(source, destination, limit):
 """Copy CSV records, not physical lines; preserve source order and quoting."""
 if limit <= 0:
  raise ValueError('causal limit must be positive')
 count = 0
 with source.open(encoding='utf-8-sig', newline='') as src, destination.open('w', encoding='utf-8', newline='') as dst:
  reader = csv.reader(src, strict=True)
  header = next(reader, None)
  if header is None:raise ValueError('Empty causal_data.csv')
  writer = csv.writer(dst, lineterminator='\n')
  writer.writerow(header)
  for row in itertools.islice(reader, limit):
   if len(row) != len(header):raise ValueError(f'causal_data: malformed record {count+1}')
   writer.writerow(row)
   count += 1
   if count % 250_000 == 0:print(f'  SAMPLE causal_data: {count:,}/{limit:,} records', flush=True)
 if not count:raise ValueError('causal_data.csv has no data records')
 print(f'  SAMPLE ready: {count:,} records; original CSV unchanged', flush=True)
 return count


def ensure_scope(c, limit):
 # Never silently reinterpret a previously loaded full baseline as a sample.
 c.execute("CREATE TABLE IF NOT EXISTS audit.demo_scope(singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), causal_limit bigint NOT NULL CHECK(causal_limit>=0), selection text NOT NULL)")
 previous = c.execute('SELECT causal_limit FROM audit.demo_scope WHERE singleton').fetchone()
 if previous and previous[0] != limit:
  raise ValueError('Causal scope changed. Use a fresh database; --force cannot change the source scope.')
 if not previous:
  if limit and c.execute("SELECT 1 FROM audit.source_file WHERE source_name='causal_data'").fetchone():
   raise ValueError('Existing causal_data baseline has no demo scope. Stop: use a fresh demo database before loading the limited sample. No existing source rows were deleted.')
  c.execute("INSERT INTO audit.demo_scope VALUES(true,%s,%s)", (limit, 'first CSV records in source order' if limit else 'full source'))
 c.execute('GRANT SELECT ON audit.demo_scope TO minimart_reader')


def run_pipeline(data_dir=None,sales_batch=None,allow_rejects=False,force=False,fail_at=None,causal_limit=DEFAULT_CAUSAL_LIMIT):
 if causal_limit < 0:raise ValueError('--causal-limit must be >= 0; 0 explicitly means full source')
 print(f'SCOPE: causal_data = first {causal_limit:,} records' if causal_limit else 'SCOPE: causal_data = FULL SOURCE',flush=True)
 print('Other seven baseline CSVs: full source. Promotion sample is NOT representative.',flush=True)
 # Temporary file is bounded by N records; no full-source hash/read for sampled causal.
 with tempfile.TemporaryDirectory(prefix='minimart-causal-') as temp:
  sample = None
  if causal_limit and not sales_batch:
   source = Path(data_dir or ROOT/'Data')/'causal_data.csv'
   sample = Path(temp)/'causal_data.csv'
   prepare_causal_sample(source, sample, causal_limit)
  return _run_pipeline(data_dir,sales_batch,allow_rejects,force,fail_at,causal_limit,sample)


def setup(c):
 if c.execute("SELECT to_regclass('mart.release'),to_regclass('audit.release_meta')").fetchone()==('mart.release',None):
  if c.execute('SELECT count(*) FROM mart.release').fetchone()[0]:
   raise RuntimeError('Existing standalone publication detected. Use the separate minimart_demo project; do not migrate in place.')
 c.execute((ROOT/'sql/00_schema.sql').read_text())
 c.execute((ROOT/'sql/01_dw.sql').read_text())
 operations=(ROOT/'sql/02_operations.sql').read_text()
 # Compatibility with the original SQL parser: accept scientific notation.
 operations=operations.replace('^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$','^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$')
 c.execute(operations)
 for t,cols in TABLES.items():
  c.execute(f'CREATE TABLE IF NOT EXISTS raw.{t}(file_id text NOT NULL, source_row_no bigint NOT NULL,'+','.join(f'{n} text' for n,_ in cols)+', PRIMARY KEY(file_id,source_row_no))')
  c.execute(f'CREATE TABLE IF NOT EXISTS stg.{t}(file_id text NOT NULL, source_row_no bigint NOT NULL,'+','.join(f'{n} {k}' for n,k in cols)+', valid boolean NOT NULL DEFAULT true,PRIMARY KEY(file_id,source_row_no))')
 c.execute('GRANT USAGE ON SCHEMA audit,mart TO minimart_reader')
 c.execute('GRANT SELECT ON ALL TABLES IN SCHEMA audit,mart TO minimart_reader')


@contextlib.contextmanager
def step(c,run,name):
 i=c.execute("INSERT INTO audit.steps(run_id,step_name,status) VALUES(%s,%s,'RUNNING') RETURNING step_id",(run,name)).fetchone()[0]
 print(name,flush=True)
 started=time.monotonic()
 try:
  yield
 except Exception as e:
  if not c.closed:
   c.execute("UPDATE audit.steps SET status='FAILED',finished_at=now(),message=%s WHERE step_id=%s",(str(e)[:2000],i))
  raise
 else:
  c.execute("UPDATE audit.steps SET status='DONE',finished_at=now() WHERE step_id=%s",(i,))
  print(f'DONE {name} ({time.monotonic()-started:.1f}s)',flush=True)


def ingest(c,t,path,sha):
 fid=t+':'+sha
 if c.execute('SELECT 1 FROM audit.source_file WHERE file_id=%s',(fid,)).fetchone():
  print(f'  REUSE {path.name}: committed raw/stg; no COPY',flush=True)
  return fid
 cols=TABLES[t]
 with path.open(encoding='utf-8-sig',newline='') as f:
  header=[x.strip().lower() for x in next(csv.reader(f))]
 if len(header)!=len(set(header)) or set(header)!={x for x,_ in cols}:raise ValueError(f'{path.name}: header mismatch {header}')
 # COPY a temporary table: source row numbers assigned in original CSV record order.
 with c.transaction():
  c.execute('CREATE TEMP TABLE ingest_tmp(source_row_no bigint GENERATED ALWAYS AS IDENTITY,'+','.join(f'{x} text' for x in header)+') ON COMMIT DROP')
  if os.getenv('MINIMART_COPY_MODE')=='insert':
   # Portable fixture-only fallback for WASM PostgreSQL wire adapters without COPY support.
   if os.getenv('MINIMART_TEST_ONLY')!='1':raise ValueError('insert mode is test-only')
   with path.open(encoding='utf-8-sig',newline='') as f:
    reader=csv.reader(f);next(reader)
    with c.cursor() as cur:cur.executemany('INSERT INTO ingest_tmp('+','.join(header)+') VALUES('+','.join(['%s']*len(header))+')',reader)
  else:
   with c.cursor() as cur:
    with cur.copy('COPY ingest_tmp('+','.join(header)+") FROM STDIN WITH(FORMAT CSV,HEADER true,ENCODING 'UTF8')") as cp,path.open('rb') as f:
     first=True;copied=0;next_log=64*1024*1024
     for chunk in iter(lambda:f.read(4*1024*1024),b''):
      if first:chunk=chunk.removeprefix(b'\xef\xbb\xbf');first=False
      cp.write(chunk);copied+=len(chunk)
      if copied>=next_log:
       print(f"  COPY {path.name}: {copied//(1024*1024)} MiB",flush=True);next_log+=64*1024*1024
  count=c.execute('SELECT count(*) FROM ingest_tmp').fetchone()[0]
  print(f'  COPY done: {count:,} rows; loading raw',flush=True)
  c.execute('INSERT INTO audit.source_file(file_id,source_name,filename,sha256,row_count) VALUES(%s,%s,%s,%s,%s)',(fid,t,path.name,sha,count))
  names=','.join(n for n,_ in cols)
  c.execute(f'INSERT INTO raw.{t}(file_id,source_row_no,{names}) SELECT %s,source_row_no,{names} FROM ingest_tmp',(fid,))
  print(f'  RAW done: {count:,} rows; converting staging',flush=True)
  expr=','.join(f'NULLIF(BTRIM({n}),\'\')' if k=='text' else f'stg.as_{k}({n})' for n,k in cols)
  c.execute(f'INSERT INTO stg.{t}(file_id,source_row_no,{names}) SELECT %s,source_row_no,{expr} FROM ingest_tmp',(fid,))
  print(f'  STAGING written: {count:,} rows; validating types',flush=True)
  conditions=[f'{n} IS NULL' for n in REQUIRED[t]]
  if t=='campaign_desc':conditions+=['start_day>end_day']
  if t=='transaction_data':conditions+=['trans_time>2359','mod(trans_time,100)>59','quantity<>round(quantity,3)']
  c.execute(f'UPDATE stg.{t} SET valid=false WHERE file_id=%s AND ('+' OR '.join(conditions)+')',(fid,))
  c.execute(f"INSERT INTO audit.rejects(file_id,source_row_no,source_name,rule_code,raw_payload) SELECT s.file_id,s.source_row_no,%s,'INVALID_REQUIRED_TYPE_RANGE',to_jsonb(r) FROM stg.{t} s JOIN raw.{t} r USING(file_id,source_row_no) WHERE s.file_id=%s AND NOT s.valid ON CONFLICT DO NOTHING",(t,fid))
  c.execute(f'ANALYZE stg.{t}')
 return fid


def relational_validation(c):
 # Every offending source row is quarantined with lineage; no silent inner-join losses.
 rules={
 'transaction_data':[('UNKNOWN_PRODUCT','NOT EXISTS(SELECT 1 FROM stg.product p WHERE p.valid AND p.product_id=s.product_id)')],
 'causal_data':[('UNKNOWN_PRODUCT','NOT EXISTS(SELECT 1 FROM stg.product p WHERE p.valid AND p.product_id=s.product_id)')],
 'campaign_table':[('UNKNOWN_CAMPAIGN','NOT EXISTS(SELECT 1 FROM stg.campaign_desc d WHERE d.valid AND d.campaign=s.campaign)')],
 'coupon':[('UNKNOWN_PRODUCT','NOT EXISTS(SELECT 1 FROM stg.product p WHERE p.valid AND p.product_id=s.product_id)'),('UNKNOWN_CAMPAIGN','NOT EXISTS(SELECT 1 FROM stg.campaign_desc d WHERE d.valid AND d.campaign=s.campaign)')],
 'coupon_redempt':[('UNKNOWN_CAMPAIGN','NOT EXISTS(SELECT 1 FROM stg.campaign_desc d WHERE d.valid AND d.campaign=s.campaign)')]
 }
 with c.transaction():
  for t,keys in KEYS.items():
   # Dimension duplicates are ambiguous; contacts duplicates are collapsed in DW instead.
   if t=='campaign_table':continue
   key=','.join(keys)
   c.execute(f'UPDATE stg.{t} s SET valid=false WHERE ({key}) IN (SELECT {key} FROM stg.{t} WHERE valid GROUP BY {key} HAVING count(*)>1)')
   c.execute(f"INSERT INTO audit.rejects SELECT s.file_id,s.source_row_no,%s,'DUPLICATE_DIMENSION_KEY',to_jsonb(r),now() FROM stg.{t} s JOIN raw.{t} r USING(file_id,source_row_no) WHERE NOT s.valid AND NOT EXISTS(SELECT 1 FROM audit.rejects e WHERE e.file_id=s.file_id AND e.source_row_no=s.source_row_no) ON CONFLICT DO NOTHING",(t,))
  for t,rr in rules.items():
   for code,condition in rr:
    c.execute(f"INSERT INTO audit.rejects SELECT s.file_id,s.source_row_no,%s,%s,to_jsonb(r),now() FROM stg.{t} s JOIN raw.{t} r USING(file_id,source_row_no) WHERE s.valid AND ({condition}) ON CONFLICT DO NOTHING",(t,code))
    c.execute(f'UPDATE stg.{t} s SET valid=false WHERE s.valid AND ({condition})')


def publish(c,run,manifest,fail_at=None):
 checks=[]
 def check(name,q,severity='ERROR'):
  n=c.execute(q).fetchone()[0];ok=n==0
  checks.append((run,name,severity,n,ok))
  c.execute('INSERT INTO audit.checks VALUES(%s,%s,%s,%s,%s)',checks[-1])
  if not ok and severity=='ERROR':raise ValueError(f'{name}: {n}')
 with c.transaction():
  c.execute("SET LOCAL work_mem='64MB'")
  # Freshly populated dimensions need statistics before the large fact joins.

  dimensions_analyzed=False
  for statement in (ROOT/'sql/03_load_dw.sql').read_text().split(';\n'):
   if statement.strip():
    target=re.search(r'(?:INSERT INTO|ANALYZE) (dw\.\w+)',statement)
    if target:print('  DW',target.group(1),flush=True)
    if target and target.group(1).startswith('dw.fact_') and not dimensions_analyzed:
     for dim in ('dim_product','dim_store','dim_week','dim_day','dim_household','dim_campaign','dim_coupon'):
      c.execute(sql.SQL('ANALYZE {}').format(sql.Identifier('dw',dim)))
     dimensions_analyzed=True
    started=time.monotonic()
    c.execute(statement)
    if target:print(f'  DONE {target.group(1)} ({time.monotonic()-started:.1f}s)',flush=True)
  if fail_at=='after-dw':raise RuntimeError('Intentional failure after DW; transaction must roll back')
  check('nonempty_sales',"SELECT CASE WHEN EXISTS(SELECT 1 FROM dw.fact_sales) THEN 0 ELSE 1 END")
  c.execute((ROOT/'sql/04_source_views.sql').read_text())
  c.execute((ROOT/'sql/10_marts.sql').read_text())
  for m in MARTS:
   print('Refresh',m,flush=True)
   c.execute(sql.SQL('REFRESH MATERIALIZED VIEW {}').format(sql.Identifier('mart',m)))
   c.execute(sql.SQL('ANALYZE {}').format(sql.Identifier('mart',m)))
  if fail_at=='before-publish':raise RuntimeError('Intentional failure before publish')
  check('sales_count',"SELECT (SELECT count(*) FROM dw.fact_sales)-(SELECT count(*) FROM stg.transaction_data WHERE valid)")
  check('sales_sum',"SELECT COALESCE((SELECT sum(sales_value) FROM dw.fact_sales),0)-COALESCE((SELECT sum(round(sales_value,2)) FROM stg.transaction_data WHERE valid),0)")
  check('mart_sales_rows','SELECT (SELECT count(*) FROM mart.sales_detail)-(SELECT count(*) FROM dw.fact_sales)')
  check('mart_sales_sum','SELECT COALESCE((SELECT sum(sales_value) FROM mart.sales_detail),0)-COALESCE((SELECT sum(sales_value) FROM dw.fact_sales),0)')
  check('promotion_no_fanout','SELECT COALESCE((SELECT sum(sales_value) FROM mart.promotion_sales),0)-COALESCE((SELECT sum(sales_value) FROM dw.fact_sales),0)')
  check('promotion_lineage','SELECT COALESCE((SELECT sum(source_row_count) FROM dw.fact_promotion),0)-(SELECT count(*) FROM stg.causal_data WHERE valid)')
  check('redemption_rows','SELECT (SELECT count(*) FROM dw.fact_coupon_redemption)-(SELECT count(*) FROM stg.coupon_redempt WHERE valid)')
  check('bridge_rows','SELECT (SELECT count(*) FROM dw.bridge_coupon_product)-(SELECT count(*) FROM (SELECT DISTINCT campaign,coupon_upc,product_id FROM stg.coupon WHERE valid) a)')
  check('contacts_rows','SELECT (SELECT count(*) FROM dw.fact_campaign_contact)-(SELECT count(*) FROM (SELECT DISTINCT campaign,household_key FROM stg.campaign_table WHERE valid) a)')
  check('household_versions',"SELECT count(*) FROM dw.fact_sales f JOIN dw.dim_household h USING(household_key) WHERE f.household_id<>h.household_id OR f.source_day<h.effective_from_day OR f.source_day>=COALESCE(h.effective_to_day,2147483647)")
  check('rfm_one_per_household','SELECT count(*)-count(DISTINCT household_key) FROM mart.household_rfm')
  check('campaign_response','SELECT count(*) FROM mart.campaign WHERE responding_households>contacted_households')
  check('zero_quantity','SELECT count(*) FROM stg.transaction_data WHERE valid AND quantity=0','WARN')
  check('negative_quantity','SELECT count(*) FROM stg.transaction_data WHERE valid AND quantity<0','WARN')
  check('money_rounding','SELECT count(*) FROM stg.transaction_data WHERE valid AND sales_value<>round(sales_value,2)','WARN')
  check('redemption_no_contact','SELECT count(*) FROM src.coupon_redempt r WHERE NOT EXISTS(SELECT 1 FROM src.campaign_table c WHERE c.campaign=r.campaign AND c.household_key=r.household_key)','WARN')
  check('redemption_outside_period','SELECT count(*) FROM src.coupon_redempt r JOIN src.campaign_desc d USING(campaign) WHERE r.day NOT BETWEEN d.start_day AND d.end_day','WARN')
  c.execute("INSERT INTO mart.release VALUES(true,%s,now()) ON CONFLICT(singleton) DO UPDATE SET version=excluded.version,published_at=excluded.published_at",(run,))
  c.execute('INSERT INTO audit.release_meta VALUES(%s,%s,%s,%s,%s)',(run,VERSION,'dw -> src -> mart',manifest,'minimart-kpi-v2'))
  c.execute('INSERT INTO audit.committed_file SELECT file_id,%s FROM audit.source_file ON CONFLICT DO NOTHING',(run,))
  c.execute("INSERT INTO audit.watermark SELECT 'sales',max(source_day),%s FROM dw.fact_sales ON CONFLICT(source_name) DO UPDATE SET max_day=excluded.max_day,run_id=excluded.run_id",(run,))
  c.execute("UPDATE audit.runs SET status='PUBLISHED',finished_at=now(),message='DW, mart and watermark committed atomically' WHERE run_id=%s",(run,))
 return checks


def _run_pipeline(data_dir=None,sales_batch=None,allow_rejects=False,force=False,fail_at=None,causal_limit=DEFAULT_CAUSAL_LIMIT,causal_sample=None):
 run=uuid.uuid4().hex
 with connect(autocommit=True) as c:
  if not c.execute('SELECT pg_try_advisory_lock(760501)').fetchone()[0]:raise RuntimeError('Another ETL/publisher is running. Retry later.')
  try:
   with c.transaction():
    setup(c)
    ensure_scope(c,causal_limit)
   c.execute("UPDATE audit.steps SET status='ABORTED',finished_at=now(),message='Previous process stopped before completion' WHERE status='RUNNING'")
   c.execute("UPDATE audit.runs SET status='ABORTED',finished_at=now(),message='Previous process stopped before completion; publication was not committed' WHERE status='RUNNING'")
   c.execute("INSERT INTO audit.runs(run_id,status) VALUES(%s,'RUNNING')",(run,))
   try:
    inputs=[]
    if sales_batch:inputs=[('transaction_data',Path(sales_batch))]
    else:inputs=[(t,causal_sample if t=='causal_data' and causal_sample else Path(data_dir or ROOT/'Data')/(t+'.csv')) for t in TABLES]
    for t,path in inputs:
     if not path.is_file():raise FileNotFoundError(path)
     sha=digest(path)
     if not sales_batch:
      prior=c.execute('SELECT sha256 FROM audit.source_file WHERE source_name=%s ORDER BY created_at LIMIT 1',(t,)).fetchone()
      if prior and prior[0]!=sha:raise ValueError(f'{t}: baseline checksum changed. Use a fresh project/database for replacement; --sales-batch only for disjoint new events.')
     with step(c,run,'raw/stg:'+path.name):ingest(c,t,path,sha)
    pending=c.execute('SELECT count(*) FROM audit.source_file s WHERE NOT EXISTS(SELECT 1 FROM audit.committed_file f WHERE f.file_id=s.file_id)').fetchone()[0]
    if pending==0 and not force and not fail_at and c.execute('SELECT 1 FROM mart.release').fetchone():
     # Fast replay: immutable committed files need neither restaging nor a 37M-row rescan.
     c.execute("INSERT INTO audit.files SELECT %s,filename,sha256,source_rows,loaded_rows FROM audit.files WHERE run_id=(SELECT version FROM mart.release)",(run,))
     c.execute("INSERT INTO audit.batch_file SELECT %s,s.file_id,s.row_count,0,coalesce(r.n,0),s.row_count-coalesce(r.n,0) FROM audit.source_file s LEFT JOIN (SELECT file_id,count(DISTINCT source_row_no) n FROM audit.rejects GROUP BY file_id) r USING(file_id)",(run,))
     c.execute("UPDATE audit.runs SET status='SKIPPED',finished_at=now(),message='Identical committed files; no source scan or DW writes' WHERE run_id=%s",(run,))
     print('SKIPPED',run,flush=True);return run
    with step(c,run,'validate-staging'):relational_validation(c)
    for fid,t,filename,sha,n in c.execute('SELECT file_id,source_name,filename,sha256,row_count FROM audit.source_file').fetchall():
     accepted=c.execute(f'SELECT count(*) FROM stg.{t} WHERE file_id=%s AND valid',(fid,)).fetchone()[0]
     committed=bool(c.execute('SELECT 1 FROM audit.committed_file WHERE file_id=%s',(fid,)).fetchone())
     c.execute('INSERT INTO audit.batch_file VALUES(%s,%s,%s,%s,%s,%s)',(run,fid,n,0 if committed else accepted,n-accepted,accepted if committed else 0))
     c.execute('INSERT INTO audit.files VALUES(%s,%s,%s,%s,%s)',(run,filename,sha,n,accepted))
    rejects=c.execute('SELECT count(*) FROM (SELECT DISTINCT file_id,source_row_no FROM audit.rejects) a').fetchone()[0]
    if rejects and not allow_rejects:raise ValueError(f'{rejects} rejected rows; inspect audit.rejects. Use --allow-rejects only to explicitly publish accepted rows.')
    if c.execute('SELECT count(DISTINCT source_name) FROM audit.source_file').fetchone()[0]!=8:raise ValueError('Load all eight baseline CSVs first')
    manifest=hashlib.sha256(json.dumps(c.execute('SELECT file_id FROM audit.source_file ORDER BY file_id').fetchall()).encode()).hexdigest()
    prior=c.execute('SELECT manifest_hash FROM audit.release_meta WHERE version=(SELECT version FROM mart.release)').fetchone()
    if prior and prior[0]==manifest and not force and not fail_at:
     c.execute("UPDATE audit.runs SET status='SKIPPED',finished_at=now(),message='Identical manifest; no DW or mart writes' WHERE run_id=%s",(run,));print('SKIPPED',run,flush=True);return run
    with step(c,run,'load-dw-refresh-publish'):publish(c,run,manifest,fail_at)
    out=EVIDENCE/'etl';out.mkdir(parents=True,exist_ok=True)
    result={'run_id':run,'status':'PUBLISHED','pipeline_version':VERSION+'+'+PATCH_VERSION,'causal_limit':causal_limit,'promotion_scope':'first CSV records; not a representative sample' if causal_limit else 'full source','source_layer':'dw -> src -> mart','database':c.execute('SELECT version()').fetchone()[0],'files':c.execute('SELECT filename,source_rows,loaded_rows,sha256 FROM audit.files WHERE run_id=%s',(run,)).fetchall(),'checks':c.execute('SELECT check_name,severity,observed,passed FROM audit.checks WHERE run_id=%s',(run,)).fetchall()}
    (out/(run+'.json')).write_text(json.dumps(result,default=str,ensure_ascii=False,indent=2));print('PUBLISHED',run,flush=True);return run
   except Exception as e:
    out=EVIDENCE/'etl';out.mkdir(parents=True,exist_ok=True)
    (out/(run+'_failed.json')).write_text(json.dumps({'run_id':run,'status':'FAILED','error':str(e)},ensure_ascii=False,indent=2))
    try:
     if not c.closed:c.execute("UPDATE audit.runs SET status='FAILED',finished_at=now(),message=%s WHERE run_id=%s",(str(e)[:2000],run))
    except Exception:pass  # Local failure evidence survives DB outage; next run marks interrupted rows ABORTED.
    raise
  finally:
   if not c.closed:c.execute('SELECT pg_advisory_unlock(760501)')

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--causal-limit',type=int,default=DEFAULT_CAUSAL_LIMIT,help='First N causal CSV records; default 2000000; 0 = full. Scope changes require a fresh DB.');ap.add_argument('--data-dir',type=Path);ap.add_argument('--sales-batch',type=Path);ap.add_argument('--allow-rejects',action='store_true');ap.add_argument('--force',action='store_true');ap.add_argument('--fail-at',choices=['after-dw','before-publish']);a=ap.parse_args()
 run_pipeline(a.data_dir,a.sales_batch,a.allow_rejects,a.force,a.fail_at,a.causal_limit)
