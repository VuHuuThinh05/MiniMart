
import argparse
from pathlib import Path

import pandas as pd


CHUNK_SIZE = 200_000
TOP_N = 100

COLUMNS = [
    "household_key",
    "BASKET_ID",
    "DAY",
    "PRODUCT_ID",
    "QUANTITY",
    "SALES_VALUE",
    "STORE_ID",
    "RETAIL_DISC",
    "TRANS_TIME",
    "WEEK_NO",
    "COUPON_DISC",
    "COUPON_MATCH_DISC",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_file = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    header = pd.read_csv(input_file, nrows=0).columns.tolist()
    columns = [c for c in COLUMNS if c in header]

    required = ["QUANTITY", "SALES_VALUE"]
    missing = [c for c in required if c not in columns]

    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    quantity_candidates = []
    sales_candidates = []
    total_rows = 0

    for chunk in pd.read_csv(
        input_file,
        usecols=columns,
        dtype=str,
        chunksize=CHUNK_SIZE,
        keep_default_na=False,
    ):
        total_rows += len(chunk)

        for col in ["QUANTITY", "SALES_VALUE"]:
            chunk[col] = pd.to_numeric(
                chunk[col].str.strip(),
                errors="coerce"
            )

        quantity_candidates.append(
            chunk.nlargest(TOP_N, "QUANTITY")
        )

        sales_candidates.append(
            chunk.nlargest(TOP_N, "SALES_VALUE")
        )

        print(f"Processed {total_rows:,} rows", end="\r")

    quantity_top = (
        pd.concat(quantity_candidates, ignore_index=True)
        .nlargest(TOP_N, "QUANTITY")
    )

    sales_top = (
        pd.concat(sales_candidates, ignore_index=True)
        .nlargest(TOP_N, "SALES_VALUE")
    )

    quantity_path = output_dir / "top_100_quantity_transactions.csv"
    sales_path = output_dir / "top_100_sales_value_transactions.csv"

    quantity_top.to_csv(
        quantity_path, index=False, encoding="utf-8-sig"
    )
    sales_top.to_csv(
        sales_path, index=False, encoding="utf-8-sig"
    )

    print("\n\n========== EXTREME VALUE SUMMARY ==========")
    print(f"Total transaction rows: {total_rows:,}")

    print("\nTop 10 QUANTITY:")
    print(quantity_top.head(10).to_string(index=False))

    print("\nTop 10 SALES_VALUE:")
    print(sales_top.head(10).to_string(index=False))

    print(f"\nSaved: {quantity_path}")
    print(f"Saved: {sales_path}")


if __name__ == "__main__":
    main()
