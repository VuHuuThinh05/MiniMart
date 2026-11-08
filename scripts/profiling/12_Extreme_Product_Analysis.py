
import argparse
from pathlib import Path

import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    product_file = input_dir / "product.csv"
    quantity_file = output_dir / "top_100_quantity_transactions.csv"
    sales_file = output_dir / "top_100_sales_value_transactions.csv"

    product = pd.read_csv(product_file, dtype=str)

    product_columns = [
        "PRODUCT_ID",
        "MANUFACTURER",
        "DEPARTMENT",
        "COMMODITY_DESC",
        "SUB_COMMODITY_DESC",
        "BRAND",
        "CURR_SIZE_OF_PRODUCT",
    ]

    product_columns = [
        c for c in product_columns if c in product.columns
    ]

    product = product[product_columns].drop_duplicates(
        subset=["PRODUCT_ID"]
    )

    for filename, metric in [
        (quantity_file, "QUANTITY"),
        (sales_file, "SALES_VALUE"),
    ]:
        transactions = pd.read_csv(filename, dtype=str)

        result = transactions.merge(
            product,
            on="PRODUCT_ID",
            how="left",
            indicator=True,
        )

        result["PRODUCT_MATCH"] = result["_merge"].map({
            "both": "Matched",
            "left_only": "Unmatched",
        })

        result.drop(columns=["_merge"], inplace=True)

        output_file = output_dir / (
            f"top_100_{metric.lower()}_with_product.csv"
        )

        result.to_csv(
            output_file,
            index=False,
            encoding="utf-8-sig",
        )

        print(f"\n========== TOP {metric} WITH PRODUCT ==========")
        display_columns = [
            c for c in [
                "PRODUCT_ID",
                "QUANTITY",
                "SALES_VALUE",
                "DEPARTMENT",
                "COMMODITY_DESC",
                "SUB_COMMODITY_DESC",
                "BRAND",
                "CURR_SIZE_OF_PRODUCT",
                "PRODUCT_MATCH",
            ]
            if c in result.columns
        ]

        print(result[display_columns].head(15).to_string(index=False))
        print(f"Saved: {output_file}")


if __name__ == "__main__":
    main()
