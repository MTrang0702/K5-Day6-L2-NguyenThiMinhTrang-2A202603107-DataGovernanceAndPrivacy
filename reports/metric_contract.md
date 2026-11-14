# Metric contract (khai báo bắt buộc — chốt ở phút 30, trước khi chạy eval)

> Các metric chuẩn đã được cài trong `src/metrics/tracks.py`. File này là nơi nhóm **cam kết** cách dùng chúng.
> Không đổi testset, threshold hay trọng số sau khi đã thấy kết quả eval.

| Mục | Khai báo của nhóm |
|---|---|
| Track | T02 · Raw QC Triage: ảnh mờ, lóa và thiếu sáng |
| Primary metric (tên đúng như evaluator in ra) | `Defect Recall@B` |
| Tăng tốt hay giảm tốt? | higher (càng cao càng tốt) |
| Đơn vị đánh giá (image / region / pair / release / batch / case …) | image (từng ảnh trong tập dữ liệu) |
| Công thức + numerator / denominator | $\text{Recall@B} = \frac{\text{# ảnh lỗi trong top-B}}{\text{Tổng số ảnh lỗi thực tế (GT defects)}}$ (numerator: số lỗi GT tìm thấy trong top-B; denominator: tổng số ảnh lỗi GT) |
| Cách ghép prediction ↔ GT (IoU? id? tolerance?) | Khớp chính xác theo khóa định danh `image_id` |
| Candidate pool cố định | 96 ảnh synthetic 320×180 từ 24 cảnh trong `fixtures/t02_raw_qc/images.csv` |
| Review budget B / K | Budget $B = 20$ ảnh |
| Seed | 42 |
| Threshold policy (chọn trên dev như thế nào) | Chuẩn hóa thống kê và tinh chỉnh ngưỡng hoàn toàn trên tập `dev` (56 ảnh, 14 cảnh); tuyệt đối không nhìn trước nhãn tập `eval` (40 ảnh, 10 cảnh) |
| Eval split (không dùng để tune) | `eval` split (40 ảnh cố định theo phân chia cảnh gốc `scene_id`) |
| Chỉ số lỗi xấu (miss / false alarm / false reject) | Missed defect (bỏ sót ảnh lỗi lọt vào tập release) và False alarm (báo nhầm ảnh đêm sạch/ảnh camera mềm vào hàng đợi lỗi) |
| Slices sẽ báo cáo (≥2) | 1. Slice điều kiện ánh sáng `light` (`day`, `dusk`, `night`)<br>2. Slice loại camera `camera_id` (`cam_A`, `cam_B`)<br>3. Slice loại lỗi `defect_type` (`blur`, `glare`, `dark`, `compression`) |
| Cách báo độ bất định khi N nhỏ (Wilson CI / bootstrap) | Khoảng tin cậy Wilson score interval cho tỷ lệ nhị phân và Bootstrap 95% CI |
| Ngày giờ chốt + người chốt | 15:30 14/11/2026 · Nguyễn Thị Minh Trang (Lead/Owner) |

Nếu baseline = 0 thì ghi rõ "baseline = 0" thay vì phần trăm cải thiện.
