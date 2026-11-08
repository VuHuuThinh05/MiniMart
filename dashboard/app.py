import os
from decimal import Decimal
import pandas as pd
import psycopg
from psycopg.rows import dict_row
import streamlit as st

st.set_page_config(page_title='MiniMart Analytics',page_icon='🛒',layout='wide')
st.markdown('''<style>.block-container{padding-top:2rem;padding-bottom:2rem}h1{font-size:2rem!important}[data-testid="stMetric"]{background:#f1f5f9;border-radius:10px;padding:16px}div[data-testid="stSidebar"]{background:#eef2f6}</style>''',unsafe_allow_html=True)
PAGES=['Bán hàng','Hộ khách hàng','Chiến dịch và coupon','Sản phẩm và quảng bá','Chất lượng dữ liệu','Kiến trúc & ERD','Vận hành ETL']
def connect():
    return psycopg.connect(host=os.getenv('DB_HOST','postgres'),port=os.getenv('DB_PORT','5432'),dbname=os.getenv('DB_NAME','minimart'),user=os.getenv('DB_USER','minimart'),password=os.getenv('DB_PASSWORD','minimart_local_2026'),row_factory=dict_row,prepare_threshold=None)
class ReleaseChanged(Exception):pass
@st.cache_data(show_spinner=False,max_entries=96)
def fetch(version, statements):
    with connect() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        r=c.execute('SELECT version FROM mart.release').fetchone()
        if not r or r['version']!=version:raise ReleaseChanged()
        return [c.execute(q,params).fetchall() for q,params in statements]
def query(statements):
    try:return fetch(version,tuple(statements))
    except ReleaseChanged:
        st.warning('Vừa có phiên bản mới. Bấm Tải lại trang để đồng bộ.');st.stop()
    except psycopg.Error as e:
        st.error('Truy vấn thất bại. Kiểm tra log và chạy lại publish.');st.exception(e);st.stop()
def frame(rows):
    df=pd.DataFrame(rows)
    for col in df:
        if any(isinstance(v,Decimal) for v in df[col].head(20)):df[col]=df[col].map(lambda v:float(v) if isinstance(v,Decimal) else v)
    return df
def table(rows):
    df=frame(rows);st.dataframe(df,hide_index=True,width='stretch');return df
def cards(values):
    for c,(label,value) in zip(st.columns(len(values)),values):c.metric(label,value)
# Kiến trúc động: chỉ đọc catalog, không thay đổi dữ liệu hay quyền.
ARCH_RELATIONS = """
SELECT c.oid::bigint AS oid,n.nspname AS schema_name,c.relname AS name,c.relkind AS kind
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE c.relkind IN ('r','p','v','m','f') AND n.nspname NOT IN ('pg_catalog','information_schema')
AND n.nspname !~ '^pg_' ORDER BY n.nspname,c.relname
"""
ARCH_COLUMNS = """
SELECT a.attrelid::bigint AS oid,a.attnum AS position,a.attname AS name,
pg_catalog.format_type(a.atttypid,a.atttypmod) AS data_type,a.attnotnull AS not_null,
EXISTS(SELECT 1 FROM pg_catalog.pg_constraint k WHERE k.conrelid=a.attrelid AND k.contype='p' AND a.attnum=ANY(k.conkey)) AS pk,
EXISTS(SELECT 1 FROM pg_catalog.pg_constraint k WHERE k.conrelid=a.attrelid AND k.contype='f' AND a.attnum=ANY(k.conkey)) AS fk
FROM pg_catalog.pg_attribute a JOIN pg_catalog.pg_class c ON c.oid=a.attrelid
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE a.attnum>0 AND NOT a.attisdropped AND c.relkind IN ('r','p','v','m','f')
AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_'
ORDER BY a.attrelid,a.attnum
"""
ARCH_KEYS = """
SELECT k.conrelid::bigint AS source,k.confrelid::bigint AS target,k.conname AS name,
k.contype AS kind,pg_catalog.pg_get_constraintdef(k.oid,true) AS definition,k.convalidated AS validated
FROM pg_catalog.pg_constraint k JOIN pg_catalog.pg_class c ON c.oid=k.conrelid
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE k.contype IN ('p','f','u','c','x') AND n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_'
ORDER BY k.conrelid,k.conname
"""
ARCH_DEPS = """
SELECT DISTINCT d.refobjid::bigint AS source,r.ev_class::bigint AS target
FROM pg_catalog.pg_depend d JOIN pg_catalog.pg_rewrite r ON r.oid=d.objid
JOIN pg_catalog.pg_class v ON v.oid=r.ev_class
WHERE d.classid='pg_catalog.pg_rewrite'::regclass AND d.refclassid='pg_catalog.pg_class'::regclass
AND d.deptype='n' AND v.relkind IN ('v','m') AND r.ev_class<>d.refobjid
"""
ARCH_INDEXES = """
SELECT i.indrelid::bigint AS oid,c.relname AS name,i.indisunique AS is_unique,
i.indisprimary AS is_primary,pg_catalog.pg_get_indexdef(i.indexrelid) AS definition
FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class c ON c.oid=i.indexrelid
JOIN pg_catalog.pg_class t ON t.oid=i.indrelid JOIN pg_catalog.pg_namespace n ON n.oid=t.relnamespace
WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname !~ '^pg_'
ORDER BY i.indrelid,c.relname
"""

