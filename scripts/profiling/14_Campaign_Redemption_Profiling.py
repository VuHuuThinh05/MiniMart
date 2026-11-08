
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

    campaign_table = pd.read_csv(
        input_dir / "campaign_table.csv",
        dtype=str,
        keep_default_na=False,
    )

    redempt = pd.read_csv(
        input_dir / "coupon_redempt.csv",
        dtype=str,
        keep_default_na=False,
    )

    campaign_desc = pd.read_csv(
        input_dir / "campaign_desc.csv",
        dtype=str,
        keep_default_na=False,
    )

    # Chuẩn hóa khoảng trắng ở các khóa
    for df, cols in [
        (campaign_table, ["household_key", "CAMPAIGN"]),
        (redempt, ["household_key", "CAMPAIGN", "DAY", "COUPON_UPC"]),
        (campaign_desc, ["CAMPAIGN", "START_DAY", "END_DAY"]),
    ]:
        for col in cols:
            if col not in df.columns:
                raise ValueError(f"Missing column: {col}")
            df[col] = df[col].astype(str).str.strip()

    # Chuyển đổi các trường ngày và kiểm tra tính hợp lệ
    redempt["DAY_NUM"] = pd.to_numeric(
        redempt["DAY"], errors="coerce"
    )
    campaign_desc["START_NUM"] = pd.to_numeric(
        campaign_desc["START_DAY"], errors="coerce"
    )
    campaign_desc["END_NUM"] = pd.to_numeric(
        campaign_desc["END_DAY"], errors="coerce"
    )

    # Đối chiếu hộ gia đình và chiến dịch được nhận
    contact_keys = campaign_table[
        ["household_key", "CAMPAIGN"]
    ].drop_duplicates()

    result = redempt.merge(
        contact_keys.assign(CONTACT_MATCH=True),
        on=["household_key", "CAMPAIGN"],
        how="left",
    )

    result["CONTACT_MATCH"] = result["CONTACT_MATCH"].fillna(False)

    # Đối chiếu thời gian hiệu lực chiến dịch
    result = result.merge(
        campaign_desc[
            ["CAMPAIGN", "START_NUM", "END_NUM"]
        ].drop_duplicates(subset=["CAMPAIGN"]),
        on="CAMPAIGN",
        how="left",
        indicator="CAMPAIGN_MATCH",
    )

    result["CAMPAIGN_FOUND"] = result["CAMPAIGN_MATCH"].eq("both")
    result["DATE_VALID"] = (
        result["CAMPAIGN_FOUND"]
        & result["DAY_NUM"].notna()
        & result["START_NUM"].notna()
        & result["END_NUM"].notna()
        & (result["DAY_NUM"] >= result["START_NUM"])
        & (result["DAY_NUM"] <= result["END_NUM"])
    )

    # Phân loại kết quả
    result["PROFILE_STATUS"] = "Valid"
    result.loc[~result["CONTACT_MATCH"], "PROFILE_STATUS"] = (
        "Household not in campaign_table"
    )
    result.loc[
        ~result["CAMPAIGN_FOUND"], "PROFILE_STATUS"
    ] = "Campaign not found"
    result.loc[
        result["CAMPAIGN_FOUND"] & ~result["DATE_VALID"],
        "PROFILE_STATUS",
    ] = "Outside campaign period or invalid day"

    # Tổng hợp
    summary = pd.DataFrame([
        ["Total redemption rows", len(result)],
        ["Redemptions matched to contacted household", int(result["CONTACT_MATCH"].sum())],
        ["Redemptions unmatched to campaign_table", int((~result["CONTACT_MATCH"]).sum())],
        ["Redemptions with campaign found", int(result["CAMPAIGN_FOUND"].sum())],
        ["Redemptions within campaign period", int(result["DATE_VALID"].sum())],
        ["Redemptions outside campaign period or invalid day", int((~result["DATE_VALID"]).sum())],
        ["Fully valid redemption rows", int((result["CONTACT_MATCH"] & result["DATE_VALID"]).sum())],
    ], columns=["Metric", "Value"])

    status_summary = (
        result["PROFILE_STATUS"]
        .value_counts(dropna=False)
        .rename_axis("Profile_Status")
        .reset_index(name="Rows")
    )

    detail_columns = [
        "household_key",
        "CAMPAIGN",
        "DAY",
        "COUPON_UPC",
        "CONTACT_MATCH",
        "CAMPAIGN_FOUND",
        "START_NUM",
        "END_NUM",
        "DATE_VALID",
        "PROFILE_STATUS",
    ]

    result[detail_columns].to_csv(
        output_dir / "campaign_redemption_details.csv",
        index=False,
        encoding="utf-8-sig",
    )

    summary.to_csv(
        output_dir / "campaign_redemption_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    status_summary.to_csv(
        output_dir / "campaign_redemption_status.csv",
        index=False,
        encoding="utf-8-sig",
    )

    print("\n========== CAMPAIGN - REDEMPTION SUMMARY ==========")
    print(summary.to_string(index=False))

    print("\n========== PROFILE STATUS ==========")
    print(status_summary.to_string(index=False))

    print("\n========== SAMPLE DETAILS ==========")
    print(result[detail_columns].head(15).to_string(index=False))

    print(f"\nOutput directory: {output_dir}")


if __name__ == "__main__":
    main()
