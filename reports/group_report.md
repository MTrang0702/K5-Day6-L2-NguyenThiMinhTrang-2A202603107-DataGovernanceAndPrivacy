# Group Report — Day 06 Data Lab (Field-to-Release PoC)

> Điền đầy đủ, cụ thể, không viết chung chung. Mọi con số lấy từ file do script sinh ra
> (`reports/metrics_*.json`, `reports/table1_baseline_vs_poc.md`).

## 00 · Header

| Mục | Giá trị |
|---|---|
| Group ID | G_2A202603107 (Cá nhân) |
| Challenge | T02 · Raw QC Triage: ảnh mờ, lóa và thiếu sáng |
| Thành viên (1) + vai trò | 1. Nguyễn Thị Minh Trang - MSSV: 2A202603107 (Solo Lead / Pipeline, QA & Report) |
| Git URL | https://github.com/MTrang0702/K5-Day6-L2-NguyenThiMinhTrang-2A202603107-DataGovernanceAndPrivacy.git |
| Tag `demo-180m` (commit) | demo-180m |
| Tag `final-24h` (commit) | final-24h |
| Deadline (giờ VN) | 2026-11-14 18:00 (Mốc 180m) / 2026-11-15 14:00 (+24h) |

## 01 · Problem statement

- **Ai bị ảnh hưởng / ai chịu hậu quả khi hệ thống sai?**
  Các mô hình nhận diện phía sau trong hệ thống tự hành ADAS (object detection, lane tracking, segmentation) và người tham gia giao thông. Nếu ảnh bị mờ nặng do rung lắc, lóa sáng chói mắt hoặc tối mịt lọt vào tập huấn luyện/sản xuất, mô hình sẽ hallucinate hoặc bỏ sót chướng ngại vật; ngược lại nếu loại nhầm ảnh đêm hợp lệ, mô hình sẽ thiếu hụt dữ liệu lái xe ban đêm nghiêm trọng.
- **Điểm nghẽn cụ thể:**
  Đội ngũ annotation và kiểm thử chất lượng dữ liệu (Data QC) có ngân sách thời gian hữu hạn ($B = 20$ ảnh cho mỗi batch 96 ảnh). Không thể duyệt thủ công từng khung hình, cần cơ chế tự động xếp hạng ưu tiên các ảnh có nguy cơ lỗi cao nhất để con người kiểm duyệt và quyết định KEEP hay RECAPTURE.
- **Đầu vào → đầu ra:**
  - Đầu vào: 96 ảnh lái xe synthetic kích thước 320×180 từ 24 cảnh gốc kèm metadata (`image_id, path, camera_id, light, split`) và `manifest.csv`.
  - Đầu ra: File xếp hạng kiểm duyệt `out/poc/ranked_review.csv` (`image_id, score, pred_defect_type, pred_action, reason`), danh sách hàng đợi `review_queue.csv`, trang web trực quan `contact_sheet.html`, nhật ký kiểm toán `audit_log.jsonl`, và quyết định phát hành `decision.json`.
- **Tiêu chí GO / HOLD / REWORK (chốt trước khi chạy eval):**
  - `GO` (Phát hành): Tỷ lệ ảnh lỗi nghiêm trọng $\le 15\%$ tổng số ảnh.
  - `REWORK` (Thu thập lại): Tỷ lệ ảnh lỗi $> 15\%$, đưa danh sách top-$B$ ảnh lỗi vào hàng đợi đi chụp/quay bổ sung (Recapture Plan).
  - `HOLD` (Tạm dừng): Vi phạm tính toàn vẹn nguồn gốc (`strict_provenance`) hoặc lỗi hệ thống không thể xác định.
- **Giả định của nhóm (cần DPO/legal/domain owner xác nhận):**
  Dữ liệu thực hành là synthetic hoàn toàn (CC0, procedurally generated), không chứa khuôn mặt hoặc biển số xe thật. Khi triển khai trên dữ liệu thực tế ngoài đường, cần DPO và đội ngũ pháp lý thẩm định quy chuẩn bảo vệ dữ liệu cá nhân (GDPR / Nghị định 13/2023/NĐ-CP).

## 02 · Data & provenance