def arch_load():
    from datetime import datetime, timezone
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        conn.execute("SET LOCAL statement_timeout='15s'")
        data = dict(zip(['relations','columns','keys','deps','indexes'],
                        [conn.execute(q).fetchall() for q in [ARCH_RELATIONS,ARCH_COLUMNS,ARCH_KEYS,ARCH_DEPS,ARCH_INDEXES]]))
        data['database'] = conn.execute('SELECT current_database() AS db,current_user AS role,version() AS engine').fetchone()
    data['read_at'] = datetime.now(timezone.utc).isoformat()
    return data

def arch_scope(ids, edges, focus, hops):
    if focus is None:return set(ids)
    chosen={focus}
    for _ in range(hops):
        old=set(chosen)
        for e in edges:
            if e['source'] in old or e['target'] in old:chosen.update([e['source'],e['target']])
    return chosen & set(ids)

def arch_svg(relations, columns, edges, focus=None, show_columns=False):
    # SVG nội tuyến; không CDN, không cần Graphviz hay gói Python bổ sung.
    from html import escape
    import textwrap
    rel={r['oid']:r for r in relations}
    ids=sorted(rel,key=lambda i:(rel[i]['schema_name'],rel[i]['name']))
    edges=[e for e in edges if e['source'] in rel and e['target'] in rel]
    if focus in rel:
        before={e['source'] for e in edges if e['target']==focus}-{focus}
        groups=[[i for i in ids if i in before],[focus],[i for i in ids if i!=focus and i not in before]]
    else:groups=[ids[i::3] for i in range(3)]
    pos={}; boxes={}; max_y=80
    for col,group in enumerate(groups):
        y=75
        for oid in group:
            r=rel[oid]; lines=[]
            if show_columns:
                for a in columns:
                    if a['oid']==oid:
                        flag=('PK ' if a['pk'] else '')+('FK ' if a['fk'] else '')
                        lines.extend(textwrap.wrap(flag+a['name']+' : '+a['data_type'],42) or [''])
            h=70+18*len(lines); pos[oid]=(30+col*450,y,h); boxes[oid]=lines;y+=h+45
        max_y=max(max_y,y)
    out=[f'<svg xmlns="http://www.w3.org/2000/svg" width="1350" height="{max_y}" viewBox="0 0 1350 {max_y}">',
         '<rect width="100%" height="100%" fill="#f8fafc"/>',
         '<defs><marker id="arrow" markerWidth="9" markerHeight="9" refX="8" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8" fill="#64748b"/></marker></defs>',
         '<text x="30" y="36" font-family="sans-serif" font-size="18" fill="#0f172a">MiniMart • Cấu trúc đọc từ PostgreSQL</text>']
    for e in edges:
        x,y,h=pos[e['source']];xx,yy,hh=pos[e['target']]
        if x<xx:a,b=x+370,xx
        elif x>xx:a,b=x,xx+370
        else:a,b=x+370,xx+370
        sy=y+h/2;ty=yy+hh/2
        if e['source']==e['target']:path=f'M {a} {sy-15} C {a+65} {sy-70}, {b+65} {ty+70}, {b} {ty+15}'
        elif x==xx:mid=a+55;path=f'M {a} {sy} C {mid} {sy}, {mid} {ty}, {b} {ty}'
        else:mid=(a+b)/2;path=f'M {a} {sy} C {mid} {sy}, {mid} {ty}, {b} {ty}'
        title=escape(e.get('definition','Nguồn → view / materialized view'))
        out.append(f'<path d="{path}" fill="none" stroke="#64748b" stroke-width="1.8" marker-end="url(#arrow)"><title>{title}</title></path>')
    kinds={'r':'TABLE','p':'PARTITIONED TABLE','v':'VIEW','m':'MATERIALIZED VIEW','f':'FOREIGN TABLE'}
    for oid in ids:
        r=rel[oid];x,y,h=pos[oid];color='#2563eb' if oid==focus else '#0f766e'
        out.append(f'<rect x="{x}" y="{y}" width="370" height="{h}" rx="8" fill="white" stroke="{color}" stroke-width="2"/>')
        label=r['schema_name']+'.'+r['name']
        out.append(f'<text x="{x+12}" y="{y+25}" font-family="sans-serif" font-size="14" fill="{color}">{escape(label)}<title>{escape(label)}</title></text>')
        out.append(f'<text x="{x+12}" y="{y+46}" font-family="sans-serif" font-size="11" fill="#64748b">{kinds.get(r["kind"],r["kind"])}</text>')
        for j,line in enumerate(boxes[oid]):out.append(f'<text x="{x+12}" y="{y+69+18*j}" font-family="monospace" font-size="12" fill="#334155">{escape(line)}</text>')
    return ''.join(out)+'</svg>'

