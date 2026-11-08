
import pandas as pd
from pathlib import Path

ROOT = Path.home() / "Documents" / "MiniMart_DataWarehouse_BTL"
DATA_DIR = ROOT / "01_Source_Data" / "Extracted_CSV"
OUTPUT_DIR = ROOT / "02_Data_Profiling" / "02_Data_Types"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

results = []

for file in sorted(DATA_DIR.glob("*.csv")):
    print(f"Processing: {file.name}")

    # Đọc dữ liệu theo từng cột dưới dạng chuỗi
    # để tránh tự động làm biến đổi mã định danh.
    df = pd.read_csv(file, dtype=str)

    for column in df.columns:
        values = df[column].dropna()

        numeric_values = pd.to_numeric(
            values, errors="coerce"
        )

        results.append({
            "File_Name": file.name,
            "Column_Name": column,
            "Pandas_Dtype": str(df[column].dtype),
            "Total_Rows": len(df),
            "Non_Null_Count": int(df[column].notna().sum()),
            "Null_Count": int(df[column].isna().sum()),
            "Numeric_Convertible_Count": int(numeric_values.notna().sum()),
            "Non_Numeric_Count": int(
                len(values) - numeric_values.notna().sum()
            ),
            "Sample_Values": " | ".join(
                values.drop_duplicates().head(5).tolist()
            )
        })

result_df = pd.DataFrame(results)

output_file = OUTPUT_DIR / "data_type_profile.csv"
result_df.to_csv(output_file, index=False, encoding="utf-8-sig")

print("\nCompleted!")
print("Total columns:", len(result_df))
print("Output:", output_file)
