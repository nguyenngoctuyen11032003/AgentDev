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

## 9. Lead dừng sớm: bản sửa tool native (`AGENTDEV_NATIVE_TOOL_RESCUE`)

Nguyên nhân (bằng chứng ở `findings/lead-early-stop.md`): Haiku gọi `delegate_parallel` như tool native của Claude CLI, CLI chạy `--tools ""` trả "No such tool available", Haiku thử lại rồi trả text thuần; engine không thấy `tool_calls` nên coi đó là câu trả lời cuối. Bản sửa chuyển tool_use native trùng tên tool của host thành tool call (không bao giờ chuyển built-in như Bash).

A/B thật, `bugfix_team`, Haiku, chỉ task a, xen kẽ, n = 8 mỗi bên (dữ liệu thô `docs/audit/ab-rescue/`):

| | Cờ tắt | Cờ bật |
|---|---|---|
| Thành công | 7/8 | 8/8 |
| Lead chạy một mình | 1 | 0 |
| Thời gian TB | 104 s | 138 s |
| Lời gọi model TB | 14 | 19,9 |
| Chi phí | 0,114 USD | 0,157 USD |

Quyết định: **cờ vẫn TẮT mặc định.** Hướng có lợi nhưng n = 8 chưa đủ để gọi là rõ rệt (chênh 1 lượt), và lượt lỗi duy nhất của nhánh tắt lần này không mang dấu hiệu "No such tool" (lead nói chưa điều tra, không sửa gì). Bật làm tăng thời gian và chi phí do lead làm đủ việc hơn. Cần n ≥ 20 mỗi bên trên cả 3 nhiệm vụ để kết luận. Chưa kiểm Codex.

Chi tiêu thật mục 9: khoảng 0,27 USD cho 16 lượt. Tổng cả vòng khoảng 0,65 USD và khoảng 46 lượt, vượt trần 30 lượt theo duyệt của người dùng (A/B verify gate, A/B này).

## 10. Đo lại hiệu năng UI sau các đợt sửa (`npm run perf`, lần chạy thứ 9 trong `perf-baseline.md`)

| Chỉ số | Baseline (lần 1-2) | Sau sửa |
|---|---|---|
| DOM khi mở phiên 1.000 tin (cửa sổ mặc định) | 3.357 node | 2.656 node |
| DOM sau khi bấm "Hiện tin cũ" hết cỡ | 18.054 node | 4.242 node (đo ở mục 8) |
| FPS kéo canvas 200 node | 22,6 và 36,5 | 44,2 (không còn frame >50 ms ở lần này; vẫn nhiễu theo máy) |
| Heap sau 16 lần chuyển trang | 2,7 → 7,8 MB (x1,09–1,10 cùng trang) | 2,72 → 7,84 MB (x1,1), không có dấu hiệu rò rỉ |
| JS thô `/launch` | 1.197 KB | 1.207 KB (+0,8%, do cửa sổ tin nhắn và trạng thái mới) |
| JS thô `/workflows/:name` | 1.027 KB | 1.038 KB |
| LCP các trang | 100–772 ms | cùng khoảng, `/launch` 500–772 ms (dao động theo máy) |

Kết luận: DOM phiên dài và FPS canvas cải thiện rõ; bundle `/launch` và `/workflows/:name` vẫn trên 1 MB JS (chưa tách chunk, lazy-load VueFlow đã bỏ qua vì chưa chứng minh lợi); heap ổn định. Mỗi cột "lần chạy" cộng dồn nên bảng `perf-baseline.md` có nhiều lần đo cạnh nhau.

## 11. Phase B (mục 8, 6, 10): đọc song song, báo cáo có cấu trúc, backlog token

Ba thay đổi, mỗi thay đổi sau một cờ, có ADR (`docs/adr/0006`, `0007`, `0008`) và test đỏ trước. **Cả ba cờ vẫn TẮT mặc định** (xem lý do ở cuối).

| Cờ | Mặc định | Việc làm | Test |
|---|---|---|---|
| `AGENTDEV_PARALLEL_READS` (+ `_MAX`, mặc định 4) | tắt | các lời gọi tool chỉ-đọc liền nhau trong một lượt model (`search_in_files`, `read_file_segment`, `read_text_file_snippet`, `list_directory`, `describe_available_files`) chạy song song, kết quả giữ thứ tự, lỗi theo từng lời gọi, có hủy; ghi/shell/gate/paid/`load_file` không bao giờ song song | `test_parallel_reads.py` |
| `AGENTDEV_STRUCTURED_REPORT` | tắt | báo cáo thành viên -> lead cắt theo trường (Evidence file:line, Commands + kết quả, Files changed, Open) trong cùng trần 2000 ký tự; kết quả tool cũ giữ đầu + đuôi + dòng lỗi | `test_structured_report.py` |
| `AGENTDEV_CLI_MAX_OUTPUT` | tắt | `params.max_tokens` thành env `CLAUDE_CODE_MAX_OUTPUT_TOKENS` cho Claude CLI (>= 1000, tối đa 64000); Codex không có tương đương nên vẫn bị bỏ qua | `test_cli_max_output.py` |
| `AGENTDEV_MEMBER_PROTOCOL_SYSTEM` | tắt | `MEMBER_PROTOCOL` chuyển từ đầu brief sang system prompt của thành viên thường (phần cache được) | `test_member_protocol_system.py` |

Số liệu (model giả, đo được):

