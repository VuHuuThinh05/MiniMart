import os
from pathlib import Path
import psycopg
ROOT=Path(__file__).resolve().parents[1]
def connect(prepare_threshold=None,**kwargs):
    return psycopg.connect(host=os.getenv('DB_HOST','127.0.0.1'),port=os.getenv('DB_PORT','55433'),dbname=os.getenv('DB_NAME','minimart'),user=os.getenv('DB_USER','minimart'),password=os.getenv('DB_PASSWORD','minimart_local_2026'),prepare_threshold=None,**kwargs)

EVIDENCE=Path(os.getenv("EVIDENCE_DIR",str(ROOT/"evidence")))
