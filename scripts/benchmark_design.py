"""BM02/BM03: Khanh's 520,000-row synthetic experiment, with equality gates.
Synthetic timings are not production DW/dashboard timings.
"""
import json,csv,statistics,time,platform
from datetime import datetime,timezone
from common import ROOT,connect,EVIDENCE

def main(rows=520000):
 out=EVIDENCE/'bm02_bm03';out.mkdir(parents=True,exist_ok=True)
 runs=[]
 with connect() as c:
  c.execute('SELECT pg_advisory_xact_lock(760501)')
  c.execute('CREATE SCHEMA IF NOT EXISTS bench')
  for t in ['design_plain','design_partitioned','design_single','design_composite']:c.execute('DROP TABLE IF EXISTS bench.'+t+' CASCADE')
  definition='(sale_id bigint NOT NULL,store_key bigint NOT NULL,source_day integer NOT NULL,sales_value numeric(18,2) NOT NULL)'
  for t in ['design_plain','design_single','design_composite']:c.execute('CREATE TABLE bench.'+t+definition)
  c.execute('CREATE TABLE bench.design_partitioned'+definition+' PARTITION BY RANGE(source_day)')
  for k in range(13):c.execute(f'CREATE TABLE bench.design_p{k} PARTITION OF bench.design_partitioned FOR VALUES FROM ({k*28+1}) TO ({(k+1)*28+1})')
  c.execute('INSERT INTO bench.design_plain SELECT i,(i%%50)+1,(i%%364)+1,((i%%5000)+100)::numeric/100 FROM generate_series(1,%s) g(i)',(rows,))
  for t in ['design_single','design_composite','design_partitioned']:c.execute(f'INSERT INTO bench.{t} SELECT * FROM bench.design_plain')
  c.execute('CREATE INDEX ON bench.design_single(store_key)');c.execute('CREATE INDEX ON bench.design_composite(store_key,source_day)')
  for t in ['design_plain','design_partitioned','design_single','design_composite']:c.execute('ANALYZE bench.'+t)
  # Full multiset identity, not merely count/sum checks.
  for t in ['design_partitioned','design_single','design_composite']:
   assert c.execute(f'SELECT NOT EXISTS((SELECT * FROM bench.design_plain EXCEPT ALL SELECT * FROM bench.{t}) UNION ALL (SELECT * FROM bench.{t} EXCEPT ALL SELECT * FROM bench.design_plain))').fetchone()[0]
  queries={v:f'SELECT sum(sales_value) FROM bench.{t} WHERE store_key=7 AND source_day BETWEEN 85 AND 112' for v,t in [('plain','design_plain'),('partitioned','design_partitioned'),('single_index','design_single'),('composite_index','design_composite')]}
  expected=c.execute(queries['plain']).fetchall()
  for q in queries.values():
   assert c.execute(q).fetchall()==expected
   for _ in range(3):c.execute(q).fetchall()
  for i in range(15):
   # Rotate variant order to reduce fixed-order bias.
   order=list(queries);order=order[i%4:]+order[:i%4]
   for v in order:
    p=c.execute('EXPLAIN(ANALYZE,BUFFERS,FORMAT JSON) '+queries[v]).fetchone()[0]
    (out/f'{v}_{i+1}.json').write_text(json.dumps(p,indent=2))
    runs.append(dict(iteration=i+1,variant=v,execution_ms=p[0]['Execution Time'],planning_ms=p[0]['Planning Time']))
  meta={'utc':datetime.now(timezone.utc).isoformat(),'database_version':c.execute('SELECT version()').fetchone()[0],'host_platform':platform.platform(),'rows':rows,'source':'Synthetic generate_series, based on Khanh design; separate bench tables','equal_full_multiset':True,'equal_query':True,'method':'3 warmups, 15 rotating runs per variant, warm cache, no cache purge; partition and index tested separately','settings':{k:c.execute('SHOW '+k).fetchone()[0] for k in ['shared_buffers','work_mem','max_parallel_workers_per_gather','jit']},'variants':{}}
  for v in queries:
   vals=[r['execution_ms'] for r in runs if r['variant']==v]
   meta['variants'][v]={'median_ms':statistics.median(vals),'min_ms':min(vals),'max_ms':max(vals),'p95_ms':sorted(vals)[-1]}
  (out/'summary.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2))
  (out/'queries.sql').write_text('\n'.join('-- '+v+'\n'+q+';' for v,q in queries.items()))
  with (out/'timings.csv').open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=runs[0]);w.writeheader();w.writerows(runs)
 print(json.dumps(meta,indent=2))
if __name__=='__main__':main()
