"""BM01: identical results, alternating warm runs, execution plans + refresh cost."""
import json,csv,time,statistics,platform,os,math
from datetime import datetime,timezone
from common import ROOT,connect,EVIDENCE
DIRECT='SELECT week_no,department,SUM(sales_value) AS sales_value,COUNT(DISTINCT basket_id) AS baskets FROM bench.sales_snapshot GROUP BY week_no,department ORDER BY week_no,department'
MV='SELECT week_no,department,sales_value,baskets FROM bench.sales_week_department ORDER BY week_no,department'
def main():
 out=EVIDENCE/'bm01';out.mkdir(parents=True,exist_ok=True)
 with connect() as c:
  c.execute('SELECT pg_advisory_xact_lock(760501)')
  version=c.execute('SELECT version FROM mart.release').fetchone()[0]
  c.execute('CREATE SCHEMA IF NOT EXISTS bench')
  c.execute('DROP MATERIALIZED VIEW IF EXISTS bench.sales_week_department')
  c.execute('DROP TABLE IF EXISTS bench.sales_snapshot')
  c.execute('CREATE TABLE bench.sales_snapshot AS SELECT week_no,department,basket_id,sales_value FROM mart.sales_base')
  c.execute('ANALYZE bench.sales_snapshot')
  started=time.perf_counter()
  c.execute('CREATE MATERIALIZED VIEW bench.sales_week_department AS '+DIRECT)
  create_ms=(time.perf_counter()-started)*1000
  c.execute('ANALYZE bench.sales_week_department')
  a=c.execute(DIRECT).fetchall();b=c.execute(MV).fetchall()
  assert a==b,'BM01 results differ; no timing conclusion permitted'
  meta={'utc':datetime.now(timezone.utc).isoformat(),'release':version,'database_version':c.execute('select version()').fetchone()[0],'host_platform':platform.platform(),'client_python':platform.python_version(),'cpu_visible':os.cpu_count(),'result_rows':len(a),'equal':True,'source_rows':c.execute('select count(*) from dw.fact_sales').fetchone()[0],'method':'Three warmups each; fifteen alternating pairs; EXPLAIN ANALYZE BUFFERS FORMAT JSON; warm cache, no cache purge. Not end-to-end HTTP latency.','settings':{k:c.execute('SHOW '+k).fetchone()[0] for k in ['shared_buffers','work_mem','max_parallel_workers_per_gather','jit']}}
  for q in [DIRECT,MV]:
   for _ in range(3):c.execute(q).fetchall()
  timings=[]
  for i in range(15):
   for label,q in ([('direct',DIRECT),('materialized',MV)] if i%2==0 else [('materialized',MV),('direct',DIRECT)]):
    plan=c.execute('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+q).fetchone()[0]
    (out/f'{label}_{i+1}.json').write_text(json.dumps(plan,indent=2))
    timings.append(dict(iteration=i+1,variant=label,execution_ms=plan[0]['Execution Time'],planning_ms=plan[0]['Planning Time']))
  t=time.perf_counter();c.execute('REFRESH MATERIALIZED VIEW bench.sales_week_department');meta['refresh_ms']=(time.perf_counter()-t)*1000
  assert c.execute(MV).fetchall()==a
  meta['create_ms']=create_ms
  meta['source_layer']='bench.sales_snapshot copied from mart.sales_base over dw.fact_sales; scan vs preaggregation, not full dashboard latency'
  meta['source_manifest']=[dict(zip(['filename','sha256','source_rows','loaded_rows'],r)) for r in c.execute('SELECT filename,sha256,source_rows,loaded_rows FROM audit.files WHERE run_id=%s ORDER BY filename',(version,)).fetchall()]
  meta['mv_bytes']=c.execute("SELECT pg_total_relation_size('bench.sales_week_department')").fetchone()[0]
  for label in ['direct','materialized']:
   v=[x['execution_ms'] for x in timings if x['variant']==label];meta[label]={'median_ms':statistics.median(v),'min_ms':min(v),'max_ms':max(v),'p95_ms':sorted(v)[math.ceil(.95*len(v))-1]}
  meta['speedup']=meta['direct']['median_ms']/meta['materialized']['median_ms']
  (out/'summary.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
  with (out/'timings.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=timings[0]);w.writeheader();w.writerows(timings)
  (out/'queries.sql').write_text('-- Direct\n'+DIRECT+';\n-- Materialized\n'+MV+';\n')
  print(json.dumps(meta,indent=2))
if __name__=='__main__':main()