def arch_graph(data, mode):
    rel=data['relations']; ids={r['oid'] for r in rel}
    edges=data['deps'] if mode=='lineage' else [k for k in data['keys'] if k['kind']=='f']
    edges=[e for e in edges if e['source'] in ids and e['target'] in ids]
    labels={r['oid']:r['schema_name']+'.'+r['name'] for r in rel}
    default=next((r['oid'] for r in rel if r['schema_name']=='dw' and r['name']=='fact_sales'),None)
    options=[None]+list(labels)
    focus=st.selectbox('Đối tượng trung tâm',options,index=options.index(default),format_func=lambda x:labels.get(x,'Tất cả đối tượng'),key='arch_focus_'+mode)
    hops=st.slider('Số bước quan hệ quanh đối tượng',1,3,1,key='arch_hops_'+mode)
    selected=arch_scope(ids,edges,focus,hops)
    chosen=st.multiselect('Đối tượng hiển thị',sorted(ids,key=labels.get),default=sorted(selected,key=labels.get),format_func=labels.get,key=f'arch_nodes_{mode}_{focus}_{hops}')
    if not chosen:st.info('Chọn ít nhất một đối tượng.');return
    include_columns=st.checkbox('Hiện các cột và dấu PK/FK',value=(mode=='erd'),key='arch_columns_'+mode)
    graph_edges=[e for e in edges if e['source'] in chosen and e['target'] in chosen]
    if mode=='erd':
        st.caption('Mũi tên: bảng chứa FK → bảng được tham chiếu. PK/FK là ràng buộc đã khai báo; unique index xem ở tab Từ điển.')
        if not graph_edges:st.info('Không có khóa ngoại đã khai báo giữa các đối tượng đang chọn. Đây không phải lỗi; các quan hệ JOIN chưa khai báo FK sẽ không được tự thêm.')
    else:
        st.caption('Mũi tên: nguồn → view/materialized view sử dụng nguồn đó. Đây là phụ thuộc SQL, không phải thứ tự lịch chạy ETL hay quan hệ FK.')
        st.info('Chỉ gồm phụ thuộc relation của view/MV trong catalog. Không suy ra luồng Python, CSV hoặc SQL bên trong hàm dạng chuỗi như mart.rfm_at.')
    svg=arch_svg([r for r in rel if r['oid'] in chosen],data['columns'],graph_edges,focus,include_columns)
    zoom=st.slider('Thu phóng (%)',40,150,85,5,key='arch_zoom_'+mode)
    markup='<div style="overflow:auto;height:610px;border:1px solid #cbd5e1;border-radius:8px"><div style="zoom:'+str(zoom/100)+'">'+svg+'</div></div>'
    if hasattr(st,'iframe'):st.iframe(markup,height=630)
    else:
        from streamlit.components.v1 import html
        html(markup,height=630,scrolling=True)
    st.download_button('Tải sơ đồ SVG',svg,file_name='minimart_'+mode+'.svg',mime='image/svg+xml',key='arch_svg_'+mode)
    if graph_edges:
        st.dataframe(pd.DataFrame([{'Nguồn':labels[e['source']],'Đích':labels[e['target']],'Chi tiết':e.get('definition','Phụ thuộc view/MV')} for e in graph_edges]),hide_index=True,width='stretch')

def render_architecture():
    st.caption('Cấu trúc thực tế từ catalog PostgreSQL; chỉ đọc metadata, không quét hàng triệu dòng dữ liệu.')
    if st.button('Tải lại cấu trúc',key='arch_reload'):st.session_state.pop('arch_metadata',None)
    try:
        if 'arch_metadata' not in st.session_state:st.session_state['arch_metadata']=arch_load()
        data=st.session_state['arch_metadata']
    except psycopg.Error as exc:
        st.error('Không đọc được metadata. Kiểm tra kết nối hoặc quyền catalog của tài khoản dashboard. Không cần cấp quyền quản trị.');st.exception(exc);return
    st.caption(f"Database: {data['database']['db']} • Vai trò: {data['database']['role']} • Đọc lúc UTC: {data['read_at']}")
    if not data['relations']:st.info('Chưa có bảng/view trong schema người dùng.');return
    tabs=st.tabs(['ERD vật lý','Luồng nguồn → mart','Từ điển cấu trúc','Định nghĩa SQL'])
    with tabs[0]:arch_graph(data,'erd')
    with tabs[1]:arch_graph(data,'lineage')
    labels={r['oid']:r['schema_name']+'.'+r['name'] for r in data['relations']}
    with tabs[2]:
        oid=st.selectbox('Bảng hoặc view',list(labels),format_func=labels.get,key='arch_dictionary')
        cols=[a for a in data['columns'] if a['oid']==oid]
        st.dataframe(pd.DataFrame(cols).drop(columns=['oid'],errors='ignore'),hide_index=True,width='stretch')
        st.markdown('**Ràng buộc đã khai báo**')
        keys=[k for k in data['keys'] if k['source']==oid]
        if keys:st.dataframe(pd.DataFrame(keys)[['name','kind','definition','validated']],hide_index=True,width='stretch')
        else:st.caption('Chưa có PK/FK/UNIQUE/CHECK khai báo cho đối tượng này.')
        st.markdown('**Chỉ mục**')
        idx=[i for i in data['indexes'] if i['oid']==oid]
        if idx:st.dataframe(pd.DataFrame(idx).drop(columns=['oid']),hide_index=True,width='stretch')
        else:st.caption('Chưa có chỉ mục.')
        export=[dict(object=labels[a['oid']],**{k:v for k,v in a.items() if k!='oid'}) for a in data['columns'] if a['oid'] in labels]
        st.download_button('Tải từ điển toàn database',pd.DataFrame(export).to_csv(index=False).encode('utf-8-sig'),'minimart_dictionary.csv','text/csv')
    with tabs[3]:
        views=[r for r in data['relations'] if r['kind'] in ('v','m')]
        if not views:st.info('Chưa có view hoặc materialized view.')
        else:
            oid=st.selectbox('View / materialized view', [r['oid'] for r in views],format_func=labels.get,key='arch_sql')
            try:
                with connect() as conn:
                    conn.execute('SET TRANSACTION READ ONLY')
                    sql=conn.execute('SELECT pg_catalog.pg_get_viewdef(%s::oid,true) AS sql',(oid,)).fetchone()['sql']
                st.code(sql,language='sql')
                st.caption('Đây là câu SELECT định nghĩa đang lưu trong database, không phải toàn bộ migration CREATE/GRANT/INDEX. Đổi file SQL nhưng chưa áp dụng sẽ không đổi cấu trúc hiển thị.')
                st.download_button('Tải định nghĩa SELECT',sql,labels[oid]+'.sql','text/plain')
            except psycopg.Error:st.warning('Đối tượng đã đổi hoặc không đọc được định nghĩa; bấm Tải lại cấu trúc.')


