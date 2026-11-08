import os
from decimal import Decimal
import pandas as pd
import streamlit as st

st.set_page_config(page_title='MiniMart Analytics (Demo Cloud)', page_icon='🛒', layout='wide')
st.markdown('''<style>.block-container{padding-top:2rem;padding-bottom:2rem}h1{font-size:2rem!important}[data-testid="stMetric"]{background:#f1f5f9;border-radius:10px;padding:16px}div[data-testid="stSidebar"]{background:#eef2f6}</style>''', unsafe_allow_html=True)

PAGES = ['Bán hàng', 'Hộ khách hàng', 'Chiến dịch và coupon', 'Sản phẩm và quảng bá', 'Chất lượng dữ liệu', 'Kiến trúc & ERD', 'Vận hành ETL']

# Kiểm tra xem có thể kết nối PostgreSQL không (Local vs Cloud)
USE_MOCK_DATA = False
try:
    import psycopg
    from psycopg.rows import dict_row
    
    conn_check = psycopg.connect(
        host=os.getenv('DB_HOST', 'postgres'),
        port=os.getenv('DB_PORT', '5432'),
        dbname=os.getenv('DB_NAME', 'minimart'),
        user=os.getenv('DB_USER', 'minimart'),
        password=os.getenv('DB_PASSWORD', 'minimart_local_2026'),
        row_factory=dict_row,
        prepare_threshold=None,
        connect_timeout=3
    )
    conn_check.close()
except Exception:
    USE_MOCK_DATA = True

def connect():
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(
        host=os.getenv('DB_HOST', 'postgres'),
        port=os.getenv('DB_PORT', '5432'),
        dbname=os.getenv('DB_NAME', 'minimart'),
        user=os.getenv('DB_USER', 'minimart'),
        password=os.getenv('DB_PASSWORD', 'minimart_local_2026'),
        row_factory=dict_row,
        prepare_threshold=None
    )

def cards(values):
    for c, (label, value) in zip(st.columns(len(values)), values):
        c.metric(label, value)

# --- CHẾ ĐỘ DEMO ONLINE TRÊN STREAMLIT CLOUD ---
if USE_MOCK_DATA:
    st.info('💡 Đang hiển thị ứng dụng ở chế độ Demo Online (Dữ liệu thử nghiệm giao diện do không kết nối PostgreSQL Local).')
    st.sidebar.title('MINI-MART (DEMO)')
    page = st.sidebar.radio('Phân tích', PAGES)
    st.title(f"🛒 {page} - Demo Giao diện")

    if page == PAGES[0]: # Bán hàng
        cards([('Doanh số (USD)', '$124,500.00'), ('Số giỏ', '1,420'), ('Giá trị chọn/giỏ', '$87.67'), ('Hộ mua hàng', '350')])
        
        df_weekly = pd.DataFrame({
            'Tuần': range(1, 11),
            'Doanh số': [12000, 15000, 9000, 18000, 21000, 16000, 14000, 19000, 22000, 25000],
            'Số giỏ': [140, 152, 138, 160, 171, 155, 148, 162, 175, 180]
        })
        a, b = st.columns(2)
        with a:
            st.subheader('Doanh số theo tuần')
            st.line_chart(df_weekly.set_index('Tuần')[['Doanh số']])
        with b:
            st.subheader('Số giỏ theo tuần')
            st.line_chart(df_weekly.set_index('Tuần')[['Số giỏ']])

        df_dept = pd.DataFrame({
            'Ngành hàng': ['GROCERY', 'DRUG GM', 'PRODUCE', 'MEAT', 'DELI'],
            'Doanh số': [45000, 32000, 21000, 18000, 8500]
        })
        st.subheader('Ngành hàng đóng góp')
        st.bar_chart(df_dept, x='Ngành hàng', y='Doanh số', horizontal=True)

    else:
        st.write("Giao diện Demo cho phần này đã sẵn sàng. Khi chạy ở máy Local với Docker, hệ thống sẽ tự động truy vấn CSDL PostgreSQL thực tế.")
        st.dataframe(pd.DataFrame({
            "Mẫu dữ liệu": ["Metric A", "Metric B", "Metric C"],
            "Giá trị": [100, 250, 400]
        }))
    st.stop()

# --- NẾU CHẠY LOCAL (KẾT NỐI POSTGRESQL THẬT) ---
class ReleaseChanged(Exception): pass

@st.cache_data(show_spinner=False, max_entries=96)
def fetch(version, statements):
    with connect() as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        r = c.execute('SELECT version FROM mart.release').fetchone()
        if not r or r['version'] != version: raise ReleaseChanged()
        return [c.execute(q, params).fetchall() for q, params in statements]

def query(statements):
    try: return fetch(version, tuple(statements))
    except ReleaseChanged:
        st.warning('Vừa có phiên bản mới. Bấm Tải lại trang để đồng bộ.'); st.stop()
    except Exception as e:
        st.error('Truy vấn thất bại.'); st.exception(e); st.stop()

def frame(rows):
    df = pd.DataFrame(rows)
    for col in df:
        if any(isinstance(v, Decimal) for v in df[col].head(20)):
            df[col] = df[col].map(lambda v: float(v) if isinstance(v, Decimal) else v)
    return df

def table(rows):
    df = frame(rows); st.dataframe(df, hide_index=True, width='stretch'); return df

try:
    with connect() as c: release = c.execute('SELECT * FROM mart.release').fetchone()
except Exception:
    st.error('Chưa có dữ liệu công bố. Chạy start.ps1 hoặc pipeline trước.'); st.stop()

if not release: st.info('Chưa có phiên bản dữ liệu.'); st.stop()
version = release['version']
initial = st.query_params.get('page', PAGES[0]); initial = initial if initial in PAGES else PAGES[0]

st.sidebar.title('MINI-MART')
st.sidebar.caption('Bán hàng • Hộ khách hàng • Khuyến mãi')
page = st.sidebar.radio('Phân tích', PAGES, index=PAGES.index(initial))
st.sidebar.caption(f"Phiên bản: {version[:10]}")
st.title(page)