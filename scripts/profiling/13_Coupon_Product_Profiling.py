
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

    coupon_file = input_dir / "coupon.csv"
    product_file = input_dir / "product.csv"

    coupon = pd.read_csv(coupon_file, dtype=str, keep_default_na=False)
    product = pd.read_csv(product_file, dtype=str, keep_default_na=False)

    required_coupon = ["CAMPAIGN", "COUPON_UPC", "PRODUCT_ID"]
    required_product = ["PRODUCT_ID"]

    for col in required_coupon:
        if col not in coupon.columns:
            raise ValueError(f"coupon.csv missing column: {col}")

    for col in required_product:
        if col not in product.columns:
            raise ValueError(f"product.csv missing column: {col}")

    # Chuẩn hóa khoảng trắng, không thay đổi mã nguồn
    for df, cols in [
        (coupon, required_coupon),
        (product, required_product),
    ]:
        for col in cols:
            df[col] = df[col].astype(str).str.strip()

    # Kiểm tra khóa rỗng
    coupon_missing = coupon[
        coupon[required_coupon].eq("").any(axis=1)
    ]

    # Đối chiếu coupon với danh mục sản phẩm
    product_ids = set(product["PRODUCT_ID"])
    coupon["PRODUCT_MATCH"] = coupon["PRODUCT_ID"].isin(product_ids)

    unmatched = coupon[~coupon["PRODUCT_MATCH"]].copy()

    # Phân tích quan hệ coupon - sản phẩm
    valid = coupon[
        coupon[required_coupon].ne("").all(axis=1)
    ].copy()

    coupon_product = valid[
        ["CAMPAIGN", "COUPON_UPC", "PRODUCT_ID"]
    ].drop_duplicates()

    products_per_coupon = (
        coupon_product.groupby(["CAMPAIGN", "COUPON_UPC"])
        ["PRODUCT_ID"].nunique()
        .reset_index(name="Distinct_Products")
    )

    coupons_per_product = (
        coupon_product.groupby("PRODUCT_ID")
        .apply(
            lambda x: x[["CAMPAIGN", "COUPON_UPC"]]
            .drop_duplicates().shape[0],
            include_groups=False,
        )
        .reset_index(name="Distinct_Coupons")
    )

    key_counts = (
        valid.groupby(["CAMPAIGN", "COUPON_UPC", "PRODUCT_ID"])
        .size()
        .reset_index(name="Occurrences")
    )

    repeated_keys = key_counts[key_counts["Occurrences"] > 1]

    summary = pd.DataFrame([
        ["Coupon rows", len(coupon)],
        ["Product rows", len(product)],
        ["Coupon rows with missing key", len(coupon_missing)],
        ["Coupon rows matched to product", int(coupon["PRODUCT_MATCH"].sum())],
        ["Coupon rows unmatched to product", len(unmatched)],
        ["Distinct campaign-coupon-product combinations", len(coupon_product)],
        ["Distinct campaign-coupon combinations", len(products_per_coupon)],
        ["Coupons linked to multiple products", int((products_per_coupon["Distinct_Products"] > 1).sum())],
        ["Products linked to multiple coupons", int((coupons_per_product["Distinct_Coupons"] > 1).sum())],
        ["Repeated campaign-coupon-product keys", len(repeated_keys)],
    ], columns=["Metric", "Value"])

    summary.to_csv(
        output_dir / "coupon_product_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    products_per_coupon.to_csv(
        output_dir / "products_per_coupon.csv",
        index=False,
        encoding="utf-8-sig",
    )

    coupons_per_product.to_csv(
        output_dir / "coupons_per_product.csv",
        index=False,
        encoding="utf-8-sig",
    )

    unmatched.to_csv(
        output_dir / "coupon_unmatched_products.csv",
        index=False,
        encoding="utf-8-sig",
    )

    repeated_keys.to_csv(
        output_dir / "coupon_repeated_business_keys.csv",
        index=False,
        encoding="utf-8-sig",
    )

    print("\n========== COUPON - PRODUCT SUMMARY ==========")
    print(summary.to_string(index=False))

    print("\n========== PRODUCTS PER COUPON ==========")
    print(products_per_coupon["Distinct_Products"].value_counts().sort_index())

    print("\n========== COUPONS PER PRODUCT ==========")
    print(coupons_per_product["Distinct_Coupons"].value_counts().sort_index())

    print(f"\nOutput directory: {output_dir}")


if __name__ == "__main__":
    main()