def money(v):return f'{v or 0:,.2f}'
try:
    with connect() as c:release=c.execute('SELECT * FROM mart.release').fetchone()
except psycopg.Error:
    st.error('Chưa có dữ liệu công bố. Chạy start.ps1 hoặc pipeline trước.');st.stop()
if not release:st.info('Chưa có phiên bản dữ liệu.');st.stop()
version=release['version']
initial=st.query_params.get('page',PAGES[0]);initial=initial if initial in PAGES else PAGES[0]
st.sidebar.title('MINI-MART')
st.sidebar.caption('Bán hàng • Hộ khách hàng • Khuyến mãi')
page=st.sidebar.radio('Phân tích',PAGES,index=PAGES.index(initial))
if st.sidebar.button('Tải lại trang'):
    fetch.clear();st.rerun()
st.sidebar.caption(f"Phiên bản: {version[:10]}\n\nCông bố: {release['published_at']:%Y-%m-%d %H:%M %Z}")
st.sidebar.caption('Nguồn: kho dw → lớp src → mart. Phiên bản công bố sau đối soát.')
st.title(page)
st.caption('dunnhumby Complete Journey | Tiền tệ: USD | Phạm vi: tập hộ được quan sát')
st.caption('Giá trị mua dùng SALES_VALUE của nhà bán lẻ, không nhất thiết bằng tiền hộ thực trả.')

if page in [PAGES[0],PAGES[3]]:
    opts=query([('SELECT MIN(week_no) lo,MAX(week_no) hi FROM mart.sales_detail',()),('SELECT DISTINCT store_id FROM mart.sales_detail ORDER BY 1',()),('SELECT DISTINCT department FROM mart.sales_detail ORDER BY 1',())])
    lo,hi=opts[0][0]['lo'],opts[0][0]['hi']
    weeks=st.sidebar.slider('Khoảng tuần',lo,hi,(lo,hi)) if lo<hi else (lo,hi)
    stores=st.sidebar.multiselect('Cửa hàng — trống là tất cả',[r['store_id'] for r in opts[1]])
    depts=st.sidebar.multiselect('Ngành hàng — trống là tất cả',[r['department'] for r in opts[2]])
    where='week_no BETWEEN %s AND %s';params=list(weeks)
    if stores:where+=' AND store_id=ANY(%s)';params.append(stores)
    if depts:where+=' AND department=ANY(%s)';params.append(depts)
    product_text=st.sidebar.text_input('Mã sản phẩm (cách nhau bằng dấu phẩy)')
    if product_text.strip():
        try:products=[int(v.strip()) for v in product_text.split(',')]
        except ValueError:st.error('Mã sản phẩm phải là số nguyên, cách nhau bằng dấu phẩy.');st.stop()
        where+=' AND product_id=ANY(%s)';params.append(products)
    params=tuple(params)

