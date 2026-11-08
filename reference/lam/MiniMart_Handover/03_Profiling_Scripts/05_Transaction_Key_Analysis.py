import pandas as pd
import sqlite3
from pathlib import Path

ROOT = Path.home() / "Documents" / "MiniMart_DataWarehouse_BTL"

SOURCE = ROOT / "01_Source_Data" / "Extracted_CSV" / "transaction_data.csv"
OUTPUT_DIR = ROOT / "02_Data_Profiling" / "04_Duplicates"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DB_FILE = OUTPUT_DIR / "transaction_key_analysis_temp.sqlite"
OUTPUT_FILE = OUTPUT_DIR / "transaction_key_analysis.csv"

CHUNK_SIZE = 100_000

KEYS = [
    ["household_key"],
    ["BASKET_ID"],
    ["PRODUCT_ID"],
    ["household_key", "BASKET_ID"],
    ["household_key", "PRODUCT_ID"],
    ["BASKET_ID", "PRODUCT_ID"],
    ["household_key", "BASKET_ID", "PRODUCT_ID"]
]

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS key_counts (
        key_name TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        occurrences INTEGER NOT NULL,
        PRIMARY KEY (key_name, fingerprint)
    ) WITHOUT ROWID
""")
conn.commit()

total_rows = 0

try:
    for chunk in pd.read_csv(
        SOURCE,
        dtype=str,
        keep_default_na=False,
        chunksize=CHUNK_SIZE
    ):
        total_rows += len(chunk)

        for key in KEYS:
            key_name = " + ".join(key)

            hashes = pd.util.hash_pandas_object(
                chunk[key],
                index=False
            )

            counts = hashes.value_counts(sort=False)

            records = [
                (key_name, f"{fingerprint:016x}", int(count))
                for fingerprint, count in counts.items()
            ]

            cursor.executemany("""
                INSERT INTO key_counts
                    (key_name, fingerprint, occurrences)
                VALUES (?, ?, ?)
                ON CONFLICT(key_name, fingerprint)
                DO UPDATE SET
                    occurrences = occurrences + excluded.occurrences
            """, records)

        conn.commit()

        print(f"Processed: {total_rows:,} rows")

    results = []

    for key in KEYS:
        key_name = " + ".join(key)

        stats = cursor.execute("""
            SELECT
                COUNT(*),
                COALESCE(SUM(occurrences - 1), 0),
                COALESCE(SUM(
                    CASE WHEN occurrences > 1 THEN 1 ELSE 0 END
                ), 0),
                COALESCE(MAX(occurrences), 0)
            FROM key_counts
            WHERE key_name = ?
        """, (key_name,)).fetchone()

        unique_count, duplicate_rows, duplicate_groups, max_occ = stats

        results.append({
            "Key_Columns": key_name,
            "Unique_Combinations": unique_count,
            "Duplicate_Excess_Rows": duplicate_rows,
            "Duplicate_Groups": duplicate_groups,
            "Max_Occurrences": max_occ,
            "Is_Unique": duplicate_rows == 0
        })

    result_df = pd.DataFrame(results)

    result_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n========== SUMMARY ==========")
    print("Total rows:", total_rows)
    print(result_df.to_string(index=False))
    print("\nOutput:", OUTPUT_FILE)

finally:
    conn.close()

    if DB_FILE.exists():
        DB_FILE.unlink()