| Split | N | Nguồn / link | License | Synthetic? |
|---|---|---|---|---|
| dev | 56 ảnh (14 cảnh gốc) | `fixtures/t02_raw_qc/images/` | CC0 1.0 Universal | Có (Synthetic procedural) |
| eval / heldout | 40 ảnh (10 cảnh gốc) | `fixtures/t02_raw_qc/images/` | CC0 1.0 Universal | Có (Synthetic procedural) |

- **Schema & class mapping:**
  - Cột bảng: `image_id` (string), `path` (relpath), `camera_id` (`cam_A`, `cam_B`), `light` (`day`, `dusk`, `night`), `split` (`dev`, `eval`).
  - Lớp lỗi (Ground Truth): `defect_type ∈ {none, blur, glare, dark, compression}`, `severity 0–2`, `is_defect ∈ {0, 1}`.
- **Seed: 42 · Cách chia split:**
  Chia theo cảnh gốc (`scene_id`, 4 ảnh/cảnh) với tỷ lệ xấp xỉ 60% dev (14 cảnh) / 40% eval (10 cảnh) để đảm bảo không bị rò rỉ dữ liệu cùng cảnh giữa tập phát triển và tập đánh giá.
- **`manifest.csv` verified (sha256):**
  Có. Đã kiểm tra 100% khớp bằng lệnh `python -m tools.preflight` và `python -m tools.verify_manifests`.
- **Dữ liệu thật dùng (nếu có):**
  Không dùng dữ liệu thật ngoài gói offline fixtures để đảm bảo tính tái lập 100% không phụ thuộc mạng.

## 03 · Research & design

- **2–3 references và vì sao chọn kỹ thuật:**
  1. *Pech-Pacheco et al. (ICPR 2000)*: Diatom autofocusing using modified Laplacian. Chọn Laplacian Variance vì chi phí tính toán cực thấp ($O(N)$), đo trực tiếp năng lượng tần số cao của cạnh sắc nét.
  2. *Wang et al. (IEEE TIP 2004)*: Blind Measurement of Blocking Artifacts in Images. Khai thác sự gián đoạn gradient tại ranh giới khối $8\times 8$ để phát hiện nén JPEG chất lượng thấp mà không cần ảnh gốc.
  3. *ISO/IEC TR 5259-6:2026 / CVAT Automated QA*: Thiết kế quy trình kiểm soát chất lượng dữ liệu nhiều tầng kết hợp Human-in-the-loop.
- **Sơ đồ data flow:**
  `Input (images + manifest) -> 01 load (SHA256 check) -> 02 process (Multi-feature QC) -> 03 rank (Top-20 queue + HTML contact sheet) -> 04 review (Human verification + Audit log) -> 05 decide (GO/REWORK Gate) -> Report`.
- **Thành phần offline:**
  Thuần túy dùng NumPy, Pillow, SciPy và OpenCV CPU cơ bản. Không tải model pretrained, không gọi API ngoài mạng.
- **Trade-offs đã cân nhắc:**
  - Nếu chỉ dùng ngưỡng Laplacian toàn ảnh (như Baseline), mô hình sẽ bỏ sót hoàn toàn lỗi lóa sáng (`glare`) và nén JPEG (`compression`), đồng thời báo nhầm ảnh ban đêm hữu ích thành lỗi.
  - Nhóm chọn kết hợp 4 nhánh đặc trưng chuẩn hóa theo ngữ cảnh (`camera_id` và `light`), tăng nhẹ thời gian tính toán từ 0.35s lên 0.44s/100 ảnh nhưng tăng độ chính xác Precision@20 từ 70% lên 100%.

## 04 · Baseline vs PoC

- **Baseline:** Ngưỡng Laplacian toàn ảnh duy nhất (`src/baseline.py`, `laplacian_variance`).
- **PoC:** Pipeline đa đặc trưng chuẩn hóa theo camera và điều kiện ánh sáng (`src/pipeline.py`).
- **Cùng budget / cùng heldout / cùng seed:** Xác nhận cùng seed 42, cùng budget $B=20$, cùng candidate pool 96 ảnh.

**Bảng 1 · Baseline vs PoC & hard slices**

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **Defect Recall@B** (fraction) | all | 0.5185 | 0.7407 | +0.2222 | +42.9% | higher | 56 |
| Precision@B (fraction) | all | 0.7000 | 1.0000 | +0.3000 | +42.9% | higher | 56 |
| False alarm in top-B (fraction) | light=night | 0.2000 | 0.0000 | -0.2000 | -100.0% | lower | 20 |
| Runtime / 100 items (s) | all | 0.3457 | 0.4431 | +0.0974 | - | lower | 96 |

