# KPI phiên bản minimart-kpi-v2 / rfm-fixed-v1

Nguồn công bố: DW → src → mart. Tiền USD; phạm vi tập hộ được quan sát. Không suy ra toàn chuỗi, lợi nhuận, ROI hoặc tác động nhân quả.

| KPI | Công thức | Giới hạn |
|---|---|---|
| Doanh số | SUM(sales_value) | NUMERIC(18,2) trong DW; đã làm tròn từng dòng theo thiết kế kho |
| Số giỏ | COUNT(DISTINCT BasketKey) | Không cộng số giỏ qua ngành/tuần |
| Giá trị chọn/giỏ | Doanh số sau lọc / giỏ có phần khớp lọc | Lọc SKU/ngành chỉ là phần giỏ, không phải giá trị toàn giỏ |
| Hộ mua | COUNT(DISTINCT household_id) | Không đếm khóa phiên bản SCD |
| Mua lặp | Hộ ≥2 giỏ / hộ ≥1 giỏ trong cửa sổ | Không gọi là retention giữa hai kỳ |
| RFM | R=ngày chốt−ngày mua cuối trong cửa sổ; F=số giỏ; M=tổng tiền trong cửa sổ | Không mua: R NULL, F/M=0, điểm 0, nhóm riêng |
| Hưởng ứng | Hộ nhận có đổi đúng campaign trong kỳ / hộ nhận phân biệt ×100 | Mẫu số 0 → NULL; không nhân với danh mục sản phẩm |
| Trước/trong/sau | Tổng tiền / (số hộ nhận × số ngày quan sát) | Trước/sau tối đa 28 ngày, cắt biên nguồn, giữ hộ không mua |
| Quảng bá | Tổng tiền theo product/store/week và trạng thái đã gộp | Không có causal là Unknown; không phải số lượt xem |

Ngưỡng quy ước cho 365 ngày: R≤30/60/90/180/>180 → 5/4/3/2/1; F≥52/26/12/4/khác →5/4/3/2/1; M≥2000/1000/500/100/khác →5/4/3/2/1. Cùng giá trị nhận cùng điểm. Ngưỡng là đề xuất demo, chưa tối ưu bằng mô hình dự báo.

Thứ tự CASE phân nhóm: không mua; giá trị cao (R≥4,F≥4,M≥4); nguy cơ rời bỏ (R≤2,F≥3); mua thường xuyên (R≥4,F≥3); mua gần đây (R≥4); cần theo dõi. Không gọi phân nhóm là dự báo churn/CLV đã kiểm định.

Ngày chốt mặc định=max DAY đã công bố; cửa sổ 365 ngày. Đổi cửa sổ không tự đổi ngưỡng F/M; UI cảnh báo. Nhân khẩu học lấy phiên bản hiệu lực tại ngày chốt. Phần dữ liệu trước biên nguồn không được suy ra là không mua.

Các thay đổi so với bản Thịnh độc lập: nguồn DW, BasketKey tổng hợp, tiền 2 chữ số trong fact, nhân khẩu học as-of và audit ETL thật. Giữ công thức phân tích còn lại để dễ đối chiếu. Dùng `verify.ps1` kiểm tra dữ liệu của lần công bố mới, không tái sử dụng log 9 PASS cũ làm bằng chứng cho DW.
