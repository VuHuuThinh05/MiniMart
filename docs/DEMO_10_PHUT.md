# Kịch bản demo 10 phút

## Chuẩn bị trước giờ học

Chạy `start.ps1`, `verify.ps1`, `run_tests.ps1`, `run_benchmarks.ps1` từ README. Nạp đủ CSV trước; không chờ nạp 36 triệu dòng causal tại lớp. Mở localhost:8502. Giữ log/kết quả máy mình, không lấy số thời gian trong thư mục reference thay thế.

## 0–2 phút: bài toán và kiến trúc

Giới thiệu phạm vi tập hộ Complete Journey. Mở Kiến trúc & ERD, chọn dw.fact_sales và 1 bước; có 5 dimension FK. Chọn tất cả 12 bảng dw nếu cần toàn galaxy. Giải thích hộ bền vững khác khóa SCD. Xem `docs/MAPPING_VA_QUY_TAC.md` cho luồng raw → staging → DW → mart.

## 2–4 phút: ETL và đối soát

Mở Vận hành ETL, chọn PUBLISHED: từng bước, file/checksum, read/accepted/rejected/skipped, watermark. Chạy lại:

```powershell
docker compose -p minimart_demo run --rm tools python -u scripts/etl.py
```

Kỳ vọng SKIPPED vì cùng manifest; số fact và version không đổi. Bấm Tải lại trang để xem run mới. Mở Chất lượng dữ liệu: đối soát từ DB, phân biệt với tab kết quả profiling CSV do Lam làm.

## 4–6 phút: lỗi, SCD và đến muộn

Dùng báo cáo `evidence/tests/integration.json`, chọn T09/T10/T18/T19. Đây là fixture tách riêng, không phải lịch sử khách thật. Giải thích khoảng [0,95), [95,100), [100,∞), giao dịch ngày 90 đến sau vẫn dùng phiên bản cũ. T09 chứng minh reject có lý do và rollback không đổi release/watermark. Nếu có thời gian chạy lại `run_tests.ps1`; không chèn fixture vào DB demo.

## 6–8 phút: nghiệp vụ

Bán hàng: lọc tuần/ngành; giải thích DISTINCT và phần giỏ. Hộ: ngày chốt và 365 ngày; thử 362 ngày thấy cảnh báo ngưỡng. Campaign: hộ nhận khác lượt đổi, mẫu số 0 trả không xác định. Quảng bá: gộp 3-key, Unknown không đồng nghĩa không quảng bá.

## 8–10 phút: hiệu năng và giới hạn

BM01 dùng snapshot từ DW; so sánh quét/tổng hợp với kết quả đã tính, báo thêm chi phí refresh. BM02/BM03 là synthetic 520.000 dòng, không suy ra tốc độ toàn dashboard. Hiện engine/thời điểm và số lượt đo. Kết thúc bằng phần còn giới hạn: không lịch ngày thật, không giá vốn/ROI, không nhân quả, SCD nguồn tĩnh chỉ minh họa bằng fixture.

## Phân công khi thuyết trình

- Lam: dữ liệu, profiling, ý nghĩa KPI và kết quả test.
- Khánh: grain, PK/FK, mô hình SCD, BM02/BM03.
- Long: raw/stg/reject, nạp DW, idempotency, audit, đến muộn, phục hồi và lịch.
- Thịnh: adapter, mart, Streamlit, cache/công bố, BM01.

Code ETL trong bản này được bổ sung khi tích hợp để bao phủ phạm vi Long; không mô tả nó là code đã nằm trong ba ZIP ban đầu.