if page==PAGES[0]:
    results=query([
      (f'SELECT SUM(sales_value) sales,COUNT(DISTINCT basket_id) baskets,COUNT(DISTINCT household_key) households FROM mart.sales_detail WHERE {where}',params),
      (f'SELECT week_no AS "Tuần",SUM(sales_value) AS "Doanh số",COUNT(DISTINCT basket_id) AS "Số giỏ",COUNT(DISTINCT household_key) AS "Số hộ" FROM mart.sales_detail WHERE {where} GROUP BY 1 ORDER BY 1',params),
      (f'SELECT department AS "Ngành hàng",SUM(sales_value) AS "Doanh số" FROM mart.sales_detail WHERE {where} GROUP BY 1 ORDER BY 2 DESC LIMIT 12',params),
      (f'SELECT store_id AS "Cửa hàng",SUM(sales_value) AS "Doanh số" FROM mart.sales_detail WHERE {where} GROUP BY 1 ORDER BY 2 DESC LIMIT 10',params)])
    k=results[0][0]
    if not k['baskets']:st.info('Không có giao dịch khớp bộ lọc.');st.stop()
    avg=k['sales']/k['baskets'] if k['baskets'] else 0
    cards([('Doanh số (USD)',money(k['sales'])),('Số giỏ',f"{k['baskets']:,}"),('Giá trị chọn/giỏ (USD)',money(avg)),('Hộ mua hàng',f"{k['households']:,}")])
    st.caption('Khi lọc ngành hàng, giá trị/giỏ chỉ gồm sản phẩm thuộc ngành đã chọn; số giỏ và hộ được đếm lại bằng DISTINCT.')
    a,b=st.columns(2)
    with a:st.subheader('Doanh số theo tuần');st.line_chart(frame(results[1]).set_index('Tuần')[['Doanh số']])
    with b:st.subheader('Số giỏ theo tuần');st.line_chart(frame(results[1]).set_index('Tuần')[['Số giỏ']])
    a,b=st.columns(2)
    with a:st.subheader('Ngành hàng đóng góp');st.bar_chart(frame(results[2]),x='Ngành hàng',y='Doanh số',horizontal=True)
    with b:st.subheader('Cửa hàng trong mẫu');st.bar_chart(frame(results[3]).astype({'Cửa hàng':str}),x='Cửa hàng',y='Doanh số',horizontal=True)
    with st.expander('Số liệu chi tiết và tải CSV'):
        df=table(results[1]);st.download_button('Tải số liệu theo tuần',df.to_csv(index=False).encode('utf-8-sig'),'sales_weekly.csv','text/csv')
    st.info('Tuần 1 chỉ gồm ngày 1–5. Số hộ quan sát thay đổi theo tuần; mức tăng doanh số chưa chứng minh tăng trưởng toàn chuỗi.')

elif page==PAGES[1]:
    bounds=query([('SELECT MIN(day) lo,MAX(day) hi FROM mart.basket',())])[0][0]
    asof=st.sidebar.number_input('Ngày chốt RFM',min_value=bounds['lo'],max_value=bounds['hi'],value=bounds['hi'])
    window=st.sidebar.number_input('Cửa sổ RFM (ngày)',min_value=1,max_value=bounds['hi']-bounds['lo']+1,value=min(365,bounds['hi']-bounds['lo']+1))
    r=query([('SELECT * FROM mart.rfm_at(%s,%s) ORDER BY monetary DESC',(asof,window))])[0]
    df=frame(r);cutoff=int(df['cutoff_day'].iloc[0])
    st.caption(f"RFM cố định tại ngày {cutoff}; cửa sổ ngày {max(bounds['lo'], cutoff-window+1)}–{cutoff} ({window} ngày yêu cầu). Không dùng ngày hệ thống.")
    st.caption('Quy tắc: minimart-kpi-v2 • RFM: rfm-fixed-v1. Ngưỡng đề xuất cho cửa sổ 365 ngày.')
    if int(window) != 365:
        st.warning(
            'Bạn đang dùng cửa sổ khác 365 ngày. Điểm F/M vẫn dùng ngưỡng cố định '
            'của cửa sổ 365 ngày; kết quả chỉ để khám phá, không so sánh trực tiếp '
            'phân nhóm giữa các cửa sổ. Ngưỡng không tự đổi theo số ngày.'
        )
    if cutoff - int(window) + 1 < bounds['lo']:
        st.info(
            'Cửa sổ yêu cầu bắt đầu trước ngày đầu của dữ liệu. '
            'Chỉ tính trên phần dữ liệu hiện có; không suy ra hộ không mua '
            'trong khoảng thời gian chưa được quan sát.'
        )
    segments=st.multiselect('Nhóm hộ',sorted(df.segment.unique()))
    if segments:df=df[df.segment.isin(segments)]
    income=st.multiselect('Nhóm thu nhập',sorted(df.income_desc.unique()))
    if income:df=df[df.income_desc.isin(income)]
    active=int((df.frequency>0).sum()); repeat=int((df.frequency>=2).sum())
    st.caption(f'Tỷ lệ mua lặp trong cửa sổ: {100*repeat/active:.2f}%' if active else 'Tỷ lệ mua lặp: không xác định vì không có hộ mua.')
    cards([('Số hộ',f'{len(df):,}'),('Có nhân khẩu học',f'{int(df.has_demographic.sum()):,}'),('Giá trị mua trong cửa sổ (USD)',money(df.monetary.sum())),('Có mua trong cửa sổ',f'{int((df.frequency>0).sum()):,}')])
    a,b=st.columns(2)
    with a:st.subheader('Phân nhóm RFM');st.bar_chart(df.groupby('segment').size().rename('Số hộ'),horizontal=True)
    with b:st.subheader('Chi tiêu theo nhóm');st.bar_chart(df.groupby('segment').monetary.sum().rename('USD'),horizontal=True)
    st.subheader('Thu nhập của các hộ có thông tin')
    demo=df[df.has_demographic]
    if len(demo):st.bar_chart(demo.groupby('income_desc').size().rename('Số hộ'),horizontal=True)
    st.caption('Hộ thiếu nhân khẩu học vẫn nằm trong tổng và RFM. Biểu đồ thu nhập chỉ mô tả nhóm có thông tin.')
    with st.expander('Ngưỡng RFM và chi tiết hộ'):
        st.write('R: ≤30/60/90/180/>180 ngày → 5/4/3/2/1. F: ≥52/26/12/4/<4 giỏ → 5/4/3/2/1. M: ≥2000/1000/500/100/<100 USD → 5/4/3/2/1. Không mua: điểm 0. Đây là quy tắc đề xuất rfm-fixed-v1 của bản tích hợp; chưa phải ngưỡng tối ưu được chứng minh bằng mô hình dự báo.')
        st.dataframe(df,width='stretch',hide_index=True);st.download_button('Tải RFM',df.to_csv(index=False).encode('utf-8-sig'),'rfm.csv')

