
import argparse
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd

COLUMNS = [
    "household_key",
    "BASKET_ID",
    "DAY",
    "STORE_ID",
    "WEEK_NO",
]

CHUNK_SIZE = 200_000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--chunksize", type=int, default=CHUNK_SIZE)
    args = parser.parse_args()

    input_file = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_file.exists():
        raise FileNotFoundError(f"Không tìm thấy: {input_file}")

    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "basket_analysis.sqlite"
        conn = sqlite3.connect(db_path)

        conn.execute("""
            CREATE TABLE transactions (
                household_key TEXT,
                BASKET_ID TEXT,
                DAY TEXT,
                STORE_ID TEXT,
                WEEK_NO TEXT
            )
        """)

        total_rows = 0
        missing = {c: 0 for c in COLUMNS}

        try:
            for chunk_no, chunk in enumerate(
                pd.read_csv(
                    input_file,
                    dtype=str,
                    chunksize=args.chunksize,
                    encoding="utf-8-sig"
                ),
                start=1
            ):
                chunk.columns = chunk.columns.str.strip()

                absent = [c for c in COLUMNS if c not in chunk.columns]
                if absent:
                    raise ValueError(f"Thiếu cột: {absent}")

                data = chunk[COLUMNS].copy()

                for col in COLUMNS:
                    data[col] = data[col].replace(
                        r"^\s*$", pd.NA, regex=True
                    )
                    missing[col] += int(data[col].isna().sum())

                data = data.astype(object).where(
                    pd.notna(data), None
                )

                conn.executemany(
                    """
                    INSERT INTO transactions
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    data.itertuples(index=False, name=None)
                )
                conn.commit()

                total_rows += len(chunk)
                print(
                    f"Chunk {chunk_no}: {len(chunk):,} rows | "
                    f"Total: {total_rows:,}"
                )

            # A. Thống kê theo BASKET_ID
            basket = pd.read_sql_query("""
                SELECT
                    BASKET_ID,
                    COUNT(*) AS source_rows,
                    COUNT(DISTINCT household_key) AS household_count,
                    COUNT(DISTINCT DAY) AS day_count,
                    COUNT(DISTINCT STORE_ID) AS store_count,
                    COUNT(DISTINCT WEEK_NO) AS week_count
                FROM transactions
                WHERE BASKET_ID IS NOT NULL
                GROUP BY BASKET_ID
            """, conn)

            # B. Thống kê theo household_key + BASKET_ID
            household_basket = pd.read_sql_query("""
                SELECT
                    household_key,
                    BASKET_ID,
                    COUNT(*) AS source_rows,
                    COUNT(DISTINCT DAY) AS day_count,
                    COUNT(DISTINCT STORE_ID) AS store_count,
                    COUNT(DISTINCT WEEK_NO) AS week_count
                FROM transactions
                WHERE household_key IS NOT NULL
                  AND BASKET_ID IS NOT NULL
                GROUP BY household_key, BASKET_ID
            """, conn)

            # C. Kiểm tra ứng viên BasketKey
            candidate = pd.read_sql_query("""
                SELECT
                    household_key,
                    BASKET_ID,
                    DAY,
                    STORE_ID,
                    COUNT(*) AS source_rows,
                    COUNT(DISTINCT WEEK_NO) AS week_count
                FROM transactions
                WHERE household_key IS NOT NULL
                  AND BASKET_ID IS NOT NULL
                  AND DAY IS NOT NULL
                  AND STORE_ID IS NOT NULL
                GROUP BY
                    household_key, BASKET_ID, DAY, STORE_ID
            """, conn)

            # D. Các nhóm có dấu hiệu không nhất quán
            basket_conflicts = basket[
                (basket.household_count > 1)
                | (basket.day_count > 1)
                | (basket.store_count > 1)
                | (basket.week_count > 1)
            ]

            household_conflicts = household_basket[
                (household_basket.day_count > 1)
                | (household_basket.store_count > 1)
                | (household_basket.week_count > 1)
            ]

            candidate_conflicts = candidate[
                candidate.week_count > 1
            ]

            # E. Bảng tổng hợp
            summary = [
                ("Total transaction rows", total_rows),
                ("Distinct BASKET_ID", len(basket)),
                ("BASKET_ID with multiple households",
                 int((basket.household_count > 1).sum())),
                ("BASKET_ID with multiple days",
                 int((basket.day_count > 1).sum())),
                ("BASKET_ID with multiple stores",
                 int((basket.store_count > 1).sum())),
                ("BASKET_ID with multiple weeks",
                 int((basket.week_count > 1).sum())),
                ("Distinct household + BASKET_ID",
                 len(household_basket)),
                ("Household-basket with multiple days",
                 int((household_basket.day_count > 1).sum())),
                ("Household-basket with multiple stores",
                 int((household_basket.store_count > 1).sum())),
                ("Household-basket with multiple weeks",
                 int((household_basket.week_count > 1).sum())),
                ("Candidate BasketKey count", len(candidate)),
                ("Candidate BasketKey with multiple weeks",
                 int((candidate.week_count > 1).sum())),
                ("Candidate BasketKey with multiple source rows",
                 int((candidate.source_rows > 1).sum())),
            ]

            for col, count in missing.items():
                summary.append((f"Missing {col}", count))

            summary_df = pd.DataFrame(
                summary, columns=["Metric", "Value"]
            )

            outputs = {
                "basket_consistency_summary.csv": summary_df,
                "basket_id_profile.csv": basket,
                "household_basket_profile.csv": household_basket,
                "candidate_basketkey_profile.csv": candidate,
                "basket_id_conflicts.csv": basket_conflicts,
                "household_basket_conflicts.csv": household_conflicts,
                "candidate_basketkey_conflicts.csv": candidate_conflicts,
            }

            for filename, df in outputs.items():
                path = output_dir / filename
                df.to_csv(
                    path, index=False, encoding="utf-8-sig"
                )
                print(f"Saved: {path} ({len(df):,} rows)")

            print("\n========== SUMMARY ==========")
            print(summary_df.to_string(index=False))
            print("\nAnalysis completed.")

        finally:
            conn.close()


if __name__ == "__main__":
    main()
