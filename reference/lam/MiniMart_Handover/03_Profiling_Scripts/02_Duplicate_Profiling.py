
import pandas as pd
import sqlite3
from pathlib import Path

ROOT = Path.home() / "Documents" / "MiniMart_DataWarehouse_BTL"
DATA_DIR = ROOT / "01_Source_Data" / "Extracted_CSV"
OUTPUT_DIR = ROOT / "02_Data_Profiling" / "04_Duplicates"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

DB_FILE = OUTPUT_DIR / "duplicate_analysis_temp.sqlite"
OUTPUT_FILE = OUTPUT_DIR / "exact_duplicate_profile.csv"

CHUNK_SIZE = 100_000

results = []

conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS seen (
        file_name TEXT NOT NULL,
        fingerprint TEXT NOT NULL,
        PRIMARY KEY (file_name, fingerprint)
    ) WITHOUT ROWID
""")
conn.commit()

try:
    for file in sorted(DATA_DIR.glob("*.csv")):
        print(f"\nProcessing: {file.name}")

        cursor.execute(
            "DELETE FROM seen WHERE file_name = ?",
            (file.name,)
        )
        conn.commit()

        total_rows = 0
        duplicate_rows = 0

        for chunk in pd.read_csv(
            file,
            dtype=str,
            keep_default_na=False,
            chunksize=CHUNK_SIZE
        ):
            row_hashes = pd.util.hash_pandas_object(
                chunk,
                index=False
            )

            fingerprints = [
                (file.name, f"{value:016x}")
                for value in row_hashes
            ]

            before = conn.total_changes

            cursor.executemany(
                """
                INSERT OR IGNORE INTO seen
                (file_name, fingerprint)
                VALUES (?, ?)
                """,
                fingerprints
            )

            conn.commit()

            inserted = conn.total_changes - before
            chunk_duplicates = len(chunk) - inserted

            total_rows += len(chunk)
            duplicate_rows += chunk_duplicates

            print(
                f"  Processed: {total_rows:,} rows | "
                f"Duplicates: {duplicate_rows:,}"
            )

        unique_rows = total_rows - duplicate_rows
        duplicate_rate = (
            duplicate_rows / total_rows * 100
            if total_rows else 0
        )

        results.append({
            "File_Name": file.name,
            "Total_Rows": total_rows,
            "Unique_Row_Fingerprints": unique_rows,
            "Exact_Duplicate_Rows": duplicate_rows,
            "Duplicate_Rate_Percent": round(
                duplicate_rate, 4
            )
        })

        print(f"Completed: {file.name}")

    result_df = pd.DataFrame(results)
    result_df.to_csv(
        OUTPUT_FILE,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n========== SUMMARY ==========")
    print(result_df.to_string(index=False))
    print("\nOutput:", OUTPUT_FILE)

finally:
    conn.close()

    if DB_FILE.exists():
        DB_FILE.unlink()
