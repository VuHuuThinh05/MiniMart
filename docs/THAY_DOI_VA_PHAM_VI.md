# Đối chiếu ba phần bàn giao và bản tích hợp

## Nguồn đóng góp

| Phần | Đã sử dụng | Điều chỉnh khi hợp nhất |
|---|---|---|
| Lam | Đề xuất nghiệp vụ, tám CSV, profiling, grain/lineage, tiêu chí T01–T19 | Giữ tài liệu gốc trong reference; đưa các quy tắc thành validation và kiểm thử chạy được; không coi kết quả profiling là CSV đã làm sạch |
| Khánh | 12 bảng DW, 17 FK, exclusion SCD2, index, bus matrix/ERD, ý tưởng BM02/BM03 | DDL chạy trong database cấu hình của dự án (mặc định minimart), bỏ guard minimart_dw; không đổi cấu trúc 88 cột của DW; bổ sung ETL dùng đúng khóa và grain |
| Thịnh | Dữ liệu, Docker/wheels, mart, RFM, dashboard, BM01 và tab ERD/profiling | Chuyển toàn bộ tham chiếu nguồn sang src đọc DW; sửa BasketKey, lịch sử nhân khẩu học, source count quảng bá; thêm vận hành ETL; tách bằng chứng cũ |
| Phạm vi Long được bổ sung | Trước đó chưa có trong ba ZIP một pipeline DW hoàn chỉnh | scripts/etl.py, raw/stg, reject, ledger, load DW, SCD/Type1, late sales, atomic publish, phục hồi và scheduler |

README gốc của Khánh có nhãn tên thành viên không khớp phân công người dùng cung cấp. Giữ nguyên file gốc để truy vết; bảng này dùng phân công đã xác nhận trong cuộc trao đổi.

## Quyết định giải quyết khác biệt

- Database giữ tên minimart; dw là schema bên trong, không phải tên database mới.
- Dùng household_id cho KPI; household_key của DW chỉ dùng tra phiên bản. Các view src giữ kiểu mã bigint của dashboard vì bộ CSV này dùng mã số.
- Dùng BasketKey tổng hợp theo đề xuất Lam; `src.basket_id` đổi sang text. Vì kiểu cột MV cũ khác, không triển khai ghi đè vào mart đang chạy: bản mới dùng project Docker/volume riêng.
- Khánh lưu NUMERIC(18,2), Thịnh độc lập giữ numeric gốc. Chốt làm tròn từng dòng vào fact, giữ raw/stg gốc. Có 29 dòng nguồn thêm chữ số; tổng sau làm tròn vẫn 8.057.463,08 USD trong bộ được gửi, nhưng không mặc định mọi tập lọc đều bằng tuyệt đối bản cũ.
- FactPromotion giữ 5-key; mart chỉ gộp về 3-key trước khi nối. Không dùng count(fact rows) làm số dòng causal gốc; phải SUM(source_row_count).
- RFM theo ngày chốt dùng lịch sử nhân khẩu học đã materialize cùng release; tránh lấy thuộc tính hiện hành cho mọi ngày chốt.
- Contact neo SCD vào ngày bắt đầu chiến dịch do không có ngày nhận thực tế; đây là quy ước, không phải dữ liệu quan sát.
- BM02/BM03 có cổng kiểm tra toàn bộ multiset và kết quả query bằng nhau; dùng 3 warmup + 15 lượt xoay thứ tự thay cho 1 warmup + 5 lượt của bản gốc. Không tái sử dụng số đo cũ sau thay đổi phương pháp.

## Phần cần nghiệm thu tại máy demo

Code, fixture, hướng dẫn, dữ liệu gốc và wheels đều có trong bản đầy đủ. Môi trường xây dựng không chạy được PostgreSQL native/Docker; kiểm thử SQL dùng PostgreSQL WASM 18.6/PGlite, khác PostgreSQL 16 của bản triển khai. COPY production được giữ nguyên và cần kiểm tra khi chạy start.ps1 trên máy người dùng. Không dùng fallback INSERT cho dữ liệu thật.

Chưa có kết quả chạy COPY toàn bộ 8 CSV, benchmark DW thật hay ảnh chụp trình duyệt của bản tích hợp trên máy Thịnh. Các lệnh README tạo bằng chứng đó. Báo cáo Word/PDF cũ được giữ ở reference/thinh_docs, chưa tự động trở thành báo cáo của bản tích hợp; dùng tài liệu mới và số đo mới để sửa Chương 3/4.
