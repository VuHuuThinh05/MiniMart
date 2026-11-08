# Hợp đồng dữ liệu và quyết định tích hợp v1

## Đầu vào và đích

| CSV gốc | Chuẩn hóa/kiểm tra | Đích chính | Grain/khóa |
|---|---|---|---|
| product | PRODUCT_ID và MANUFACTURER số nguyên; mã sản phẩm duy nhất; trim thuộc tính | dim_product | Một mã sản phẩm; khóa thay thế ổn định; Type 1 |
| hh_demographic | mã hộ duy nhất, thuộc tính có thể thiếu | dim_household | Một mã hộ + khoảng hiệu lực SCD2 |
| campaign_desc | mã chiến dịch duy nhất, 0 ≤ start ≤ end | dim_campaign | Một campaign_id |
| campaign_table | mã hộ, tham chiếu campaign | fact_campaign_contact | DISTINCT hộ bền vững + chiến dịch; chọn dòng nguồn đầu theo file_id/row_no |
| coupon | coupon_upc là text, product/campaign phải tồn tại | dim_coupon + bridge_coupon_product | Coupon trong chiến dịch; bridge DISTINCT coupon_key/product_key |
| coupon_redempt | mã hộ/ngày/campaign hợp lệ; tra coupon theo campaign + UPC | fact_coupon_redemption | Một bản ghi nguồn; UNIQUE(file_id,source_row_no) |
| transaction_data | mã hộ/giỏ/ngày/sản phẩm/cửa hàng/tuần, HHMM, tiền/lượng hợp lệ | fact_sales | Một bản ghi nguồn; không tự xóa hai giao dịch giống nhau |
| causal_data | mã sản phẩm tồn tại, store/week hợp lệ, display/mailer không trống | fact_promotion | Sản phẩm/cửa hàng/tuần/display/mailer; đếm source_row_count |

DimDay lấy ngày nguồn bán hàng/đổi coupon và biên chiến dịch. DimWeek giữ WEEK_NO nguồn. Không suy ra ngày lịch, tháng, năm hay tuần ISO. DimStore từ giao dịch và quảng bá, không bịa tên/vùng. DimHousehold hợp nhất mã hộ từ cả giao dịch, liên hệ, đổi coupon và nhân khẩu học. Hộ thiếu nhân khẩu học vẫn có mã riêng.

## Khóa và lineage

- `file_id = source_name + ':' + SHA256(bytes)`; `source_row_no` từ 1, không gồm header, theo thứ tự bản ghi CSV (không phải số dòng vật lý nếu trường có xuống dòng).
- Raw giữ text và file/dòng nguồn. Staging lưu giá trị typed, `valid`; reject giữ mã lỗi và raw_payload. Dữ liệu gốc không bị sửa.
- Số dòng trong audit.files.loaded_rows là số dòng staging hợp lệ, **không phải** số dòng fact sau gộp.
- Contact/bridge có thể gộp nhiều dòng nguồn. `audit.bridge_lineage`, `audit.promotion_lineage` truy ngược từng dòng accepted. Contact có thể tra lại staging bằng household/campaign; fact giữ một dòng đại diện.
- FactPromotion tính lại COUNT từ staging bất biến, không cộng dồn source_row_count khi replay.
- BasketKey = `household_id:basket_id:day:store_id`. Các thành phần được kiểm tra là số nguyên không âm. `src.transaction_data.basket_id` là BasketKey dạng text; mã giỏ gốc nằm tại `dw.fact_sales.basket_id`. Dashboard dùng DISTINCT BasketKey.
- `household_id` là mã hộ bền vững. `dw.household_key` là khóa phiên bản. Adapter xuất household_id thành bigint để tương thích UI hiện có; không dùng surrogate để đếm hộ.

## Quy tắc xử lý