elif page==PAGES[2]:
    r=query([('SELECT * FROM mart.campaign ORDER BY campaign',())])[0]
    selected=st.selectbox('Chiến dịch',[x['campaign'] for x in r]);k=next(x for x in r if x['campaign']==selected)
    cards([('Hộ nhận',f"{k['contacted_households']:,}"),('Hộ nhận có đổi trong kỳ',f"{k['responding_households']:,}"),('Tỷ lệ hưởng ứng',f"{k['response_pct']:.2f}%" if k['response_pct'] is not None else 'Không xác định'),('Lượt đổi hợp lệ',f"{k['eligible_redemption_events']:,}")])
    st.caption(f"{k['description']} • Ngày {k['start_day']}–{k['end_day']} | Tất cả bản ghi đổi trong nguồn: {k['all_redemption_events']:,}.")
    st.subheader('So sánh tỷ lệ hưởng ứng chiến dịch')
    chart=frame(r)[['campaign','response_pct']];chart['campaign']=chart.campaign.astype(str)
    st.bar_chart(chart,x='campaign',y='response_pct')
    phase=query([("SELECT phase,start_day,end_day,observed_days,contacted_households,sales_value,sales_per_household_day FROM mart.campaign_phase WHERE campaign=%s ORDER BY CASE phase WHEN 'Trước' THEN 1 WHEN 'Trong' THEN 2 ELSE 3 END",(selected,))])[0]
    st.subheader('Chi tiêu của hộ nhận trước trong và sau chiến dịch')
    st.bar_chart(frame(phase),x='phase',y='sales_per_household_day')
    st.caption('Đơn vị USD/hộ nhận/ngày quan sát. Trước và sau: tối đa 28 ngày; trong: thời gian chiến dịch. Cắt tại biên dữ liệu. Không kết luận quan hệ nhân quả.')
    with st.expander('Công thức và số liệu chi tiết'):
        st.write('Tử số: hộ thuộc danh sách nhận và có đổi coupon đúng chiến dịch trong START_DAY–END_DAY. Mẫu số: hộ nhận phân biệt. Không nối coupon–sản phẩm để phân bổ doanh số.');table(phase);table(r)

elif page==PAGES[3]:
    r=query([(f'SELECT product_id,MAX(commodity_desc) AS commodity,SUM(sales_value) AS sales_value,COUNT(DISTINCT basket_id) AS baskets FROM mart.sales_detail WHERE {where} GROUP BY product_id ORDER BY sales_value DESC LIMIT 15',params),
      (f'SELECT promotion_status,SUM(sales_value) AS sales_value,COUNT(*) AS product_store_weeks FROM mart.promotion_sales WHERE {where} GROUP BY 1 ORDER BY 2 DESC',params)])
    if not r[0]:st.info('Không có giao dịch khớp bộ lọc.');st.stop()
    cards([('Doanh số theo bộ lọc (USD)',money(sum(x['sales_value'] for x in r[1]))),('Tổ hợp sản phẩm cửa hàng tuần',f"{sum(x['product_store_weeks'] for x in r[1]):,}")])
    a,b=st.columns(2)
    with a:
        st.subheader('Top 15 sản phẩm theo doanh số');d=frame(r[0]);d['product_id']=d.product_id.astype(str);st.bar_chart(d,x='product_id',y='sales_value',horizontal=True)
    with b:st.subheader('Doanh số theo trạng thái quảng bá');st.bar_chart(frame(r[1]),x='promotion_status',y='sales_value',horizontal=True)
    st.info('Đã gộp quảng bá về sản phẩm–cửa hàng–tuần trước khi nối. Không có bản ghi không đồng nghĩa không quảng bá. So sánh mô tả, không đo tác động nhân quả.')
    with st.expander('Chi tiết sản phẩm và quảng bá'):table(r[0]);table(r[1])

elif page==PAGES[5]:
    render_architecture()

