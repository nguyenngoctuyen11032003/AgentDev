# Báo cáo vòng cuối (release/hardening, đã merge vào main)

## 1. Phát hiện chính

| id | khu vực | mức | trạng thái | xử lý | test |
|---|---|---|---|---|---|
| A3-01 / A10-04 | Kết nối, hộp thoại | P1 | CONFIRMED (Playwright) | đã sửa: token `--z-confirm` | `connectionsLogic.test.js`, e2e |
| A3-02 | Kết nối | P1 | CONFIRMED | đã sửa: `authType` | `connectionsLogic.test.js` |
| A3-03 | Kết nối | P1 | CONFIRMED-CODE | đã sửa: lỗi tải có thử lại | e2e connections |
| A3-04 | Kết nối | P1 | CONFIRMED-CODE | đã sửa: popup bị chặn, hủy, timeout | `connectionsLogic.test.js` |
| A4-1/2/3/4 | Kết nối backend | P1→P3/P2 | CONFIRMED | đã sửa (đổi hành vi theo quyết định 3, 4) | `test_connection_autobind.py`, `test_connections*.py` |
| A5-01 | Skill | P1 | CONFIRMED (test đỏ) | đã sửa: copy vào thư mục tạm | `test_skill_library.py` |
| A5-02 | Skill | P2 | CONFIRMED-CODE | đã sửa: `latestOnly` | `skillPickerLogic.test.js` |
| A6-01 | Cài đặt | P1 | CONFIRMED-CODE | đã sửa: gỡ công tắc chết | `shellStructure.test.js` |
| A7-1/2/3 | Quy trình | P2/P1 | CONFIRMED-CODE | đã sửa | `useWorkflowLoadGuards.test.js` |
| A9-1 | Lab | P1 | CONFIRMED | đã sửa: một job mỗi quy trình | `test_lab_hardening.py` |
| A1-01..08, A2-01 | Khung app, Batch Run, Trang chủ | P2 | CONFIRMED | đã sửa | `batchRunStatus.test.js`, `shellStructure.test.js` |
| A2-03/04 | Hướng dẫn | P2 | CONFIRMED | đã sửa vi/en/zh | `tutorialContent.test.js` |
| A10 | Tương phản chữ mờ | P2 | CONFIRMED (đo) | đã sửa | `tokens.contrast.test.js` |

Chi tiết từng agent: `docs/audit/findings/`.

## 2. Số liệu

| Chỉ số | Trước (vòng 2) | Sau |
|---|---|---|
| pytest | 1.663 pass | 1.726 pass, 17 skip |
| vitest | 73 | 139 |
| e2e | 13 | 115 (8 trang x 4 độ rộng x sáng/tối, 64 ảnh); 110 xanh lúc chạy đầu, 4 lỗi đã sửa và chạy lại phần liên quan |
| Repo map (repo 1.631 file) | 1.939 ký tự (cây cũ) | 669 ký tự |
| Baseline UI | không có | `perf-baseline.md` (JS `/launch` 1,2 MB; 18k DOM khi mở hết 1.000 tin; canvas 200 node 22–36 fps) |

Số UI sau sửa chưa đo lại (chưa chạy lại `npm run perf` sau đợt sửa).

## 3. bench_projects (bugfix_team, Haiku, model thật)

| Lần | a (bug) | b (tính năng) | c (đổi tên) | Chi phí |
|---|---|---|---|---|
| 1 (`bench-projects-20261105-154853`) | fail | fail | fail | 0,019 USD |
| chẩn đoán (2 lượt đơn) | ok | ok | - | 0,032 USD |
| 2 (`bench-projects-20261105-160400`) | fail (1 lời gọi, 18 s) | ok (15 lời gọi, 112 s) | ok (14 lời gọi, 136 s) | 0,036 USD |

Kết luận: hạ tầng đúng (không file hỏng, không sửa ngoài phạm vi). Tỷ lệ thành công không ổn định (khoảng 4/8 lượt). Kiểu thất bại lặp lại: **Tech Lead chạy một mình rồi kết thúc, không giao việc cho Bug Fixer** (`nodes_run = ['Tech Lead']`). Đây là hành vi engine/prompt, chưa sửa. Hướng sửa nhỏ nhất: cổng kiểm chứng (mục B7 của kế hoạch) từ chối kết thúc khi chưa có file nào đổi và test còn đỏ. n quá nhỏ để kết luận về thời gian và token.

Tổng chi tiêu model thật cả vòng: khoảng 0,09 USD (trần: 30 lượt, 5 USD).

## 4. ADR và cờ

- 0001 process registry — `AGENTDEV_PROCESS_REGISTRY` (bật)
- 0001 edit_file/multi_edit — `AGENTDEV_EDIT_TOOLS` (bật)
- 0002 search ripgrep — `AGENTDEV_SEARCH_RG` (bật)
- 0003 repo map — `AGENTDEV_REPO_MAP` (bật, chỉ khi nhỏ hơn cây cũ)

## 5. Chưa làm (backlog)

Resume phiên native, bỏ cold-start provider, checkpoint git/hoàn tác, node `verify`, song song theo phụ thuộc, báo cáo thành viên có cấu trúc, ảo hóa danh sách tin nhắn trang Chạy, Batch Run thành tab trong Lab, `@axe-core/playwright` (chờ duyệt), `/code-review` và `/security-review` toàn nhánh, đo lại hiệu năng UI. Mỗi mục engine phải đo bằng `bench_projects` với n lớn hơn (≥5 lượt/nhiệm vụ) vì baseline đang nhiễu.

## 6. Rủi ro còn lại

1. Baseline bench nhiễu, chưa đủ để chứng minh cải tiến engine.
2. Tech Lead kết thúc sớm không làm việc (xem mục 3).
3. Trang Chạy vẫn tạo ~18k node DOM khi mở hết lịch sử.
4. Đổi hành vi kết nối (ưu tiên cùng vendor, xóa tài khoản không đăng xuất CLI) khác hành vi cũ có test khóa; test đã sửa có chủ đích.
5. `storage/` chứa dữ liệu Lab cũ rất lớn, chưa dọn.
