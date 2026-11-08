# Bằng chứng kiểm chứng bản tích hợp

Ngày xây dựng: 08/11/2026. Không coi log bàn giao cũ là kết quả chạy lại của bản này.

| Phạm vi | Kết quả đã chạy | Vị trí |
|---|---|---|
| T01–T19 và 5 ca bổ sung | 24 PASS trên fixture cách ly | evidence/tests/integration.json |
| 7 trang Streamlit + RFM tùy chọn + bộ lọc rỗng | 9 kiểm tra AppTest đạt | evidence/tests/ui.json |
| Thuật toán ERD, escape SVG, catalog parser và giao diện metadata | 8 unittest đạt | evidence/build_validation/architecture.log |
| Cú pháp Python 3.11 / sáu file SQL triển khai | Phân tích cú pháp đạt | kiểm tra trong lúc đóng gói |
| Đối soát publication fixture | 14 kiểm tra đạt | evidence/build_validation/verification_fixture.json |
| Đọc toàn bộ 8 CSV gốc | Manifest, số dòng và các kiểm tra nguồn đã lưu | evidence/source_validation.json |
| Ba báo cáo profiling hiển thị trên dashboard | Đã chạy lại từ CSV gửi kèm | evidence/profiling/local_check |
| BM01 fixture / BM02-BM03 synthetic 520.000 dòng | Cổng kết quả bằng nhau và các EXPLAIN plan được tạo | evidence/tests/artifacts/bm01 và bm02_bm03 |

## Môi trường và giới hạn

Kiểm thử tích hợp dùng PostgreSQL 18.6 chạy trong WASM qua PGlite 0.5.15, client Python 3.12 trong môi trường xây dựng. Đã kiểm tra cú pháp mã tương thích Python 3.11. Adapter wire của PGlite không xử lý COPY psycopg đúng nên fixture dùng INSERT qua cổng test-only. Nhánh triển khai mặc định vẫn dùng streaming COPY cho dữ liệu lớn.

Không cài/chạy được PostgreSQL native trong môi trường xây dựng (không có Docker, không có quyền chuyển user hệ thống để khởi tạo PostgreSQL). Vì vậy **chưa nghiệm thu toàn bộ COPY + ETL 8 CSV trên PostgreSQL 16**. Kiểm tra đồng thời nhiều publisher và hiệu năng Docker thực cần chạy tại máy demo. Không dùng số thời gian PGlite để so với số đo PostgreSQL 16.

Đã thử cài trình duyệt cho kiểm thử ảnh; gói Chromium tải về bị lỗi archive nên chưa có ảnh chụp trình duyệt mới. AppTest chạy logic Streamlit thành công, không thay thế kiểm tra bố cục bằng mắt trên trình duyệt.

## Cách hoàn tất nghiệm thu tại máy demo

1. `start.ps1`: mặc định streaming COPY, đủ tám CSV, DW/mart thật.
2. `verify.ps1`: yêu cầu mọi check trong evidence/verification.json là true.
3. `run_tests.ps1`: ghi đè báo cáo test bằng lần chạy PostgreSQL 16 riêng; yêu cầu error=null và 24 PASS.
4. `run_benchmarks.ps1`: sinh bằng chứng máy demo trong evidence/bm01 và bm02_bm03.
5. Mở bảy trang, thử bộ lọc, tải SVG/CSV; chụp màn hình phục vụ báo cáo.

Mọi kết quả fixture, benchmark tổng hợp và CSV profiling đều được ghi phạm vi riêng. Báo cáo Word/PDF cũ không tự cập nhật theo kết quả tích hợp mới.
