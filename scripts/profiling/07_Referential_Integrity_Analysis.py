
import argparse
from pathlib import Path
import pandas as pd


def clean(value):
    if pd.isna(value):
        return None
    value = str(value).strip()
    return value if value else None


def load_keys(path, columns):
    df = pd.read_csv(path, dtype=str, usecols=columns)
    for col in columns:
        df[col] = df[col].map(clean)

    df = df.dropna(subset=columns).drop_duplicates()
    return set(map(tuple, df[columns].itertuples(index=False, name=None)))


def profile_relation(
    input_path,
    source_columns,
    reference_keys,
    relation_name,
    output_dir,
    chunksize=200_000,
    expected_partial=False
):
    total_rows = 0
    missing_key_rows = 0
    unmatched_rows = 0
    unmatched_samples = set()

    for chunk in pd.read_csv(
        input_path,
        dtype=str,
        usecols=source_columns,
        chunksize=chunksize
    ):
        total_rows += len(chunk)

        for col in source_columns:
            chunk[col] = chunk[col].map(clean)

        valid_mask = chunk[source_columns].notna().all(axis=1)
        missing_key_rows += int((~valid_mask).sum())

        valid = chunk.loc[valid_mask, source_columns]
        keys = list(valid.itertuples(index=False, name=None))

        for key in keys:
            if key not in reference_keys:
                unmatched_rows += 1
                if len(unmatched_samples) < 100:
                    unmatched_samples.add(key)

    result = {
        "Relationship": relation_name,
        "Source_Rows": total_rows,
        "Rows_With_Missing_Key": missing_key_rows,
        "Unmatched_Rows": unmatched_rows,
        "Unmatched_Unique_Samples": len(unmatched_samples),
        "Interpretation": (
            "Expected partial coverage; not automatically an error"
            if expected_partial else
            "Review unmatched references"
        )
    }

    sample_path = output_dir / f"{relation_name}_unmatched_samples.csv"

    pd.DataFrame(
        list(unmatched_samples),
        columns=source_columns
    ).to_csv(sample_path, index=False, encoding="utf-8-sig")

    print(
        f"Checked {relation_name}: "
        f"{total_rows:,} rows, {unmatched_rows:,} unmatched"
    )

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--chunksize", type=int, default=200_000)
    args = parser.parse_args()

    source = Path(args.input_dir)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)

    files = {
        name: source / f"{name}.csv"
        for name in [
            "transaction_data",
            "product",
            "hh_demographic",
            "campaign_desc",
            "campaign_table",
            "coupon",
            "coupon_redempt",
            "causal_data"
        ]
    }

    for name, path in files.items():
        if not path.exists():
            raise FileNotFoundError(f"Missing source file: {path}")

    print("Loading reference keys...")

    product_keys = load_keys(files["product"], ["PRODUCT_ID"])
    household_keys = load_keys(
        files["hh_demographic"], ["household_key"]
    )
    campaign_keys = load_keys(
        files["campaign_desc"], ["CAMPAIGN"]
    )
    coupon_keys = load_keys(
        files["coupon"], ["CAMPAIGN", "COUPON_UPC"]
    )
    campaign_household_keys = load_keys(
        files["campaign_table"], ["household_key", "CAMPAIGN"]
    )

    results = []

    checks = [
        (
            "transaction_product",
            files["transaction_data"],
            ["PRODUCT_ID"],
            product_keys,
            False
        ),
        (
            "transaction_household_demographic_coverage",
            files["transaction_data"],
            ["household_key"],
            household_keys,
            True
        ),
        (
            "campaign_table_campaign",
            files["campaign_table"],
            ["CAMPAIGN"],
            campaign_keys,
            False
        ),
        (
            "coupon_campaign",
            files["coupon"],
            ["CAMPAIGN"],
            campaign_keys,
            False
        ),
        (
            "coupon_redempt_campaign",
            files["coupon_redempt"],
            ["CAMPAIGN"],
            campaign_keys,
            False
        ),
        (
            "coupon_redempt_coupon",
            files["coupon_redempt"],
            ["CAMPAIGN", "COUPON_UPC"],
            coupon_keys,
            False
        ),
        (
            "coupon_redempt_campaign_household",
            files["coupon_redempt"],
            ["household_key", "CAMPAIGN"],
            campaign_household_keys,
            False
        ),
        (
            "causal_data_product",
            files["causal_data"],
            ["PRODUCT_ID"],
            product_keys,
            False
        )
    ]

    for name, path, columns, reference, partial in checks:
        result = profile_relation(
            input_path=path,
            source_columns=columns,
            reference_keys=reference,
            relation_name=name,
            output_dir=output,
            chunksize=args.chunksize,
            expected_partial=partial
        )
        results.append(result)

    summary = pd.DataFrame(results)
    summary.to_csv(
        output / "referential_integrity_summary.csv",
        index=False,
        encoding="utf-8-sig"
    )

    print("\n========== REFERENTIAL INTEGRITY SUMMARY ==========")
    print(summary.to_string(index=False))
    print(f"\nResults saved to: {output}")


if __name__ == "__main__":
    main()
