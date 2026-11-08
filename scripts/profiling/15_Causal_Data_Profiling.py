
import argparse
import sqlite3
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--transaction", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_file = Path(args.input)
    transaction_file = Path(args.transaction)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = output_dir / "causal_profile_temp.sqlite"
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=FILE")

    conn.execute("""
        CREATE TABLE causal_detail (
            PRODUCT_ID TEXT NOT NULL,
            STORE_ID TEXT NOT NULL,
            WEEK_NO TEXT NOT NULL,
            DISPLAY TEXT NOT NULL,
            MAILER TEXT NOT NULL,
            row_count INTEGER NOT NULL DEFAULT 1,
            PRIMARY KEY (
                PRODUCT_ID, STORE_ID, WEEK_NO, DISPLAY, MAILER
            )
        )
    """)

    conn.execute("""
        CREATE TABLE transaction_keys (
            PRODUCT_ID TEXT NOT NULL,
            STORE_ID TEXT NOT NULL,
            WEEK_NO TEXT NOT NULL,
            PRIMARY KEY (PRODUCT_ID, STORE_ID, WEEK_NO)
        )
    """)

    required_causal = {
        "PRODUCT_ID", "STORE_ID", "WEEK_NO", "DISPLAY", "MAILER"
    }
    required_transaction = {"PRODUCT_ID", "STORE_ID", "WEEK_NO"}

    # Profile causal_data in chunks
    causal_rows = 0
    causal_missing_key_rows = 0
    causal_missing_detail_rows = 0

    for chunk in pd.read_csv(
        input_file, dtype=str, keep_default_na=False, chunksize=300000
    ):
        chunk.columns = chunk.columns.str.strip().str.upper()

        missing_columns = required_causal - set(chunk.columns)
        if missing_columns:
            raise ValueError(
                f"causal_data thiếu cột: {sorted(missing_columns)}"
            )

        keys = ["PRODUCT_ID", "STORE_ID", "WEEK_NO"]
        details = keys + ["DISPLAY", "MAILER"]

        for col in details:
            chunk[col] = chunk[col].astype(str).str.strip()

        causal_rows += len(chunk)
        causal_missing_key_rows += (
            chunk[keys].eq("").any(axis=1).sum()
        )
        causal_missing_detail_rows += (
            chunk[["DISPLAY", "MAILER"]].eq("").any(axis=1).sum()
        )

        records = chunk[details].itertuples(index=False, name=None)

        conn.executemany("""
            INSERT INTO causal_detail (
                PRODUCT_ID, STORE_ID, WEEK_NO, DISPLAY, MAILER
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (
                PRODUCT_ID, STORE_ID, WEEK_NO, DISPLAY, MAILER
            )
            DO UPDATE SET row_count = row_count + 1
        """, records)

        conn.commit()
        print(f"Processed causal_data: {causal_rows:,} rows")

    # Build distinct causal business keys
    conn.execute("""
        CREATE TABLE causal_business_keys AS
        SELECT PRODUCT_ID, STORE_ID, WEEK_NO,
               SUM(row_count) AS row_count,
               COUNT(*) AS display_mailer_variants
        FROM causal_detail
        GROUP BY PRODUCT_ID, STORE_ID, WEEK_NO
    """)
    conn.execute("""
        CREATE UNIQUE INDEX idx_causal_business_key
        ON causal_business_keys(PRODUCT_ID, STORE_ID, WEEK_NO)
    """)
    conn.commit()

    # Profile transaction keys in chunks
    transaction_rows = 0
    transaction_missing_key_rows = 0

    for chunk in pd.read_csv(
        transaction_file, dtype=str, keep_default_na=False, chunksize=300000
    ):
        chunk.columns = chunk.columns.str.strip().str.upper()

        missing_columns = required_transaction - set(chunk.columns)
        if missing_columns:
            raise ValueError(
                f"transaction_data thiếu cột: {sorted(missing_columns)}"
            )

        keys = ["PRODUCT_ID", "STORE_ID", "WEEK_NO"]
        for col in keys:
            chunk[col] = chunk[col].astype(str).str.strip()

        transaction_rows += len(chunk)
        transaction_missing_key_rows += (
            chunk[keys].eq("").any(axis=1).sum()
        )

        valid = chunk.loc[~chunk[keys].eq("").any(axis=1), keys]
        conn.executemany("""
            INSERT OR IGNORE INTO transaction_keys
            (PRODUCT_ID, STORE_ID, WEEK_NO)
            VALUES (?, ?, ?)
        """, valid.itertuples(index=False, name=None))

        conn.commit()
        print(f"Processed transaction_data: {transaction_rows:,} rows")

    # Summary queries
    causal_unique_keys = conn.execute("""
        SELECT COUNT(*) FROM causal_business_keys
    """).fetchone()[0]

    causal_duplicate_groups = conn.execute("""
        SELECT COUNT(*) FROM causal_business_keys
        WHERE row_count > 1
    """).fetchone()[0]

    causal_duplicate_excess = conn.execute("""
        SELECT COALESCE(SUM(row_count - 1), 0)
        FROM causal_business_keys
        WHERE row_count > 1
    """).fetchone()[0]

    causal_max_key_count = conn.execute("""
        SELECT COALESCE(MAX(row_count), 0)
        FROM causal_business_keys
    """).fetchone()[0]

    multiple_display_mailer = conn.execute("""
        SELECT COUNT(*) FROM causal_business_keys
        WHERE display_mailer_variants > 1
    """).fetchone()[0]

    full_row_groups = conn.execute("""
        SELECT COUNT(*) FROM causal_detail
        WHERE row_count > 1
    """).fetchone()[0]

    full_row_excess = conn.execute("""
        SELECT COALESCE(SUM(row_count - 1), 0)
        FROM causal_detail
        WHERE row_count > 1
    """).fetchone()[0]

    transaction_unique_keys = conn.execute("""
        SELECT COUNT(*) FROM transaction_keys
    """).fetchone()[0]

    matched_keys = conn.execute("""
        SELECT COUNT(*)
        FROM transaction_keys t
        INNER JOIN causal_business_keys c
        USING (PRODUCT_ID, STORE_ID, WEEK_NO)
    """).fetchone()[0]

    unmatched_transaction_keys = transaction_unique_keys - matched_keys

    causal_without_transaction = conn.execute("""
        SELECT COUNT(*)
        FROM causal_business_keys c
        LEFT JOIN transaction_keys t
        USING (PRODUCT_ID, STORE_ID, WEEK_NO)
        WHERE t.PRODUCT_ID IS NULL
    """).fetchone()[0]

    summary = pd.DataFrame([
        ("Total causal_data rows", causal_rows),
        ("Causal rows with missing business key", causal_missing_key_rows),
        ("Causal rows with missing DISPLAY or MAILER", causal_missing_detail_rows),
        ("Distinct PRODUCT-STORE-WEEK keys", causal_unique_keys),
        ("Business key groups with repeated rows", causal_duplicate_groups),
        ("Excess rows within repeated business keys", causal_duplicate_excess),
        ("Maximum rows per business key", causal_max_key_count),
        ("Keys with multiple DISPLAY/MAILER combinations", multiple_display_mailer),
        ("Repeated full-row groups", full_row_groups),
        ("Excess repeated full rows", full_row_excess),
        ("Transaction rows", transaction_rows),
        ("Transaction rows with missing business key", transaction_missing_key_rows),
        ("Distinct transaction PRODUCT-STORE-WEEK keys", transaction_unique_keys),
        ("Transaction keys matched to causal_data", matched_keys),
        ("Transaction keys unmatched to causal_data", unmatched_transaction_keys),
        ("Causal keys without transaction", causal_without_transaction),
    ], columns=["Metric", "Value"])

    summary.to_csv(
        output_dir / "causal_data_summary.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("\n========== CAUSAL DATA SUMMARY ==========")
    print(summary.to_string(index=False))
    print(f"\nOutput directory: {output_dir}")

    conn.close()
    db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
