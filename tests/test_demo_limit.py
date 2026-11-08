import ast
import csv
import hashlib
import itertools
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]/'scripts/etl.py'
ns = dict(csv=csv,itertools=itertools,hashlib=hashlib)
tree=ast.parse(SOURCE.read_text())
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('prepare_causal_sample','ensure_scope','digest')],type_ignores=[]),str(SOURCE),'exec'),ns)

class DB:
 def __init__(self,scope=None,existing=False):self.scope=scope;self.existing=existing;self.inserted=False
 def execute(self,q,args=None):
  self.result=None
  if q.startswith('SELECT causal_limit'):self.result=None if self.scope is None else (self.scope,)
  elif q.startswith('SELECT 1 FROM audit.source_file'):self.result=(1,) if self.existing else None
  elif q.startswith('INSERT INTO audit.demo_scope'):self.inserted=True
  return self
 def fetchone(self):return self.result

class Tests(unittest.TestCase):
 def test_prefix_records_and_original_unchanged(self):
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/'original.csv';out=Path(d)/'sample.csv'
   src.write_text('\ufeffa,b\n1,"two\nlines"\n2,"quote""x"\n3,z\n',encoding='utf-8')
   before=src.read_bytes()
   self.assertEqual(ns['prepare_causal_sample'](src,out,2),2)
   with out.open(newline='') as f:self.assertEqual(list(csv.reader(f)),[['a','b'],['1','two\nlines'],['2','quote"x']])
   self.assertEqual(src.read_bytes(),before)
   one=ns['digest'](out);ns['prepare_causal_sample'](src,out,2);self.assertEqual(ns['digest'](out),one)
 def test_short_source(self):
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/'a.csv';src.write_text('a,b\n1,2\n')
   self.assertEqual(ns['prepare_causal_sample'](src,Path(d)/'out.csv',2000000),1)
 def test_malformed(self):
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/'a.csv';src.write_text('a,b\n1,2,3\n')
   with self.assertRaises(ValueError):ns['prepare_causal_sample'](src,Path(d)/'out.csv',2)
 def test_empty(self):
  with tempfile.TemporaryDirectory() as d:
   src=Path(d)/'a.csv';src.write_text('a,b\n')
   with self.assertRaises(ValueError):ns['prepare_causal_sample'](src,Path(d)/'out.csv',2)
 def test_old_full_database_blocked(self):
  db=DB(existing=True)
  with self.assertRaises(ValueError):ns['ensure_scope'](db,2000000)
  self.assertFalse(db.inserted)
 def test_new_database_records_scope(self):
  db=DB();ns['ensure_scope'](db,2000000);self.assertTrue(db.inserted)
 def test_replay_scope(self):ns['ensure_scope'](DB(scope=2000000,existing=True),2000000)
 def test_scope_change_blocked(self):
  with self.assertRaises(ValueError):ns['ensure_scope'](DB(scope=2000000,existing=True),1000000)

if __name__=='__main__':unittest.main()
