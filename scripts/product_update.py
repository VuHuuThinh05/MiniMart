"""Audited SCD Type 1 update; stable product_key preserves bridge/fact links."""
import argparse,json,uuid
from pathlib import Path
from common import connect
from etl import publish
ALLOWED={'manufacturer','department','brand','commodity_desc','sub_commodity_desc','curr_size_of_product'}
def change(c,product_id,attrs,event_id):
 if any(v is not None and not isinstance(v,str) for v in attrs.values()):raise ValueError('Attribute values must be text or null')
 if not attrs or set(attrs)-ALLOWED:raise ValueError('Invalid product attributes')
 previous=c.execute('SELECT product_id,payload FROM audit.product_events WHERE event_id=%s',(event_id,)).fetchone()
 if previous:
  if previous!=(product_id,attrs):raise ValueError('Event ID reused with different content')
  return False
 if not c.execute('SELECT 1 FROM dw.dim_product WHERE product_id=%s',(product_id,)).fetchone():raise ValueError('Product not found')
 from psycopg import sql
 assignments=sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in attrs)
 c.execute(sql.SQL('UPDATE dw.dim_product SET {},updated_at=now() WHERE product_id=%s').format(assignments),(*attrs.values(),product_id))
 c.execute('INSERT INTO audit.product_events(event_id,product_id,payload) VALUES(%s,%s,%s::jsonb)',(event_id,product_id,json.dumps(attrs)))
 return True
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--product',required=True);ap.add_argument('--attributes-file',type=Path,required=True);ap.add_argument('--event-id',required=True);a=ap.parse_args()
 attrs=json.loads(a.attributes_file.read_text());run=uuid.uuid4().hex
 with connect(autocommit=True) as c:
  if not c.execute('SELECT pg_try_advisory_lock(760501)').fetchone()[0]:raise RuntimeError('Publisher busy')
  c.execute("INSERT INTO audit.runs(run_id,status) VALUES(%s,'RUNNING')",(run,))
  try:
   with c.transaction():
    if change(c,a.product,attrs,a.event_id):
     manifest=c.execute('SELECT manifest_hash FROM audit.release_meta WHERE version=(SELECT version FROM mart.release)').fetchone()[0]
     c.execute('INSERT INTO audit.files SELECT %s,filename,sha256,source_rows,loaded_rows FROM audit.files WHERE run_id=(SELECT version FROM mart.release)',(run,))
     publish(c,run,manifest)
    else:c.execute("UPDATE audit.runs SET status='SKIPPED',finished_at=now() WHERE run_id=%s",(run,))
  except Exception as e:
   c.execute("UPDATE audit.runs SET status='FAILED',finished_at=now(),message=%s WHERE run_id=%s",(str(e),run));raise
  finally:c.execute('SELECT pg_advisory_unlock(760501)')
