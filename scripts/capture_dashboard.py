"""Optional screenshot tool. Run on host with playwright + chromium installed."""
import argparse,time,urllib.parse
from pathlib import Path
from playwright.sync_api import sync_playwright
parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://localhost:8502');args=parser.parse_args()
out=Path(__file__).resolve().parents[1]/'evidence/dashboard';out.mkdir(exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch();page=b.new_page(viewport={'width':1500,'height':1050})
 for i,name in enumerate(['Bán hàng','Hộ khách hàng','Chiến dịch và coupon','Sản phẩm và quảng bá','Chất lượng dữ liệu'],1):
  page.goto(args.url+'/?page='+urllib.parse.quote(name));page.get_by_test_id('stMetric').first.wait_for(timeout=120000);time.sleep(3)
  if page.get_by_test_id('stException').count():raise RuntimeError('Dashboard error: '+name)
  page.screenshot(path=str(out/f'{i:02}.png'),full_page=True)
 b.close()