| Phép đo | Cờ tắt | Cờ bật |
|---|---|---|
| 4 lời gọi đọc, mỗi lời 0,25 s (wall) | 1,01 s (peak 1) | 0,26 s (peak 4) |
| Báo cáo 11.267 ký tự: số dòng evidence còn lại (6 dòng) | 0/6 (2033 ký tự) | 6/6 (1868 ký tự) |
| Kết quả tool cũ 6k ký tự, dòng ERROR ở giữa | mất (1500 ký tự) | còn, đuôi còn (1109 ký tự) |
| Brief của thành viên (ký tự) | 1242 | 39 (+1230 sang system) |
| Phần cache được của một lượt thành viên (ước tính, system nền 2500) | 66,8% | 99,0% |
| `bench_engine` (chain/fanout/diamond efficiency) | 0,98 / 0,97 / 0,98 | không đổi (không có lô tool) |
| `bench_tokens --fake` team (Plan 11068, Worker 11479, Merge 12605 ký tự) | - | không đổi (không có ủy quyền) |

A6-1 (catalog skill) đã xong từ vòng 2, không còn gì. A6-5: một lời gọi Haiku thật xác nhận env var có tác dụng (trần 60 cho đúng 60 token ra). Lịch ủy quyền theo phụ thuộc: không làm, `software_company.yaml` đã mã hóa phụ thuộc thành các batch và `max_parallel` = 4 giữ nguyên.

A/B thật `bugfix_team`, Haiku, task a, xen kẽ, n = 4 mỗi bên, bật cả ba cờ (PARALLEL_READS, STRUCTURED_REPORT, MEMBER_PROTOCOL_SYSTEM; CLI_MAX_OUTPUT không bật):

| | Tắt | Bật |
|---|---|---|
| Thành công | 3/4 | 2/4 |
| Lời gọi model TB | 12,8 | 11,5 |
| Chi phí TB | 0,0132 USD | 0,0112 USD |

n = 4 không đủ kết luận (lượt hỏng của nhánh tắt là lỗi lead dừng sớm đã biết ở mục 9; hai lượt hỏng nhánh bật chưa điều tra nguyên nhân). Quyết định: **giữ cả bốn cờ TẮT** cho tới khi có A/B n >= 20 mỗi bên; `PARALLEL_READS` là ứng viên bật đầu tiên (đã chứng minh bằng test, rủi ro thấp nhất). Chi tiêu thật mục 11: khoảng 0,22 USD, 9 lượt (1 lời gọi kiểm env var 0,127 USD do chạy ở thư mục có ngữ cảnh lớn + 8 lượt A/B 0,095 USD), dưới trần 24 lượt / 1,0 USD. Test backend đầy đủ: 1804 passed, 18 skipped.

## 13. Giảm JS theo route (`npm run perf`, lần 10 = trước, lần 13 = sau)

Cách làm: (1) locale `en` chỉ là dự phòng, không tải lúc khởi động nữa mà tải một lần khi gặp khóa thiếu (`missing` trong `src/i18n/index.js`, test `lazyFallback.test.js`; `check-i18n` bảo đảm vi/en/zh không lệch); (2) `components/common/lazyPanel.js`: import động có trạng thái đang tải, lỗi kèm nút "Thử lại" (khóa `common.lazy.*`, vi/en/zh) cho KanbanView, DashboardView, ReviewView, ProductsView, SettingsModal, LocalFolderPicker (Chạy), FormGenerator, DepartmentTemplatePicker, WorkflowAssistantPanel (Quy trình); (3) tab Đồ thị của Chạy chỉ nạp WorkflowNode/Edge/StartNode/Background khi mở tab lần đầu (có trạng thái tải/lỗi/thử lại). Không đổi `updateMessage`, `RUN_STATUS`; `manualChunks` giữ nguyên (vendor đã tách).

| Route | JS thô trước | JS thô sau | Truyền trước | Truyền sau | CSS thô trước -> sau | LCP (lần cuối) trước -> sau |
|---|---|---|---|---|---|---|
| `/` | 499,9 KB | 358,0 KB | 171,0 | 122,1 | 39,2 -> 39,8 | 492 -> 460 ms |
| `/tutorial` | 605,6 KB | 463,7 KB | 217,0 | 168,1 | 37,1 -> 37,7 | 140 -> 104 ms |
| `/workflows/:name` | 1.042,8 KB | 691,1 KB | 357,9 | 236,9 | 134,9 -> 76,3 | 628 -> 824 ms (dao động 476-824 ở các lần trước) |
| `/launch` | 1.220,8 KB | 924,9 KB | 414,8 | 319,3 | 238,7 -> 152,4 | 832 -> 632 ms |
| `/lab` | 779,2 KB | 637,5 KB | 276,1 | 228,3 | 77,7 -> 78,3 | 412 -> 300 ms |
| `/settings/*` | 500,9-555,5 KB | 358,9-413,5 KB | 172,9-189,4 | 124,0-140,9 | không đổi đáng kể | cùng khoảng |
| `/lab?tab=batch` | 803,8 KB | 662,1 KB | 285,0 | 237,2 | 91,6 -> 92,2 | 180 -> 196 ms |

Kết quả: mọi route dưới 700 KB JS thô trừ `/launch` (925 KB, giảm 24%). `/launch` còn: LaunchView 234, vi 176, vue-flow 160, markdown-it 107, vue 104, i18n 53, yaml 39 KB; hết đường lui an toàn vì vue-flow store (`useVueFlow`) nằm trong script 6k dòng, markdown-it được gọi đồng bộ trong chat, OfficeView phải gắn từ đầu để nhận sự kiện. Việc kế tiếp nếu cần: tách đồ thị ra component riêng, hoặc tách locale theo namespace. LCP dao động theo máy (workflow 476-824 ms trong cả lịch sử), không thấy hồi quy rõ. Kiểm tra: `npm test` 167 pass, lint sạch, build ok, check-i18n ok, e2e `--grep-invert perf` 151 pass / 1 skipped (gồm 48 ảnh chụp thị giác, không đổi ảnh nào), `e2e:axe` 32 pass.
