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

## 7. Cổng kiểm chứng (verify gate, B7): A/B thật

Cơ chế: khi Tech Lead (lead cao nhất) định kết thúc lượt, engine chạy lệnh kiểm chứng trong workspace dự án (`team.verify_command` trong YAML, hoặc tự dò `npm test`, pytest, `make test`; timeout 180 s, cây tiến trình đăng ký và bị kill khi quá hạn, output cắt 3000 ký tự). Nếu đỏ hoặc quá hạn, kết quả thật được trả về cho lead và lead được gọi lại, tối đa 2 vòng. Hết timeout không bao giờ coi là đạt. Cờ `AGENTDEV_VERIFY_GATE`, mặc định TẮT. Chi tiết: `docs/adr/0004-verify-gate.md`.

Thiết lập: `bugfix_team`, Haiku, 3 nhiệm vụ a,b,c x 3 lần mỗi nhánh, xen kẽ OFF/ON, tổng 18 lượt (trần 18), không cổng trả phí. File thô: `bench-projects-20261105-162612` đến `-170039` (`.json` và `.md`).

| Chỉ số (trung bình mỗi lượt, n = 9) | OFF | ON |
|---|---|---|
| Thành công | 7/9 | 5/9 |
| a (bug, test đỏ) | 2/3 | 2/3 |
| b (tính năng, test xanh) | 2/3 | 2/3 |
| c (đổi tên) | 3/3 | 1/3 |
| Lượt lead chạy một mình (`nodes_run = ['Tech Lead']`) | 1 (b) | 2 (a, b) |
| Thời gian | 122 s | 112 s |
| Lời gọi model | 15,2 | 11,6 |
| Token vào / ra | 264k / 16,4k | 174k / 12,3k |
| Chi phí (tổng) | 0,166 USD | 0,118 USD |

Chi tiêu thật của A/B: 0,284 USD, 18 lượt, toàn bộ cost đã biết.

Kết luận trung thực: ON không tốt hơn (5/9 so với 7/9). Với n = 9 mỗi nhánh, chênh lệch nằm trong nhiễu (c 1/3 so với 3/3 là các lỗi đổi tên còn sót, không liên quan tới cổng vì repo xanh nên cổng không chạy lệnh nào khác). Điểm đáng nói: ở ON lượt a đầu tiên, cổng chạy 2 vòng (3 lời gọi) nhưng Tech Lead vẫn không giao việc và kết thúc với test đỏ; nhiệm vụ b (repo xanh) cổng không có tác dụng theo thiết kế. Ở nhánh OFF lần này, kiểu lỗi "lead chạy một mình" ở nhiệm vụ a không xuất hiện (0/3), nên không có mẫu đủ để chứng minh cổng sửa được nó. Quyết định: **giữ cờ TẮT mặc định**, không chỉnh để thắng. Giả thuyết cần kiểm tra tiếp: lead dừng ở bước kế hoạch/xin duyệt (plan gate) chứ không phải do quên giao việc, khi đó cổng kiểm chứng không phải thuốc đúng; cần ghi lại câu trả lời cuối của lead trong bench để phân biệt.

## 8. Giao diện: cửa sổ render tin nhắn, bước bỏ qua, tab hàng loạt, a11y 375px

| Chỉ số (phiên 1000 tin, e2e/perf.spec.js) | Trước | Sau |
|---|---|---|
| DOM khi mở phiên (cửa sổ mặc định) | 3357 node, 160 tin | 2655 node, 120 tin |
| DOM khi bấm "Hiện tin cũ" hết cỡ | 18054 node, 1000 tin (7 lần bấm) | 4242 node, 180 tin (15 lần bấm) |
| Ngân sách kiểm trong test | chỉ báo cáo | `expanded < 5000` và có nút "Hiện tin mới hơn" |

- Thiết kế: `utils/messageWindow.js` (logic thuần, có Vitest). Cửa sổ `{start, end}` tối đa 180 tin; kéo lên đọc cũ thì tin mới nhất bị gỡ khỏi DOM, hiện nút "Hiện N tin mới hơn" và nút nhảy tới tin mới nhất. Giữ nguyên `updateMessage`, tự cuộn khi stream (chỉ khi `end = null`), vị trí cuộn được neo theo tin đầu khung nhìn.
- Bước không chạy khi run hoàn tất có trạng thái riêng `skipped` (`STEP_STATUS`, i18n vi/en/zh, có icon gạch ngang và chữ, không chỉ màu). Không đổi backend, chỉ dựa tracker.
- A8-6: "Lượt gọi model" chỉ đếm lượt chạy có gọi model (`modelCallStats`); trước đó audit đã bác bỏ phần đếm sai, chỉ chỉnh số lượt kèm theo.
- Chạy hàng loạt là tab trong Phòng thí nghiệm (`/lab?tab=batch`, `LabWorkbench.vue`); `/batch-run` chuyển hướng vào tab; bỏ nút liên kết trùng trong Lab.
- 375px: mọi điều khiển >= 44px (đo lại: 0 phần tử nhỏ hơn), vùng aria-live của trạng thái đầu trang và gợi ý composer luôn có trong DOM, vòng focus cho ô tìm phiên, tay kéo panel và mục chọn chế độ. Tiêu đề 9px không tái hiện (đã bác bỏ ở A8); tương phản màu chỉ kiểm bằng a11y.spec.js (axe), không đo thêm.
