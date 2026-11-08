
import argparse
from pathlib import Path
from collections import Counter

import pandas as pd


CHUNK_SIZE = 200_000
TIME_FORMATS = ["%H%M", "%H:%M", "%H%M%S"]


def parse_time(value):
    value = str(value).strip()

    if not value:
        return False

    for fmt in TIME_FORMATS:
        try:
            pd.to_datetime(value, format=fmt)
            return True
        except (ValueError, TypeError):
            pass

    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    input_file = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    columns = ["DAY", "WEEK_NO", "TRANS_TIME"]

    header = pd.read_csv(input_file, nrows=0).columns.tolist()
    missing_columns = [c for c in columns if c not in header]

    if missing_columns:
        raise ValueError(f"Missing columns: {missing_columns}")

    stats = {
        col: {
            "count": 0,
            "missing": 0,
            "invalid": 0,
            "min": None,
            "max": None,
            "frequency": Counter(),
        }
        for col in columns
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

        # DAY và WEEK_NO
        for col in ["DAY", "WEEK_NO"]:
            raw = chunk[col].astype(str).str.strip()
            blank = raw.eq("")
            numeric = pd.to_numeric(raw.mask(blank), errors="coerce")
            invalid = (~blank) & numeric.isna()
            valid = numeric.dropna()

            s = stats[col]
            s["missing"] += int(blank.sum())
            s["invalid"] += int(invalid.sum())
            s["count"] += len(valid)

            if len(valid):
                current_min = valid.min()
                current_max = valid.max()

                s["min"] = (
                    current_min if s["min"] is None
                    else min(s["min"], current_min)
                )
                s["max"] = (
                    current_max if s["max"] is None
                    else max(s["max"], current_max)
                )

                s["frequency"].update(valid.astype(int).value_counts().to_dict())

        # TRANS_TIME
        raw_time = chunk["TRANS_TIME"].astype(str).str.strip()
        blank = raw_time.eq("")
        valid_mask = raw_time.map(parse_time)

        s = stats["TRANS_TIME"]
        s["missing"] += int(blank.sum())
        s["invalid"] += int((~blank & ~valid_mask).sum())
        s["count"] += int(valid_mask.sum())

        s["frequency"].update(raw_time[valid_mask].value_counts().to_dict())

        print(f"Processed {total_rows:,} rows", end="\r")

    summary = []

    for col, s in stats.items():
        if col == "TRANS_TIME":
            min_value = min(s["frequency"], key=lambda x: x) if s["frequency"] else None
            max_value = max(s["frequency"], key=lambda x: x) if s["frequency"] else None
        else:
            min_value = s["min"]
            max_value = s["max"]

        summary.append({
            "Column": col,
            "Total_Rows": total_rows,
            "Valid_Count": s["count"],
            "Missing_Count": s["missing"],
            "Invalid_Count": s["invalid"],
            "Min_Value": min_value,
            "Max_Value": max_value,
            "Distinct_Values": len(s["frequency"]),
        })

    summary_df = pd.DataFrame(summary)
    summary_path = output_dir / "temporal_profiling_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")

    # Lưu 20 giá trị xuất hiện nhiều nhất của từng trường
    frequency_rows = []

    for col, s in stats.items():
        for value, count in s["frequency"].most_common(20):
            frequency_rows.append({
                "Column": col,
                "Value": value,
                "Frequency": count,
            })

    frequency_df = pd.DataFrame(frequency_rows)
    frequency_path = output_dir / "temporal_value_frequency.csv"
    frequency_df.to_csv(frequency_path, index=False, encoding="utf-8-sig")

    print("\n\n========== TEMPORAL SUMMARY ==========")
    print(summary_df.to_string(index=False))

    print("\n========== TOP VALUE FREQUENCIES ==========")
    print(frequency_df.to_string(index=False))

    print(f"\nSaved: {summary_path}")
    print(f"Saved: {frequency_path}")


if __name__ == "__main__":
    main()
