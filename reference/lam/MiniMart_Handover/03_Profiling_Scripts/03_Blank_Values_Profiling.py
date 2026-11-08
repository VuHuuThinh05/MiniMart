import pandas as pd
from pathlib import Path

ROOT = Path.home() / "Documents" / "MiniMart_DataWarehouse_BTL"
DATA_DIR = ROOT / "01_Source_Data" / "Extracted_CSV"
OUTPUT_DIR = ROOT / "02_Data_Profiling" / "03_Missing_Values"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

results = []

for file in sorted(DATA_DIR.glob("*.csv")):
    print(f"Processing: {file.name}")

    for chunk in pd.read_csv(
        file,
        dtype=str,
        keep_default_na=False,
        chunksize=200_000
    ):
        for column in chunk.columns:
            values = chunk[column].astype(str)

            blank_count = int(
                values.str.strip().eq("").sum()
            )

            whitespace_count = int(
                (
                    values.ne("") &
                    values.str.strip().eq("")
                ).sum()
            )

            key = (file.name, column)

            if not any(
                r["File_Name"] == key[0] and
                r["Column_Name"] == key[1]
                for r in results
            ):
                results.append({
                    "File_Name": file.name,
                    "Column_Name": column,
                    "Total_Rows": 0,
                    "Blank_Count": 0,
                    "Whitespace_Count": 0
                })

            for r in results:
                if (
                    r["File_Name"] == key[0] and
                    r["Column_Name"] == key[1]
                ):
                    r["Total_Rows"] += len(chunk)
                    r["Blank_Count"] += blank_count
                    r["Whitespace_Count"] += whitespace_count
                    break

result_df = pd.DataFrame(results)

result_df.to_csv(
    OUTPUT_DIR / "blank_values_profile.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\nCompleted!")
print("Total columns:", len(result_df))
print("Output:", OUTPUT_DIR / "blank_values_profile.csv")