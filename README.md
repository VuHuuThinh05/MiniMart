# MiniMart — bản tích hợp để demo

Bản xây dựng ngày 08/11/2026 từ ba ZIP Thịnh, Lam và Khánh. Bổ sung ETL thuộc phạm vi Long, nối dashboard sang kho chung. Xem `docs/THAY_DOI_VA_PHAM_VI.md` để biết nguồn đóng góp và giới hạn kiểm chứng.

## Chạy nhanh trên Windows

**Giải nén thành thư mục mới `MiniMart_TichHop`. Không chép đè bản đang chạy.**

- Project Docker mới: `minimart_demo`; database vẫn `minimart`.
- PostgreSQL ở `localhost:55433`; dashboard `http://localhost:8502`.
- Bản `minimart_v2`/55432/8501 hiện có không bị đổi.
- Cần Docker Desktop đang chạy Linux containers; lần đầu cần có image `postgres:16`, `python:3.11-slim`. Wheels được giữ từ ZIP Thịnh để cài Python offline. Nếu Docker hỏi chia sẻ đúng thư mục dự án, chọn Yes.
- `Data` chứa đủ tám CSV gốc. Không thay chúng bằng CSV kết quả profiling.
- Raw, staging, fact, materialized view và WAL cần nhiều dung lượng hơn CSV. Kiểm tra còn khoảng vài chục GB trống; nạp lần đầu có thể kéo dài nhiều phút tùy máy. Terminal in tên file/bước đang chạy. Không bấm khởi động nhiều lần đồng thời.

Mở PowerShell trong thư mục vừa giải nén:

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Lệnh khởi động DB, build dashboard, nạp ETL, đối soát, công bố rồi mở web. Lần sau cùng file sẽ SKIPPED, không tăng dữ liệu. `-ReloadData` chỉ buộc đối soát/refresh lại; **không thay baseline hoặc xóa dữ liệu**.

Nếu PowerShell báo lỗi, dừng tại lỗi đầu tiên; không chạy `down -v`, không xóa volume. Sau khi sửa nguyên nhân, chạy lại cùng lệnh; raw/stg đã hoàn tất được dùng lại, DW/mart chưa commit không bị giữ dở.

## Xác nhận trên máy demo

```powershell
powershell -ExecutionPolicy Bypass -File .\verify.ps1
powershell -ExecutionPolicy Bypass -File .\run_tests.ps1
powershell -ExecutionPolicy Bypass -File .\run_benchmarks.ps1
```

- `verify.ps1`: đối soát chỉ đọc trên **dữ liệu demo thật**; lưu `evidence/verification.json`.
- `run_tests.ps1`: T01–T19 và ca bổ sung trên PostgreSQL test riêng, chứa fixture nhỏ; không xóa/nạp fixture vào database demo. T12 trong test dùng BM01 fixture và BM02/BM03 synthetic. Kết quả `evidence/tests/integration.json`; kế hoạch và số đo ở `evidence/tests/artifacts/`.
- `run_benchmarks.ps1`: BM01 snapshot lấy từ DW thật; BM02/BM03 vẫn là 520.000 dòng tổng hợp theo thiết kế Khánh. Bằng chứng tại `evidence/bm01` và `evidence/bm02_bm03`. Đây là thời gian truy vấn trong DB, không phải thời gian tải web.
- Sau đó Streamlit → Tải lại trang. Không dùng số đo của môi trường xây dựng để viết thành kết quả máy cá nhân.

Kỳ vọng với đúng tám CSV nguyên bản: 2.595.732 dòng bán hàng, 276.484 giỏ, 2.500 hộ, tổng tiền 8.057.463,08 USD; 7.208 contacts, 2.318 redemptions, 119.384 cặp bridge, 36.786.524 dòng nguồn quảng bá. Đây là mốc đối chiếu nguồn; `verify.ps1` mới xác nhận DW thực tế của lần chạy.

## Thư mục và luồng

`Data → raw → stg → dw → src → mart → Streamlit`.

