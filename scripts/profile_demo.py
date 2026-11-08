"""Run the three source-profile reports displayed by the dashboard."""
import subprocess,sys,json
from datetime import datetime,timezone
from common import ROOT
jobs=[('08_Business_Key_Profiling.py','06_Business_Key_Profiling'),('13_Coupon_Product_Profiling.py','10_Cross_Table_Profiling'),('14_Campaign_Redemption_Profiling.py','10_Cross_Table_Profiling')]
for name,folder in jobs:
 subprocess.run([sys.executable,str(ROOT/'scripts/profiling'/name),'--input-dir',str(ROOT/'Data'),'--output-dir',str(ROOT/'evidence/profiling/local_check'/folder)],check=True)
(ROOT/'evidence/profiling/local_check/run_metadata.json').write_text(json.dumps({'utc':datetime.now(timezone.utc).isoformat(),'scripts':[x[0] for x in jobs],'scope':'CSV profiling, not PostgreSQL ETL validation'},indent=2))
