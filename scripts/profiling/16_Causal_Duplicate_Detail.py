
import argparse
import sqlite3
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_file = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    db_path = output_dir / "causal_duplicate_detail_temp.sqlite"
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)

    conn.execute("""
        CREATE TABLE causal_detail (
            PRODUCT_ID TEXT,
            STORE_ID TEXT,
            WEEK_NO TEXT,
            DISPLAY TEXT,
            MAILER TEXT,
            row_count INTEGER DEFAULT 1,
            PRIMARY KEY (
                PRODUCT_ID, STORE_ID, WEEK_NO, DISPLAY, MAILER
            )
        )
    """)

    total_rows = 0

    for chunk in pd.read_csv(
        input_file,
        dtype=str,
        keep_default_na=False,
        chunksize=300000
    ):
        chunk.columns = chunk.columns.str.strip().str.upper()

        required = [
            "PRODUCT_ID", "STORE_ID", "WEEK_NO", "DISPLAY", "MAILER"
        ]
        missing = set(required) - set(chunk.columns)

        if missing:
            raise ValueError(f"Missing columns: {sorted(missing)}")

        for col in required:
            chunk[col] = chunk[col].astype(str).str.strip()

        conn.executemany("""
            INSERT INTO causal_detail (
                PRODUCT_ID, STORE_ID, WEEK_NO, DISPLAY, MAILER
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (
                PRODUCT_ID, STORE_ID, WEEK_NO, DISPLAY, MAILER
            )
            DO UPDATE SET row_count = row_count + 1
        """, chunk[required].itertuples(index=False, name=None))

        total_rows += len(chunk)
        conn.commit()
        print(f"Processed: {total_rows:,} rows")

    # Tạo bảng thống kê theo khóa nghiệp vụ
    conn.execute("""
        CREATE TABLE duplicate_keys AS
        SELECT
            PRODUCT_ID,
            STORE_ID,
            WEEK_NO,
            SUM(row_count) AS total_rows,
            COUNT(*) AS variant_count,
            COUNT(DISTINCT DISPLAY) AS display_count,
            COUNT(DISTINCT MAILER) AS mailer_count
        FROM causal_detail
        GROUP BY PRODUCT_ID, STORE_ID, WEEK_NO
        HAVING COUNT(*) > 1
    """)

    conn.commit()

    # Xuất toàn bộ các biến thể của khóa bị lặp
    details = pd.read_sql_query("""
        SELECT
            d.PRODUCT_ID,
            d.STORE_ID,
            d.WEEK_NO,
            d.DISPLAY,
            d.MAILER,
            d.row_count,
            k.total_rows,
            k.variant_count,
            k.display_count,
            k.mailer_count
        FROM causal_detail d
        INNER JOIN duplicate_keys k
        USING (PRODUCT_ID, STORE_ID, WEEK_NO)
        ORDER BY
            d.PRODUCT_ID,
            d.STORE_ID,
            d.WEEK_NO,
            d.DISPLAY,
            d.MAILER
    """, conn)

    details.to_csv(
        output_dir / "causal_duplicate_details.csv",
        index=False,
        encoding="utf-8-sig"
    )

    # Phân loại nguyên nhân khác biệt
    categories = pd.read_sql_query("""
        SELECT
            CASE
                WHEN display_count > 1 AND mailer_count > 1
                    THEN 'Different DISPLAY and MAILER'
                WHEN display_count > 1
                    THEN 'Different DISPLAY only'
                WHEN mailer_count > 1
                    THEN 'Different MAILER only'
                ELSE 'Other combination'
            END AS Difference_Type,
            COUNT(*) AS Key_Groups
        FROM duplicate_keys
        GROUP BY Difference_Type
        ORDER BY Key_Groups DESC
    """, conn)

    categories.to_csv(
        output_dir / "causal_duplicate_categories.csv",
        index=False,
        encoding="utf-8-sig"
    )

    # Phân phối số lượng giá trị DISPLAY và MAILER
    display_dist = pd.read_sql_query("""
        SELECT DISPLAY, SUM(row_count) AS Rows
        FROM causal_detail
        GROUP BY DISPLAY
        ORDER BY Rows DESC
    """, conn)

    mailer_dist = pd.read_sql_query("""
        SELECT MAILER, SUM(row_count) AS Rows
        FROM causal_detail
        GROUP BY MAILER
        ORDER BY Rows DESC
    """, conn)

    display_dist.to_csv(
        output_dir / "causal_display_distribution.csv",
        index=False,
        encoding="utf-8-sig"
    )

    mailer_dist.to_csv(
        output_dir / "causal_mailer_distribution.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("\n========== DUPLICATE DETAIL SUMMARY ==========")
    print(f"Total source rows: {total_rows:,}")
    print(f"Duplicate business-key groups: {len(details) // 2:,}")
    print(f"Distinct duplicate keys: {len(categories):,}")

    print("\n========== DIFFERENCE CATEGORIES ==========")
    print(categories.to_string(index=False))

    print("\n========== DISPLAY DISTRIBUTION ==========")
    print(display_dist.to_string(index=False))

    print("\n========== MAILER DISTRIBUTION ==========")
    print(mailer_dist.to_string(index=False))

    print("\n========== SAMPLE DUPLICATE DETAILS ==========")
    print(details.head(20).to_string(index=False))

    print(f"\nOutput directory: {output_dir}")

    conn.close()
    db_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
