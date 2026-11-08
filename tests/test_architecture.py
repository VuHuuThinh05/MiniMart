"""Offline tests with synthetic catalog metadata, NOT the user's database."""
import ast
import unittest
from pathlib import Path
from xml.etree import ElementTree

APP = Path(__file__).resolve().parents[1] / 'dashboard/app.py'
TREE = ast.parse(APP.read_text(encoding='utf-8'), feature_version=(3, 11))
ARCH = [n for n in TREE.body if
        (isinstance(n, ast.FunctionDef) and n.name.startswith('arch_')) or
        (isinstance(n, ast.FunctionDef) and n.name == 'render_architecture') or
        (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id.startswith('ARCH_') for t in n.targets))]
NS = {}
exec(compile(ast.Module(body=ARCH, type_ignores=[]), str(APP), 'exec'), NS)
REL = [dict(oid=1,schema_name='dev_src',name='transaction_data',kind='r'),
       dict(oid=2,schema_name='dev_src',name='product',kind='r'),
       dict(oid=3,schema_name='mart',name='sales_base',kind='v'),
       dict(oid=4,schema_name='mart',name='basket',kind='m')]
COLS = [dict(oid=r['oid'],position=1,name='basket_id',data_type='bigint',not_null=False,pk=False,fk=False) for r in REL]
EDGES = [dict(source=1,target=3),dict(source=2,target=3),dict(source=3,target=4)]
FIXTURE = dict(relations=REL,columns=COLS,keys=[],deps=EDGES,indexes=[],database=dict(db='fixture',role='reader',engine='synthetic'),read_at='fixture time')

class ArchitectureTests(unittest.TestCase):
    def test_scope_one_hop(self):
        self.assertEqual(NS['arch_scope']({1,2,3,4},EDGES,4,1),{3,4})
    def test_scope_two_hops(self):
        self.assertEqual(NS['arch_scope']({1,2,3,4},EDGES,4,2),{1,2,3,4})
    def test_missing_nodes_and_cycle(self):
        self.assertEqual(NS['arch_scope']({1,2},[dict(source=1,target=2),dict(source=2,target=1),dict(source=2,target=99)],1,3),{1,2})
    def test_svg_escape_and_self_reference(self):
        rel=[dict(oid=1,schema_name='x',name='<script>&"',kind='r')]
        svg=NS['arch_svg'](rel,[],[dict(source=1,target=1,definition='<unsafe>')],1,True)
        ElementTree.fromstring(svg)
        self.assertNotIn('<script>',svg)
        self.assertIn('&lt;script&gt;',svg)
        self.assertIn('marker-end',svg)
    def test_svg_columns_and_no_fake_fk(self):
        svg=NS['arch_svg'](REL,COLS,[],None,True)
        ElementTree.fromstring(svg)
        self.assertNotIn('marker-end=',svg)
        self.assertIn('basket_id',svg)
    def test_catalog_sql_syntax(self):
        from pglast import parse_sql
        for key,val in NS.items():
            if key.startswith('ARCH_'):parse_sql(val)
    def test_readonly_loader(self):
        calls=[]
        values=[REL,COLS,[],EDGES,[],[FIXTURE['database']]]
        class Conn:
            def __enter__(self):return self
            def __exit__(self,*a):pass
            def execute(self,q,*a):
                calls.append(q)
                if q.startswith('SET'):self.rows=[]
                else:self.rows=values.pop(0)
                return self
            def fetchall(self):return self.rows
            def fetchone(self):return self.rows[0]
        NS['connect']=lambda:Conn()
        result=NS['arch_load']()
        self.assertEqual(result['relations'],REL)
        self.assertIn('READ ONLY',calls[0])
        self.assertEqual(len(calls),8)
    def test_streamlit_four_tabs(self):
        from streamlit.testing.v1 import AppTest
        code='import streamlit as st\nimport pandas as pd\nimport psycopg\n'
        code+='\n'.join(ast.unparse(n) for n in ARCH)
        code+='\nst.session_state["arch_metadata"]='+repr(FIXTURE)+'\n'
        code+='''
class Conn:
 def __enter__(self):return self
 def __exit__(self,*a):pass
 def execute(self,*a):return self
 def fetchone(self):return {'sql':'SELECT 1;'}
def connect():return Conn()
render_architecture()
'''
        at=AppTest.from_string(code).run(timeout=20)
        self.assertEqual(len(at.exception),0,str(at.exception))
        self.assertEqual([t.label for t in at.tabs],['ERD vật lý','Luồng nguồn → mart','Từ điển cấu trúc','Định nghĩa SQL'])
        self.assertTrue(any('Không có khóa ngoại' in i.value for i in at.info))
        at.selectbox(key='arch_focus_lineage').select(3).run()
        self.assertEqual(len(at.exception),0,str(at.exception))
        at.checkbox(key='arch_columns_lineage').check().run()
        self.assertEqual(len(at.exception),0,str(at.exception))

if __name__=='__main__':unittest.main(verbosity=2)