elif page==PAGES[4]:
    r=query([('SELECT * FROM audit.checks WHERE run_id=%s ORDER BY severity,check_name',(version,)),('SELECT filename,source_rows,loaded_rows,sha256 FROM audit.files WHERE run_id=%s ORDER BY filename',(version,)),('SELECT run_id,started_at,finished_at,status,message FROM audit.runs ORDER BY started_at DESC LIMIT 10',())])
    checks=r[0];cards([('Kiểm tra chặn lỗi',str(sum(x['severity']=='ERROR' for x in checks))),('Kiểm tra chặn đạt',str(sum(x['severity']=='ERROR' and x['passed'] for x in checks))),('Cảnh báo dữ liệu',str(sum(x['severity']=='WARN' and not x['passed'] for x in checks)))])
    st.subheader('Đối soát và cảnh báo');table(checks)
    st.subheader('Đối chiếu CSV với bảng nguồn');table(r[1])
    st.subheader('Lịch sử chạy và công bố');table(r[2])
    st.caption('Đây là audit của ETL tích hợp. Raw/staging và reject được lưu để truy vết. Refresh và công bố trong cùng transaction; nếu lỗi, giữ phiên bản đã công bố gần nhất.')


elif page==PAGES[6]:
    st.caption('Chỉ xem trạng thái; thao tác nạp chạy bằng PowerShell, không cấp quyền ghi cho dashboard.')
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        runs=conn.execute('SELECT * FROM audit.runs ORDER BY started_at DESC LIMIT 30').fetchall()
        watermarks=conn.execute('SELECT * FROM audit.watermark').fetchall()
    st.subheader('Lịch sử ETL');table(runs)
    if runs:
        rid=st.selectbox('Lần chạy cần xem',[r['run_id'] for r in runs])
        with connect() as conn:
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            steps=conn.execute('SELECT step_name,status,started_at,finished_at,message FROM audit.steps WHERE run_id=%s ORDER BY step_id',(rid,)).fetchall()
            files=conn.execute('SELECT f.filename,b.* FROM audit.batch_file b JOIN audit.source_file f USING(file_id) WHERE run_id=%s',(rid,)).fetchall()
            rejects=conn.execute('SELECT r.source_name,r.source_row_no,r.rule_code,r.raw_payload FROM audit.rejects r JOIN audit.batch_file b USING(file_id) WHERE b.run_id=%s ORDER BY r.source_name,r.source_row_no LIMIT 100',(rid,)).fetchall()
        st.subheader('Các bước xử lý');table(steps)
        st.subheader('Đối soát file');table(files)
        st.caption('read = accepted + rejected + skipped. Skipped là dòng hợp lệ đã công bố trước đó; không nạp thêm.')
        st.subheader('Dòng bị loại — tối đa 100 dòng');table(rejects)
    st.subheader('Watermark đã commit');table(watermarks)
    st.info('Watermark là mốc ngày lớn nhất đã nạp, không dùng để bỏ qua dữ liệu đến muộn. File mới được kiểm tra bằng checksum và dòng nguồn.')
    from pathlib import Path
    import json
    report=Path(os.getenv('EVIDENCE_DIR','/app/evidence'))/'tests/integration.json'
    if report.exists():
        data=json.loads(report.read_text())
        st.subheader('Kiểm thử tích hợp trên fixture riêng')
        st.caption(data.get('scope',''))
        table(data.get('tests',[]))
    st.code('docker compose -p minimart_demo run --rm tools python -u scripts/etl.py',language='powershell')


# Hiển thị kết quả BM01 đã lưu
import json
from pathlib import Path