## 05 · Evaluation protocol

- **Công thức primary metric:**
  $$\text{Defect Recall@B} = \frac{\sum_{i \in \text{top-B}} \mathbb{I}(\text{is\_defect}_i = 1)}{\sum_{\text{all}} \mathbb{I}(\text{is\_defect}_i = 1)}$$
  Đơn vị đánh giá: từng ảnh đơn lẻ.
- **Threshold / budget B và lúc chốt:**
  Chốt ngân sách $B = 20$ ảnh; ngưỡng lỗi $0.25$ cho từng nhánh đặc trưng được chốt trước trên tập `dev` ở phút 30 (tại `reports/metric_contract.md`).
- **Độ bất định:**
  Khoảng tin cậy Wilson Score Interval 95% cho Recall@20 của PoC đạt $[0.551, 0.869]$.
- **Lệnh evaluate:**
  `python -m src.main --config configs/lab.yaml --track t02 --output out/poc --run-name poc --offline --seed 42`

## 06 · Result slices

| Slice | N | Baseline Recall | PoC Recall | Ghi chú |
|---|---:|---:|---:|---|
| Defect: `blur` | 8 | 1.0000 (8/8) | 1.0000 (8/8) | Cả hai phương pháp đều bắt trọn vẹn lỗi mờ |
| Defect: `glare` | 4 | 0.0000 (0/4) | 1.0000 (4/4) | Baseline mù hoàn toàn trước lóa; PoC đạt 100% |
| Defect: `dark` | 6 | 0.6667 (4/6) | 0.5000 (3/6) | Tập trung bắt các ca tối mịt nghiêm trọng |
| Defect: `compression`| 9 | 0.2222 (2/9) | 0.5556 (5/9) | PoC bắt thêm được các ca vỡ khối DCT nặng |
| Light: `night` (False Alarm) | 10 | 0.2000 (2/10) | 0.0000 (0/10) | PoC triệt tiêu hoàn toàn báo nhầm ảnh đêm sạch |

- **Failure case 1 (Cháy sáng nhẹ / Glare cục bộ nhỏ):**
  Ảnh có vết lóa diện tích nhỏ dưới 0.2% khung hình nhưng nằm ngay biển số xe. Do diện tích bão hòa toàn ảnh chưa vượt ngưỡng 0.0025 nên chưa được ưu tiên trong top-20. *Khắc phục:* Cần bổ sung phân tích ROI cục bộ cho các vùng trọng yếu.
- **Failure case 2 (Ảnh nén JPEG mức trung bình severity 1):**
  Một số ảnh JPEG nén ở quality=15 có chỉ số blockiness $\sim 1.55$ (nằm sát ngưỡng 1.65) nên không kích hoạt điểm lỗi tối đa.
- **Latency / compute:**
  Thực thi trên máy Intel Core i5/i7 (CPU x86_64), trung bình **4.43 ms/ảnh** (tương đương tốc độ xử lý > 220 khung hình/giây), đáp ứng thừa điều kiện chạy thời gian thực.

## 07 · Human & decision

- **Review queue:**
  Tự động xuất ra file `out/poc/review_queue.csv` gồm đúng $B=20$ ảnh có `score` cao nhất. Đi kèm trang web ngoại tuyến `out/poc/contact_sheet.html` hiển thị ảnh gốc, chỉ số lỗi và nút chọn quyết định.
- **Cách override + audit log:**
  File `out/poc/review_queue_reviewed.csv` ghi nhận phán quyết của người kiểm (`reviewer = Nguyễn Thị Minh Trang (Lead/Owner)`). Toàn bộ thao tác can thiệp được lưu vào `out/poc/audit_log.jsonl` theo chuẩn append-only kèm timestamp và lý do.
- **Decision policy:**
  - Phát hiện 43/96 khung hình có dấu hiệu lỗi ($44.8\% > 15\%$).
  - Trạng thái ban hành: `REWORK` với mã lý do `RECAPTURE_REQUIRED`.
  - Quyết định: Giữ cổng phát hành dữ liệu, yêu cầu đội thu thập quay bổ sung top-20 khung hình lỗi trước khi đóng gói release.

## 08 · Reproduce & tests

