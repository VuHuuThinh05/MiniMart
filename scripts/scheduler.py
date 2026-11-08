"""Single-process batch schedule, no overlapping launches, retry next interval.
No CDC: checks immutable baseline files; changed baselines fail with an audit record.
"""
import argparse,subprocess,sys,time,signal
from common import ROOT
stop=False
child=None
def shutdown(*_):
 global stop
 stop=True
 if child and child.poll() is None:child.terminate()
signal.signal(signal.SIGTERM,shutdown);signal.signal(signal.SIGINT,shutdown)
a=argparse.ArgumentParser();a.add_argument('--interval',type=int,default=86400);args=a.parse_args()
if args.interval<60:raise ValueError('Interval must be at least 60 seconds')
while not stop:
 child=subprocess.Popen([sys.executable,'-u',str(ROOT/'scripts/etl.py')]);code=child.wait()
 print('Scheduled ETL exit:',code,flush=True)
 deadline=time.monotonic()+args.interval
 while not stop and time.monotonic()<deadline:time.sleep(min(1,max(0,deadline-time.monotonic())))
