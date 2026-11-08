"""Explicit, idempotent dimension changes. Never infer history from a static CSV."""
import argparse,json,uuid,hashlib
from common import connect
from model import DEMO_COLS
from etl import setup,publish,step

def household_change(c,household_id,day,attrs,event_id):
 if any(v is not None and not isinstance(v,str) for v in attrs.values()):raise ValueError('Attribute values must be text or null')
 if day<0 or not attrs or set(attrs)-set(DEMO_COLS):raise ValueError('Invalid effective day/attributes')
 payload=json.dumps(attrs,sort_keys=True)
 oldevent=c.execute('SELECT household_id,effective_day,payload FROM audit.scd_events WHERE event_id=%s',(event_id,)).fetchone()
 if oldevent:
  if oldevent!=(household_id,day,attrs):raise ValueError('Event ID reused with changed content')
  return False
 row=c.execute('SELECT household_key,effective_from_day,effective_to_day,is_current,'+','.join(DEMO_COLS)+',has_demographics FROM dw.dim_household WHERE household_id=%s AND effective_from_day<=%s AND (effective_to_day IS NULL OR %s<effective_to_day) FOR UPDATE',(household_id,day,day)).fetchone()
 if not row:raise ValueError('Household/version not found')
 key,start,end,current,*rest=row
 values=dict(zip(DEMO_COLS,rest[:-1]));values.update(attrs)
 if day==start:
  if any(values[x]!=rest[i] for i,x in enumerate(DEMO_COLS)):raise ValueError('Boundary already exists with different attributes; use a new effective day')
 else:
  c.execute('UPDATE dw.dim_household SET effective_to_day=%s,is_current=false WHERE household_key=%s',(day,key))
  names=','.join(DEMO_COLS)
  c.execute(f'INSERT INTO dw.dim_household(household_id,effective_from_day,effective_to_day,is_current,{names},has_demographics,change_reason) VALUES('+','.join(['%s']*(6+len(DEMO_COLS)))+')',(household_id,day,end,current,*[values[x] for x in DEMO_COLS],True,'Explicit change '+event_id))
 # Retroactive dimension events re-key already loaded facts inside the same publication transaction.
 for table,date in [('fact_sales','f.source_day'),('fact_coupon_redemption','f.source_day'),('fact_campaign_contact','(SELECT start_day FROM dw.dim_campaign d WHERE d.campaign_key=f.campaign_key)')]:
  c.execute(f'UPDATE dw.{table} f SET household_key=h.household_key FROM dw.dim_household h WHERE f.household_id=%s AND h.household_id=f.household_id AND {date}>=h.effective_from_day AND (h.effective_to_day IS NULL OR {date}<h.effective_to_day) AND f.household_key<>h.household_key',(household_id,))
 c.execute('INSERT INTO audit.scd_events(event_id,household_id,effective_day,payload) VALUES(%s,%s,%s,%s::jsonb)',(event_id,household_id,day,payload))
 return True

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--household',required=True);ap.add_argument('--day',required=True,type=int);ap.add_argument('--attributes',required=True,help='JSON object or @path.json');ap.add_argument('--event-id',required=True);a=ap.parse_args()
 from pathlib import Path
 attrs=json.loads(Path(a.attributes[1:]).read_text() if a.attributes.startswith('@') else a.attributes)
 run=uuid.uuid4().hex
 with connect(autocommit=True) as c:
  if not c.execute('SELECT pg_try_advisory_lock(760501)').fetchone()[0]:raise RuntimeError('Publisher busy')
  try:
   c.execute("INSERT INTO audit.runs(run_id,status) VALUES(%s,'RUNNING')",(run,))
   with step(c,run,'scd2-and-publish'):
    with c.transaction():
     if not household_change(c,a.household,a.day,attrs,a.event_id):
      c.execute("UPDATE audit.runs SET status='SKIPPED',finished_at=now() WHERE run_id=%s",(run,));return
     manifest=c.execute('SELECT manifest_hash FROM audit.release_meta WHERE version=(SELECT version FROM mart.release)').fetchone()[0]
     c.execute('INSERT INTO audit.files SELECT %s,filename,sha256,source_rows,loaded_rows FROM audit.files WHERE run_id=(SELECT version FROM mart.release)',(run,))
     publish(c,run,manifest)
   print('SCD PUBLISHED',run)
  except Exception as e:
   c.execute("UPDATE audit.runs SET status='FAILED',finished_at=now(),message=%s WHERE run_id=%s",(str(e),run));raise
  finally:c.execute('SELECT pg_advisory_unlock(760501)')
if __name__=='__main__':main()
