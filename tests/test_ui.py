"""Streamlit AppTest uses a running published test DB; optional development dependency streamlit."""
import os,json
from pathlib import Path
from streamlit.testing.v1 import AppTest
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('EVIDENCE_DIR',str(ROOT/'evidence'))
a=AppTest.from_file(str(ROOT/'dashboard/app.py'),default_timeout=60).run()
results=[]
for page in ['Bán hàng','Hộ khách hàng','Chiến dịch và coupon','Sản phẩm và quảng bá','Chất lượng dữ liệu','Kiến trúc & ERD','Vận hành ETL']:
 a.sidebar.radio[0].set_value(page).run()
 errors=[x.message for x in a.exception]
 results.append({'page':page,'passed':not errors,'errors':errors})
 if errors:break
if all(x['passed'] for x in results):
 a.sidebar.radio[0].set_value('Hộ khách hàng').run();a.sidebar.number_input[1].set_value(10).run()
 results.append({'page':'RFM custom window','passed':not a.exception and bool(a.warning),'errors':[x.message for x in a.exception]})
 a.sidebar.radio[0].set_value('Bán hàng').run();a.sidebar.text_input[0].set_value('999999999').run()
 results.append({'page':'Empty product filter','passed':not a.exception and bool(a.info),'errors':[x.message for x in a.exception]})
out=ROOT/'evidence/tests/ui.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(results,ensure_ascii=False,indent=2));print(out.read_text())
if not all(x['passed'] for x in results):raise SystemExit(1)
