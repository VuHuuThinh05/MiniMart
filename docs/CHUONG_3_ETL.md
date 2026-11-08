# Nội dung kỹ thuật cho Chương 3 — Xây dựng và vận hành ETL

## 3.1. Mục tiêu và kiến trúc

Pipeline tích hợp tám CSV Complete Journey vào kho PostgreSQL có bảy dimension, bốn fact và một bridge. Dữ liệu đi qua raw, staging, DW và mart; audit ghi nhận file, lần chạy, bước xử lý, lỗi, đối soát và phiên bản công bố. Hệ thống thực hiện batch trên nguồn tĩnh, không mô phỏng đây là CDC từ POS.

Raw bảo toàn giá trị nguồn dưới dạng text. Mỗi file có checksum SHA256 và mỗi bản ghi có số thứ tự trước khi biến đổi. Staging chuyển kiểu, trim chuỗi và phân loại dòng không đạt hợp đồng. DW sử dụng khóa thay thế, ràng buộc quan hệ và grain đã thiết kế. Lớp src cung cấp giao diện ổn định cho mart và dashboard.

[Chèn sơ đồ luồng tổng thể; ERD 12 bảng lấy từ tab Kiến trúc & ERD của database thực tế.]

## 3.2. Chuẩn hóa và xử lý ngoại lệ

Các trường mã/ngày/tuần được kiểm tra kiểu và miền giá trị. UPC giữ dạng chuỗi. TRANS_TIME kiểm tra giờ–phút HHMM. Tiền được lưu NUMERIC(18,2) theo DDL kho, làm tròn ở cấp dòng; staging giữ giá trị gốc để đối soát. Không trừ các khoản giảm giá lần nữa khỏi SALES_VALUE. Dòng có tiền/lượng bằng 0 được giữ và cảnh báo.

Product/campaign không có danh mục bị đưa vào reject. Hộ thiếu nhân khẩu học vẫn được tạo riêng với has_demographics=false. Coupon và danh mục sản phẩm là nhiều–nhiều, được tách bridge; không nhân lượt đổi coupon với các sản phẩm đủ điều kiện. FactPromotion gộp theo năm mã và lưu source_row_count, sau đó mart gộp ba mã khi đối chiếu bán hàng.

Reject có file_id, source_row_no, rule_code và raw_payload. Mặc định tồn tại reject sẽ chặn công bố; công bố phần hợp lệ cần tham số rõ ràng. Lỗi cấu trúc CSV được ghi ở bước nạp, vì chưa thể xác định một bản ghi typed hợp lệ.

[Chèn màn hình Vận hành ETL: run FAILED, bước lỗi, hai dòng reject trong fixture T09. Ghi rõ fixture, không gọi đó là lỗi trong dữ liệu thật.]

## 3.3. Thứ tự nạp và tính lặp lại

Nạp danh mục sản phẩm/chiến dịch, ngày/tuần/cửa hàng và hộ; tạo coupon trong chiến dịch; tạo bridge; tiếp theo nạp bốn fact. Sales/redemption giữ một bản ghi nguồn, UNIQUE(file_id,source_row_no). Contact gộp cặp hộ–chiến dịch. Promotion tính lại số dòng nguồn từ staging bất biến, không cộng thêm khi chạy lại.

Cùng checksum đã công bố được bỏ qua và ghi run SKIPPED. Thay đổi nội dung baseline bị chặn để tránh append hai snapshot. Lô giao dịch mới được nạp qua tham số sales-batch, phải không chồng sự kiện với baseline. Do nguồn không có event ID toàn cục, không thể khẳng định hai dòng nội dung giống nhau ở hai file khác là cùng giao dịch.

[Chèn kết quả T08/T18 và hai lần chạy cùng file; đối chiếu số dòng, tiền, lineage và version.]

## 3.4. SCD và dữ liệu đến muộn

Hộ sử dụng mã nghiệp vụ household_id và khóa phiên bản household_key. Hiệu lực theo khoảng nửa mở [from,to), một phiên bản hiện hành, không có khoảng chồng lấn. Snapshot CSV ban đầu được gán hiệu lực từ ngày 0 như quy ước triển khai, không phải bằng chứng lịch sử.

Thay đổi SCD2 có event ID và ngày hiệu lực. Sự kiện đến muộn có thể tách khoảng cũ, đồng thời cập nhật khóa phiên bản của các fact đã nạp theo ngày nguồn. Contact không có ngày nhận nên neo vào ngày bắt đầu chiến dịch. Lô sales đến muộn vẫn được xử lý dù ngày nhỏ hơn watermark; tra đúng phiên bản cũ và refresh mart/RFM.

Fixture kiểm tra thay đổi ngày 100, thay đổi đến muộn ngày 95, giao dịch ngày 90 và ranh giới ngày 100. Dữ liệu thử nghiệm tách khỏi nguồn thực. DimProduct thực hiện Type 1 có audit và giữ nguyên khóa để bridge/fact không mất liên kết.

## 3.5. Công bố, phục hồi và lịch

Raw/staging từng file được lưu để có thể tiếp tục xử lý. DW, refresh mart, release, ledger file đã commit và watermark được công bố trong cùng transaction. Nếu bước này lỗi, database rollback và giữ mart/version trước. Audit lỗi tồn tại ngoài transaction công bố; mất kết nối có thêm file lỗi cục bộ và lần chạy tiếp theo đánh dấu run bỏ dở ABORTED.

Khóa advisory ngăn publisher chạy đồng thời. Scheduler một tiến trình chạy định kỳ 24 giờ, đợi lần chạy trước kết thúc rồi mới đặt lịch tiếp. Đây là lịch batch kiểm tra file tĩnh; lô bổ sung và thay đổi dimension được gọi explicit. Refresh thường có thể khóa đọc tạm thời; hệ thống không cam kết không gián đoạn.

## 3.6. Kiểm thử và kết quả

Danh mục T01–T19 nằm trong tests/test_integration.py. Kết quả sinh ra từ lần chạy thật ở evidence/tests/integration.json, gồm engine, thời điểm, COPY/INSERT mode, phạm vi và từng test. Bản kiểm chứng xây dựng dùng PGlite/fixture; không thay cho nghiệm thu PostgreSQL 16 với CSV thật. Đối soát dữ liệu thật chạy verify.ps1, lưu version và số đo tại evidence/verification.json.

[Chèn bảng kết quả từ lần chạy trên máy demo; không chép số đo hiệu năng của môi trường khác.]

BM01 đo snapshot từ DW với kết quả tổng hợp đã materialize; BM02/BM03 dùng dữ liệu tổng hợp 520.000 dòng. Chỉ rút kết luận trong phạm vi query và môi trường đo, không suy ra tỷ số tăng tốc toàn dashboard.
