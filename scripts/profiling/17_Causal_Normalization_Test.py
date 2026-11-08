
import argparse
import sqlite3
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--causal", required=True)
    parser.add_argument("--transaction", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    db_path = output / "causal_normalization_temp.sqlite"
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=FILE")

    conn.execute("""
        CREATE TABLE causal_flags (
            PRODUCT_ID TEXT,
            STORE_ID TEXT,
            WEEK_NO TEXT,
            HAS_DISPLAY INTEGER,
            HAS_MAILER INTEGER,
            PRIMARY KEY (PRODUCT_ID, STORE_ID, WEEK_NO)
        )
    """)

    conn.execute("""
        CREATE TABLE transaction_keys (
            PRODUCT_ID TEXT,
            STORE_ID TEXT,
            WEEK_NO TEXT,
            PRIMARY KEY (PRODUCT_ID, STORE_ID, WEEK_NO)
        )
    """)

    # 1. Chuẩn hóa causal_data theo PRODUCT-STORE-WEEK
    causal_rows = 0

    for chunk in pd.read_csv(
        args.causal,
        dtype=str,
        keep_default_na=False,
        chunksize=300000
    ):
        chunk.columns = chunk.columns.str.strip().str.upper()

        required = {
            "PRODUCT_ID", "STORE_ID", "WEEK_NO", "DISPLAY", "MAILER"
        }
        missing = required - set(chunk.columns)

        if missing:
            raise ValueError(f"Missing causal columns: {sorted(missing)}")

        keys = ["PRODUCT_ID", "STORE_ID", "WEEK_NO"]

        for col in list(required):
            chunk[col] = chunk[col].astype(str).str.strip()

        # 1 = có ít nhất một mã khác 0
        chunk["HAS_DISPLAY"] = (
            chunk["DISPLAY"].ne("0") & chunk["DISPLAY"].ne("")
        ).astype(int)

        chunk["HAS_MAILER"] = (
            chunk["MAILER"].ne("0") & chunk["MAILER"].ne("")
        ).astype(int)

        records = chunk[
            keys + ["HAS_DISPLAY", "HAS_MAILER"]
        ].itertuples(index=False, name=None)

        conn.executemany("""
            INSERT INTO causal_flags (
                PRODUCT_ID, STORE_ID, WEEK_NO,
                HAS_DISPLAY, HAS_MAILER
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (PRODUCT_ID, STORE_ID, WEEK_NO)
            DO UPDATE SET
                HAS_DISPLAY = MAX(
                    causal_flags.HAS_DISPLAY,
                    excluded.HAS_DISPLAY
                ),
                HAS_MAILER = MAX(
                    causal_flags.HAS_MAILER,
                    excluded.HAS_MAILER
                )
        """, records)

        causal_rows += len(chunk)
        conn.commit()
        print(f"Processed causal_data: {causal_rows:,}")

    # 2. Lấy các khóa giao dịch phân biệt
    transaction_rows = 0

    for chunk in pd.read_csv(
        args.transaction,
        dtype=str,
        keep_default_na=False,
        chunksize=300000
    ):
        chunk.columns = chunk.columns.str.strip().str.upper()

        keys = ["PRODUCT_ID", "STORE_ID", "WEEK_NO"]
        missing = set(keys) - set(chunk.columns)

        if missing:
            raise ValueError(
                f"Missing transaction columns: {sorted(missing)}"
            )

        for col in keys:
            chunk[col] = chunk[col].astype(str).str.strip()

        valid = chunk.loc[
            ~chunk[keys].eq("").any(axis=1), keys
        ]

        conn.executemany("""
            INSERT OR IGNORE INTO transaction_keys
            (PRODUCT_ID, STORE_ID, WEEK_NO)
            VALUES (?, ?, ?)
        """, valid.itertuples(index=False, name=None))

        transaction_rows += len(chunk)
        conn.commit()
        print(f"Processed transaction_data: {transaction_rows:,}")

    # 3. Thống kê trạng thái khuyến mãi
    promotion_summary = pd.read_sql_query("""
        SELECT
            HAS_DISPLAY,
            HAS_MAILER,
            COUNT(*) AS DISTINCT_KEYS
        FROM causal_flags
        GROUP BY HAS_DISPLAY, HAS_MAILER
        ORDER BY HAS_DISPLAY, HAS_MAILER
    """, conn)

    # 4. Đối chiếu với khóa giao dịch
    coverage = pd.read_sql_query("""
        SELECT
            CASE
                WHEN c.PRODUCT_ID IS NOT NULL THEN 'Matched'
                ELSE 'Unmatched'
            END AS MATCH_STATUS,
            COUNT(*) AS TRANSACTION_KEYS,
            SUM(CASE WHEN c.HAS_DISPLAY = 1 THEN 1 ELSE 0 END)
                AS KEYS_WITH_DISPLAY,
            SUM(CASE WHEN c.HAS_MAILER = 1 THEN 1 ELSE 0 END)
                AS KEYS_WITH_MAILER,
            SUM(
                CASE
                    WHEN c.HAS_DISPLAY = 1 AND c.HAS_MAILER = 1
                    THEN 1 ELSE 0
                END
            ) AS KEYS_WITH_BOTH
        FROM transaction_keys t
        LEFT JOIN causal_flags c
        USING (PRODUCT_ID, STORE_ID, WEEK_NO)
        GROUP BY MATCH_STATUS
    """, conn)

    # 5. Kiểm tra khóa sau chuẩn hóa
    total_normalized_keys = conn.execute("""
        SELECT COUNT(*) FROM causal_flags
    """).fetchone()[0]

    duplicate_normalized_keys = conn.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT PRODUCT_ID, STORE_ID, WEEK_NO
            FROM causal_flags
            GROUP BY PRODUCT_ID, STORE_ID, WEEK_NO
            HAVING COUNT(*) > 1
        )
    """).fetchone()[0]

    matched_keys = conn.execute("""
        SELECT COUNT(*)
        FROM transaction_keys t
        INNER JOIN causal_flags c
        USING (PRODUCT_ID, STORE_ID, WEEK_NO)
    """).fetchone()[0]

    total_transaction_keys = conn.execute("""
        SELECT COUNT(*) FROM transaction_keys
    """).fetchone()[0]

    summary = pd.DataFrame([
        ("Total causal source rows", causal_rows),
        ("Normalized causal keys", total_normalized_keys),
        ("Duplicate normalized keys", duplicate_normalized_keys),
        ("Total distinct transaction keys", total_transaction_keys),
        ("Matched transaction keys", matched_keys),
        ("Unmatched transaction keys",
         total_transaction_keys - matched_keys),
    ], columns=["Metric", "Value"])

    summary.to_csv(
        output / "causal_normalization_summary.csv",
        index=False,
        encoding="utf-8-sig"
    )

    promotion_summary.to_csv(
        output / "causal_promotion_flag_distribution.csv",
        index=False,
        encoding="utf-8-sig"
    )

    coverage.to_csv(
        output / "causal_normalized_transaction_coverage.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("\n========== NORMALIZATION SUMMARY ==========")
    print(summary.to_string(index=False))

    print("\n========== PROMOTION FLAG DISTRIBUTION ==========")
    print(promotion_summary.to_string(index=False))

    print("\n========== TRANSACTION COVERAGE ==========")
    print(coverage.to_string(index=False))

    print(f"\nOutput directory: {output}")

    conn.close()
    db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
