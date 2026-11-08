
import pandas as pd
from pathlib import Path

ROOT = Path.home() / "Documents" / "MiniMart_DataWarehouse_BTL"

SOURCE = ROOT / "01_Source_Data" / "Extracted_CSV" / "coupon.csv"
OUTPUT_DIR = ROOT / "02_Data_Profiling" / "04_Duplicates"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

df = pd.read_csv(
    SOURCE,
    dtype=str,
    keep_default_na=False
)

keys = [
    ["COUPON_UPC"],
    ["PRODUCT_ID"],
    ["CAMPAIGN"],
    ["COUPON_UPC", "PRODUCT_ID"],
    ["COUPON_UPC", "CAMPAIGN"],
    ["PRODUCT_ID", "CAMPAIGN"],
    ["COUPON_UPC", "PRODUCT_ID", "CAMPAIGN"]
]

results = []

for key in keys:
    unique_count = df[key].drop_duplicates().shape[0]
    duplicate_count = len(df) - unique_count

    results.append({
        "Key_Columns": " + ".join(key),
        "Unique_Combinations": unique_count,
        "Duplicate_Rows": duplicate_count,
        "Is_Unique": duplicate_count == 0
    })

result_df = pd.DataFrame(results)

output_file = OUTPUT_DIR / "coupon_key_analysis.csv"

result_df.to_csv(
    output_file,
    index=False,
    encoding="utf-8-sig"
)

print(result_df.to_string(index=False))
print("\nOutput:", output_file)