- `scripts/etl.py`: nạp, kiểm tra, audit, idempotency và công bố.
- `scripts/scd.py`, `product_update.py`: cập nhật SCD2 hộ và Type1 sản phẩm có event ID.
- `scripts/scheduler.py`: lịch batch đơn tiến trình; profile `schedule` tùy chọn.
- `sql/01_dw.sql`: cấu trúc Khánh; giữ 7 dimension, 4 fact, 1 bridge.
- `sql/02_operations.sql`: audit, reject, ledger file và watermark.
- `sql/03_load_dw.sql`: ánh xạ vào DW; `04_source_views.sql`: giao diện cho mart.
- `sql/10_marts.sql`: mart và RFM đã đổi nguồn sang DW.
- `dashboard/app.py`: bốn trang nghiệp vụ, chất lượng, ERD và vận hành ETL.
- `scripts/profiling`: bản script đã chuẩn hóa của Thịnh/Lam. Bằng chứng CSV được hiển thị riêng, không giả làm audit ETL trực tiếp.
- `reference`: tài liệu và kết quả bàn giao cũ, có thể khác phiên bản chạy mới; không dùng các lệnh DDL bên trong để ghi đè database tích hợp.
- `legacy`: code/migration bản độc lập, chỉ giữ để tham khảo.

## Nạp một lô bán hàng đến muộn

Sau khi đã nạp baseline, đặt file có cùng 12 cột giao dịch vào `batches/sales/` (tự tạo thư mục). File phải chỉ gồm **sự kiện mới chưa có trong baseline**, không phải bản sao đổi nội dung của toàn bộ transaction_data.

```powershell
docker compose -p minimart_demo run --rm tools python -u scripts/etl.py --sales-batch batches/sales/late_001.csv
```

Checksum + số thứ tự bản ghi xác định sự kiện nguồn. Cùng nội dung gửi lại, dù đổi tên, không tăng fact. Một nội dung giao dịch giống nhau trong hai file khác không tự coi là trùng: dữ liệu không có event ID toàn cục để kết luận. Người cung cấp lô phải bảo đảm không chồng sự kiện.

Baseline thay checksum bị chặn để tránh nối hai snapshot. Muốn thay toàn bộ dataset, tạo project/volume mới rồi đối soát; không cần xóa demo cũ.

## Lỗi và dòng bị loại

Mặc định có dòng reject sẽ dừng công bố. Vào Vận hành ETL xem lý do hoặc đọc `audit.rejects`. Chỉ khi đã quyết định dùng phần hợp lệ:

```powershell
docker compose -p minimart_demo run --rm tools python -u scripts/etl.py --allow-rejects
```

Số dòng bị loại được giữ trong audit, không tự sửa/xóa raw. CSV hỏng cấu trúc (thiếu cột, sai dấu ngoặc kép) làm thất bại bước COPY và được ghi trong log bước; không thể gán một bản ghi hợp lệ để đưa vào reject theo dòng.

## Lịch chạy, tạm dừng, sao lưu

```powershell
# Bật kiểm tra/nạp baseline ngay khi scheduler khởi động, rồi mỗi 24 giờ.
docker compose -p minimart_demo --profile schedule up -d scheduler
# Xem log
docker compose -p minimart_demo logs --tail 100 scheduler
# Dừng lịch
docker compose -p minimart_demo stop scheduler
# Sao lưu database
powershell -ExecutionPolicy Bypass -File .\backup.ps1
# Kết thúc buổi demo, giữ dữ liệu
docker compose -p minimart_demo stop
```

Lịch này là batch kiểm tra file tĩnh, không CDC/API. Lô bán hàng bổ sung chạy bằng lệnh riêng ở trên. Khóa advisory ngăn hai ETL/publisher cùng chạy. Mật khẩu trong compose là tài khoản demo cục bộ; cổng chỉ bind localhost.

## Kiểm chứng trước khi bàn giao

Xem `docs/KIEM_CHUNG.md`: đã chạy kiểm thử logic trên PostgreSQL WASM/PGlite bằng fixture, AppTest bảy trang, và khảo sát đọc toàn bộ CSV. **Chưa chạy trọn bộ COPY + ETL 8 CSV trên PostgreSQL 16/Docker Desktop của bạn trong môi trường này.** Có sẵn các lệnh trên để nghiệm thu chính xác tại máy demo. Không ghi “toàn bộ đã PASS trên máy Thịnh” trước khi có các log tương ứng.

## Chạy lại profiling CSV đang hiển thị

```powershell
docker compose -p minimart_demo run --rm tools python scripts/profile_demo.py
```

Ba báo cáo này độc lập với validation ETL. Các script profiling còn lại được giữ để tra cứu; một số đọc toàn bộ causal bằng pandas nên có thể cần nhiều RAM, không chạy tự động khi mở demo.
