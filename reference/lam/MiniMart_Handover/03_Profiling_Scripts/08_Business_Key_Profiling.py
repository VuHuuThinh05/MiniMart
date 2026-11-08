
import argparse
from pathlib import Path
import pandas as pd


def profile_key(file_path, table_name, key_columns):
    df = pd.read_csv(file_path, dtype=str)

    for col in key_columns:
        df[col] = df[col].str.strip()
        df[col] = df[col].replace("", pd.NA)

    missing_mask = df[key_columns].isna().any(axis=1)
    valid = df.loc[~missing_mask, key_columns]

    counts = valid.value_counts(dropna=False)

    duplicate_groups = int((counts > 1).sum())
    duplicate_excess = int((counts - 1).clip(lower=0).sum())
    max_occurrences = int(counts.max()) if len(counts) else 0

    result = {
        "Table": table_name,
        "Key_Columns": " + ".join(key_columns),
        "Total_Rows": len(df),
        "Rows_With_Missing_Key": int(missing_mask.sum()),
        "Distinct_Key_Combinations": len(counts),
        "Duplicate_Groups": duplicate_groups,
        "Duplicate_Excess_Rows": duplicate_excess,
        "Max_Occurrences": max_occurrences,
        "Is_Unique": duplicate_groups == 0 and missing_mask.sum() == 0
    }

    if duplicate_groups > 0:
        duplicate_keys = counts[counts > 1].reset_index(name="Occurrences")
        duplicate_keys.to_csv(
            output_dir / f"{table_name}_duplicate_keys.csv",
            index=False,
            encoding="utf-8-sig"
        )

    if missing_mask.any():
        df.loc[missing_mask].to_csv(
            output_dir / f"{table_name}_missing_keys.csv",
            index=False,
            encoding="utf-8-sig"
        )

    print(
        f"{table_name}: {len(df):,} rows | "
        f"{duplicate_groups:,} duplicate groups | "
        f"{int(missing_mask.sum()):,} missing-key rows"
    )

    return result


parser = argparse.ArgumentParser()
parser.add_argument("--input-dir", required=True)
parser.add_argument("--output-dir", required=True)
args = parser.parse_args()

input_dir = Path(args.input_dir)
output_dir = Path(args.output_dir)
output_dir.mkdir(parents=True, exist_ok=True)

# Không chạy lại transaction_data và coupon:
# hai bảng này đã được phân tích khóa trước đó.

key_checks = [
    ("product", ["PRODUCT_ID"]),
    ("hh_demographic", ["household_key"]),
    ("campaign_desc", ["CAMPAIGN"]),
    ("campaign_table", ["household_key", "CAMPAIGN"]),
    (
        "coupon_redempt",
        ["household_key", "DAY", "COUPON_UPC", "CAMPAIGN"]
    )
]

results = []

for table_name, key_columns in key_checks:
    file_path = input_dir / f"{table_name}.csv"

    if not file_path.exists():
        raise FileNotFoundError(f"Không tìm thấy: {file_path}")

    results.append(
        profile_key(file_path, table_name, key_columns)
    )

summary = pd.DataFrame(results)

summary.to_csv(
    output_dir / "business_key_profiling_summary.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\n========== BUSINESS KEY PROFILING SUMMARY ==========")
print(summary.to_string(index=False))
print(f"\nResults saved to: {output_dir}")
