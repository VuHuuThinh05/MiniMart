
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

duplicate_mask = df.duplicated(keep="first")

duplicates = df[duplicate_mask]

duplicates.to_csv(
    OUTPUT_DIR / "coupon_exact_duplicate_rows.csv",
    index=False,
    encoding="utf-8-sig"
)

all_duplicate_groups = df[df.duplicated(keep=False)]

all_duplicate_groups.to_csv(
    OUTPUT_DIR / "coupon_all_duplicate_groups.csv",
    index=False,
    encoding="utf-8-sig"
)

print("Total rows:", len(df))
print("Duplicate rows (excluding first occurrences):", len(duplicates))
print("Rows belonging to duplicate groups:", len(all_duplicate_groups))
print("Output directory:", OUTPUT_DIR)