```bash
# 1. Chạy PoC hoàn chỉnh (Offline contract)
python -m src.main --input fixtures/t02_raw_qc --config configs/lab.yaml --output out/poc --run-name poc --offline --seed 42

# 2. Chạy baseline
python -m src.main --config configs/lab.yaml --track t02 --pipeline src.baseline --output out/baseline --run-name baseline --offline --seed 42

# 3. So sánh hiệu năng
python -m src.compare reports/metrics_baseline.json reports/metrics_poc.json --out reports/table1_baseline_vs_poc.md

# 4. Kiểm thử toàn diện
pytest -q
```

- **Output của `pytest -q`:**
  `51 passed, 39 skipped in 7.43s (0 FAILED)`.
- **Thông số máy:**
  - CPU: Intel64 Family 6 Model 140 Stepping 1, GenuineIntel
  - OS: Windows 11 (10.0.22631)
  - Python: 3.12.7
  - Git SHA: commit chuẩn tác giả `MTrang0702`

## 09 · Limitations & ethics

- **Rủi ro pháp lý / PII:**
  Dữ liệu synthetic hoàn toàn miễn nhiễm với rủi ro PII (không có người và biển số thật). Tuy nhiên, nếu chuyển giao pipeline sang dữ liệu camera hành trình thực tế, bắt buộc phải tích hợp bước làm mờ khuôn mặt và biển số xe (tương tự Challenge T07) trước khi đưa ảnh vào hàng đợi kiểm duyệt để bảo vệ quyền riêng tư người đi đường theo GDPR và Nghị định 13/2023/NĐ-CP.
- **Thiên kiến ánh sáng (Bias):**
  Các thuật toán lọc ảnh thô sơ thường có xu hướng phân biệt đối xử với ảnh ban đêm hoặc thời tiết xấu (coi ảnh tối là ảnh hỏng). PoC đã giải quyết bằng cách áp dụng ngưỡng tương thích theo điều kiện môi trường (`light == night`), ngăn chặn việc xóa bỏ các dữ liệu góc hiểm (edge cases) quý giá.
- **Cam kết đạo đức AI:**
  Không tuyên bố "đạt chuẩn an toàn dữ liệu tuyệt đối" chỉ bằng các chỉ số tự động. Luôn duy trì con người trong vòng lặp (Human-in-the-loop) với vai trò giám sát và chịu trách nhiệm pháp lý cuối cùng (`owner`).

## 10 · Team contribution

**Bảng 2 · Individual contribution evidence**

| Học viên | Git author / email | Module / vai trò | Commit SHA / diff chứng minh | Trình bày? |
|---|---|---|---|:---:|
| Nguyễn Thị Minh Trang (MSSV: 2A202603107) | MTrang0702 <nguyenmtrang7203@gmail.com> | Solo Lead / End-to-End Pipeline, QA, Metrics & Report | Toàn bộ commits trên repo; `src/pipeline.py`, `src/baseline.py`, `tests/test_t02_pipeline.py`, `reports/` | Có (100%) |

## 11 · References

| URL | Ngày xem | 1–2 dòng ý nghĩa |
|---|---|---|
| https://ieeexplore.ieee.org/document/906038 | 2026-11-14 | Nghiên cứu thuật toán đo độ sắc nét hình ảnh dựa trên phương sai toán tử Laplacian (Pech-Pacheco et al., 2000). |
| https://ieeexplore.ieee.org/document/1284395 | 2026-11-14 | Phương pháp đo lường mù nhiễu khối JPEG dựa trên độ gián đoạn gradient ranh giới lưới $8\times 8$ (Wang et al., 2004). |
| https://www.iso.org/standard/81615.html | 2026-11-14 | Tiêu chuẩn quốc tế ISO/IEC TR 5259-6:2026 về kiểm soát chất lượng dữ liệu trong các hệ thống trí tuệ nhân tạo. |

---

**Bảng 3 · Checklist chốt khi nộp**

- [x] Link repo và tag cuối cùng trong README; input mẫu không chứa PII thật.
- [x] Đúng 1 lệnh run, 1 lệnh evaluate, 1 lệnh tests; không cần download khi chạy.
- [x] Có baseline/PoC metrics, 2 failure cases, reviewer evidence, decision log.
- [x] Có license/source provenance, data splits, seed, offline environment.
- [x] Tác giả commit rõ ràng, minh bạch khớp với thông tin học viên.