1. Các ID đầu vào của bộ CSV này là số nguyên không âm; UPC giữ nguyên chuỗi và số 0 đầu. Đây là hợp đồng dataset, không phải adapter tổng quát cho mã chữ.
2. Trống/kiểu sai/tràn giới hạn/HHMM sai: reject. Tiền/lượng không được NaN/Infinity. Lượng tối đa 3 chữ số thập phân. Số tiền có phần lẻ >2 chữ số được làm tròn bằng PostgreSQL `round(numeric,2)` trước khi nạp fact; raw/stg giữ số gốc.
3. Giá trị tiền/lượng bằng 0 được giữ; lượng âm giữ và cảnh báo để kiểm tra nghiệp vụ, không tự diễn giải là hoàn trả. Giảm giá giữ nguyên dấu, không trừ lần nữa khỏi SALES_VALUE.
4. Tham chiếu product/campaign không tồn tại: reject. Không tạo sản phẩm giả. Coupon xuất hiện trong redemption nhưng chưa có catalog sản phẩm vẫn có DimCoupon, bridge có thể rỗng.
5. Redemption ngoài kỳ hoặc không có contact được giữ để audit; KPI hưởng ứng chỉ tính hộ thuộc tập nhận, đổi đúng chiến dịch và đúng thời gian. Không phân bổ lượt đổi xuống toàn bộ sản phẩm đủ điều kiện.
6. Dimension trùng mã: loại các dòng xung đột và chặn công bố mặc định. Coupon trùng triple gộp bridge; contact trùng cặp gộp contact. Sales/redemption giữ grain dòng nguồn.
7. Không có dòng causal tương ứng là Unknown. Gộp quảng bá về product/store/week trước khi JOIN sales để không nhân dòng. `source_row_count` của fact 5-key được SUM khi lên mart 3-key.
8. Baseline là snapshot bất biến. Thay checksum bị chặn; cập nhật snapshot cần project mới để tránh trộn hai phiên bản. Lô late-sales phải là sự kiện mới không chồng với baseline; không có event ID toàn cục để tự phát hiện trùng giữa hai nội dung file khác nhau.

## SCD, đến muộn, Type 1

- CSV nhân khẩu học chỉ là một snapshot. Baseline hộ có hiệu lực từ ngày 0 là quy ước để tra cứu; không khẳng định biết lịch sử thực trước khi quan sát.
- SCD2 dùng khoảng `[from,to)`, một current và exclusion không chồng lấn. Thay đổi phải có event_id, effective_day, thuộc tính cụ thể.
- Nếu event đến muộn rơi vào giữa khoảng cũ, tách khoảng đó; không ghi đè phiên bản tương lai. Cập nhật FK của các fact đã nạp theo ngày sự kiện trong cùng transaction.
- Sales/redemption neo bằng source_day; contact thiếu ngày nhận nên neo bằng ngày bắt đầu campaign (quy ước được ghi rõ).
- RFM lấy thuộc tính nhân khẩu học đúng ngày chốt qua materialized history đã công bố; số hộ nhóm theo household_id.
- `product_update.py` thực hiện Type1 được audit theo event ID, giữ product_key để fact/bridge không mất liên kết. Không áp dụng SCD2 sản phẩm trong luồng chính.
- Fixture SCD2 và lô late chỉ chạy trong test service; không được trình bày như lịch sử thay đổi thật của bộ CSV.

## Công bố, phục hồi và lịch

Raw/stg của mỗi file được commit riêng để có thể tiếp tục sau lỗi. Sau khi ghi reject và đối soát, bước DW + tất cả refresh mart + mart.release + audit.committed_file + watermark nằm trong **một transaction**. Lỗi ở bước này rollback toàn bộ; raw/stg/reject và audit FAILED còn để giải thích.

Khóa advisory 760501 bao trùm publisher, SCD và benchmark. Kết thúc tiến trình thì kết nối đóng, transaction chưa commit rollback và khóa được giải phóng. Lần chạy sau đánh dấu RUNNING bỏ dở thành ABORTED trước khi phục hồi. Watermark chỉ là max ngày đã commit; file có ngày cũ hơn vẫn được nạp.

Refresh MV thông thường có khóa đọc: dashboard có thể phải chờ, không cam kết zero downtime. Cache khóa theo release + SQL + tham số; truy vấn trong REPEATABLE READ kiểm tra release để tránh trộn phiên bản.

Scheduler chạy tuần tự mỗi 24 giờ, không chạy chồng. Đây là lịch batch kiểm tra snapshot và retry sau lỗi, không CDC. Lô bổ sung và thay đổi dimension dùng lệnh explicit để tránh tự nạp nhầm fixture.