# Các kết quả CSV được chạy độc lập; không suy ra trạng thái ETL từ chúng.
if page == PAGES[4]:
    from datetime import datetime, timezone

    st.divider()
    st.subheader("Khảo sát CSV nguồn — kết quả chạy lại")
    st.caption(
        "Script khảo sát do Lam bàn giao; hiển thị file trong local_check. "
        "Đây là bằng chứng khảo sát CSV đã lưu, không phải kiểm tra trực tiếp "
        "PostgreSQL và không tự xác nhận phiên bản mart hiện tại. "
        "Bấm Tải lại trang sau khi chạy lại script."
    )
    profiling_root = Path(os.getenv("EVIDENCE_DIR", "/app/evidence")) / "profiling/local_check"

    def show_profile(relative_path, required_columns, title, note):
        st.markdown(f"**{title}**")
        path = profiling_root / relative_path
        try:
            data = pd.read_csv(path, encoding="utf-8-sig")
            missing = set(required_columns) - set(data.columns)
            if missing:
                st.warning("File thiếu cột: " + ", ".join(sorted(missing)))
                return
            if data.empty:
                st.info("File có tiêu đề nhưng chưa có dòng kết quả.")
                return
            st.dataframe(data, hide_index=True, width="stretch")
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            st.caption(
                f"File: {relative_path} | Sửa lần cuối (UTC): {modified:%Y-%m-%d %H:%M:%S}. "
                "Đây là thời gian sửa file, không nhất thiết là thời điểm thực nghiệm."
            )
            st.caption(note)
            st.download_button(
                "Tải CSV kết quả", data.to_csv(index=False).encode("utf-8-sig"),
                file_name=path.name, mime="text/csv", key="profile_" + path.stem,
            )
        except FileNotFoundError:
            st.info(f"Chưa có file: {relative_path}. Chạy script tương ứng để tạo kết quả.")
        except (OSError, UnicodeError, ValueError, pd.errors.ParserError) as exc:
            st.warning(f"Không đọc được {relative_path}: {exc}")

    key_tab, coupon_tab, campaign_tab = st.tabs([
        "Khóa năm bảng", "Coupon và sản phẩm", "Chiến dịch và đổi coupon"
    ])
    with key_tab:
        show_profile(
            "06_Business_Key_Profiling/business_key_profiling_summary.csv",
            ["Table", "Key_Columns", "Total_Rows", "Rows_With_Missing_Key",
             "Duplicate_Groups", "Is_Unique"],
            "Kiểm tra khóa nghiệp vụ",
            "Is_Unique phản ánh dữ liệu CSV trong lần khảo sát; "
            "không xác nhận PK/FK đã được khai báo trong PostgreSQL.",
        )
    with coupon_tab:
        show_profile(
            "10_Cross_Table_Profiling/coupon_product_summary.csv",
            ["Metric", "Value"], "Quan hệ coupon–sản phẩm",
            "Repeated keys là số nhóm khóa lặp. Số dòng trùng dư bằng tổng dòng "
            "coupon trừ số bộ ba chiến dịch–coupon–sản phẩm phân biệt. "
            "Không nối danh mục sản phẩm đủ điều kiện rồi đếm bản ghi đổi coupon.",
        )
    with campaign_tab:
        show_profile(
            "10_Cross_Table_Profiling/campaign_redemption_summary.csv",
            ["Metric", "Value"], "Kiểm tra hộ nhận và thời gian đổi coupon",
            "Số bản ghi đổi coupon không phải số hộ hưởng ứng. "
            "Tỷ lệ hưởng ứng cần đếm hộ phân biệt trong từng chiến dịch. "
            "Valid chỉ áp dụng cho các điều kiện script đã kiểm tra.",
        )

st.divider()

with st.expander("Kết quả thực nghiệm BM01", expanded=False):
    st.caption(
        "So sánh truy vấn trực tiếp với materialized view. "
        "Đây là kết quả từ file bằng chứng, "
        "không phải thời gian tải dashboard."
    )

    bm01_path = Path(os.getenv("EVIDENCE_DIR", "/app/evidence")) / "bm01/summary.json"

    if not bm01_path.exists():
        st.info("Chưa tìm thấy evidence/bm01/summary.json.")
    else:
        try:
            bm01 = json.loads(
                bm01_path.read_text(encoding="utf-8-sig")
            )

            if bm01.get("release") != version:
                st.warning("BM01 thuộc phiên bản công bố khác. Chạy lại benchmark trước khi kết luận cho phiên bản hiện tại.")
            st.caption("Nguồn đo: " + bm01.get("source_layer", "Chưa ghi nhận"))
            direct = bm01["direct"]
            materialized = bm01["materialized"]

            direct_ms = float(direct["median_ms"])
            mv_ms = float(materialized["median_ms"])

            col1, col2, col3 = st.columns(3)
            col1.metric(
                "Truy vấn trực tiếp — median",
                f"{direct_ms:,.3f} ms",
            )
            col2.metric(
                "Materialized view — median",
                f"{mv_ms:,.3f} ms",
            )
            col3.metric(
                "Tỷ số thời gian median",
                f"{direct_ms / mv_ms:,.2f} lần"
                if mv_ms > 0 else "Không xác định",
            )

            comparison = pd.DataFrame({
                "Chỉ số": ["Median", "P95", "Nhỏ nhất", "Lớn nhất"],
                "Trực tiếp (ms)": [
                    direct.get(key)
                    for key in ["median_ms", "p95_ms", "min_ms", "max_ms"]
                ],
                "Materialized view (ms)": [
                    materialized.get(key)
                    for key in ["median_ms", "p95_ms", "min_ms", "max_ms"]
                ],
            })

            st.dataframe(comparison, hide_index=True)

            st.caption(
                "Tỷ số trên chỉ áp dụng cho truy vấn BM01; "
                "không đại diện cho tốc độ toàn bộ dashboard. "
                "Môi trường và thời điểm đo cần đối chiếu "
                "trong bằng chứng bên dưới."
            )

            st.write("Bằng chứng đầy đủ")
            st.json(bm01)

        except (OSError, ValueError, KeyError, TypeError) as exc:
            st.error(f"Không đọc được kết quả BM01: {exc}")

with st.expander("BM02 / BM03 — phân vùng và chỉ mục", expanded=False):
    design_path=Path(os.getenv('EVIDENCE_DIR','/app/evidence'))/'bm02_bm03/summary.json'
    if design_path.exists():
        try:
            design=json.loads(design_path.read_text())
            st.caption(design.get('source',''))
            st.caption('Thí nghiệm trên dữ liệu tổng hợp, không phải tốc độ của bảng fact/dashboard thực tế.')
            st.dataframe(pd.DataFrame(design['variants']).T,width='stretch')
            st.json(design)
        except (ValueError,KeyError,OSError) as exc:st.warning(str(exc))
    else:st.info('Chạy scripts/benchmark_design.py để tạo bằng chứng trên máy đang demo.')
