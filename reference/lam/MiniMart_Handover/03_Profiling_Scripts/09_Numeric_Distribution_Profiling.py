
import argparse
from pathlib import Path

import numpy as np
import pandas as pd


NUMERIC_COLUMNS = [
    "SALES_VALUE",
    "QUANTITY",
    "RETAIL_DISC",
    "COUPON_DISC",
    "COUPON_MATCH_DISC",
]

CHUNK_SIZE = 200_000


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_file = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Kiểm tra header thực tế trước khi xử lý
    header = pd.read_csv(input_file, nrows=0).columns.tolist()
    columns = [c for c in NUMERIC_COLUMNS if c in header]

    if not columns:
        raise ValueError("Không tìm thấy các cột số cần kiểm tra.")

    missing_columns = [c for c in NUMERIC_COLUMNS if c not in header]
    print("Columns found:", columns)
    if missing_columns:
        print("Columns not found:", missing_columns)

    stats = {
        c: {
            "count": 0,
            "missing": 0,
            "invalid": 0,
            "zero": 0,
            "negative": 0,
            "sum": 0.0,
            "min": np.inf,
            "max": -np.inf,
            "values": [],
        }
        for c in columns
    }

    total_rows = 0

    for chunk in pd.read_csv(
        input_file,
        usecols=columns,
        dtype=str,
        chunksize=CHUNK_SIZE,
        keep_default_na=False,
    ):
        total_rows += len(chunk)

        for col in columns:
            raw = chunk[col].astype(str).str.strip()
            blank = raw.eq("")

            numeric = pd.to_numeric(raw.mask(blank), errors="coerce")
            invalid = (~blank) & numeric.isna()
            valid = numeric.dropna()

            s = stats[col]
            s["missing"] += int(blank.sum())
            s["invalid"] += int(invalid.sum())

            if len(valid) == 0:
                continue

            arr = valid.to_numpy(dtype=np.float64)

            s["count"] += len(arr)
            s["zero"] += int((arr == 0).sum())
            s["negative"] += int((arr < 0).sum())
            s["sum"] += float(arr.sum())
            s["min"] = min(s["min"], float(arr.min()))
            s["max"] = max(s["max"], float(arr.max()))
            s["values"].append(arr)

        print(f"Processed {total_rows:,} rows", end="\r")

    summary = []

    for col, s in stats.items():
        if s["values"]:
            values = np.concatenate(s["values"])
            q = np.quantile(values, [0.25, 0.5, 0.75, 0.95, 0.99])
            mean = s["sum"] / s["count"]
            minimum = s["min"]
            maximum = s["max"]
        else:
            q = [np.nan] * 5
            mean = minimum = maximum = np.nan

        summary.append({
            "Column": col,
            "Total_Rows": total_rows,
            "Valid_Count": s["count"],
            "Missing_Count": s["missing"],
            "Invalid_Count": s["invalid"],
            "Zero_Count": s["zero"],
            "Negative_Count": s["negative"],
            "Min": minimum,
            "Q1": q[0],
            "Median": q[1],
            "Q3": q[2],
            "P95": q[3],
            "P99": q[4],
            "Max": maximum,
            "Mean": mean,
        })

    result = pd.DataFrame(summary)
    output_file = output_dir / "numeric_distribution_summary.csv"
    result.to_csv(output_file, index=False, encoding="utf-8-sig")

    print("\n\n========== SUMMARY ==========")
    print(result.to_string(index=False))
    print(f"\nSaved: {output_file}")


if __name__ == "__main__":
    main()
