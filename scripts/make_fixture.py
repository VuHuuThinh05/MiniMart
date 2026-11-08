"""Small deterministic test dataset, never mixed with production Data."""
import csv
from pathlib import Path
from model import TABLES

def write(path,table,rows):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=[n for n,_ in TABLES[table]]);w.writeheader();w.writerows(rows)

def generate(path):
 path=Path(path)
 data={
 'product':[dict(product_id=i,manufacturer=1,department='GROCERY' if i==1 else 'DRUG GM',brand='National',commodity_desc='Demo',sub_commodity_desc='Demo',curr_size_of_product='1') for i in (1,2)],
 'hh_demographic':[dict(household_key=1,age_desc='35-44',marital_status_code='A',income_desc='35-49K',homeowner_desc='Homeowner',hh_comp_desc='2 Adults',household_size_desc='2',kid_category_desc='None')],
 'campaign_desc':[dict(description='TypeA',campaign=1,start_day=95,end_day=110),dict(description='TypeB',campaign=2,start_day=100,end_day=110)],
 'campaign_table':[dict(description='TypeA',household_key=h,campaign=1) for h in (1,2)],
 'coupon':[dict(coupon_upc='000123',product_id=i,campaign=1) for i in (1,2,2)],
 'coupon_redempt':[dict(household_key=1,day=100,coupon_upc='000123',campaign=1)],
 'causal_data':[dict(product_id=1,store_id=1,week_no=15,display='0',mailer='A'),dict(product_id=1,store_id=1,week_no=15,display='1',mailer='0'),dict(product_id=1,store_id=1,week_no=15,display='1',mailer='0')],
 'transaction_data':[]}
 for h,b,d,pr,amt in [(1,101,90,1,'10.005'),(1,102,100,1,'20'),(1,102,100,2,'5'),(2,201,100,1,'25'),(2,202,110,2,'10.01')]:
  data['transaction_data'].append(dict(household_key=h,basket_id=b,day=d,product_id=pr,quantity=1,sales_value=amt,store_id=1,retail_disc=0,trans_time=1200,week_no=15 if d==100 else 16 if d==110 else 13,coupon_disc=0,coupon_match_disc=0))
 for t,rows in data.items():write(path/(t+'.csv'),t,rows)
 return data
if __name__=='__main__':
 from common import ROOT
 generate(ROOT/'fixtures/base');print('Created fixtures/base')
