# Rà soát vòng 2 (nhánh `audit/round-2`, chưa commit)

Trạng thái: toàn bộ thay đổi nằm trong working tree, chưa commit/push/merge, chờ duyệt.

## 1. Phát hiện

Chiều: ENG engine, LAB, API, SEC, COST, FE, UX, A11Y, TEST. "Bằng chứng": request thật, test đỏ, script, ảnh hoặc số đo.

| id | chiều | mức | kết quả phản biện | xử lý | test / bằng chứng |
|---|---|---|---|---|---|
| A5-1 | SEC | P0 | CONFIRMED (request từ IP LAN trả 200) | đã sửa: bind `127.0.0.1`, compose publish `127.0.0.1` | `test_local_security.py` |
| A5-2 | SEC | P0 | CONFIRMED (Host+Origin `evil.com` qua guard) | đã sửa: kiểm Host, bỏ nhánh `origin==host` | `test_local_security.py` |
| A5-3 | SEC | P1 | CONFIRMED | đã sửa: `/ws` kiểm Origin và Host | `test_local_security.py` |
| A5-4 | SEC | P1 | CONFIRMED (CORS `*` đọc được `/api/sessions`) | đã sửa: bỏ `*`, dùng allowlist loopback | `test_local_security.py` |
| A5-7 | SEC | P2 | CONFIRMED (D2: access log uvicorn lộ `code`/`state`) | đã sửa: filter che query, mở rộng danh sách tên | `test_local_security.py` |
| D2-3 | SEC | P2 | CONFIRMED (`Host: localhost:6497@evil.com`, nhiều Host) | đã sửa: regex Host chặt, từ chối >1 Host | `test_local_security.py` |
| A2-1 | ENG | P1 | CONFIRMED (E1 thắng dù E2 chạy sau); user duyệt đổi | đã sửa: end node chạy xong sau cùng thắng + lint `MULTIPLE_END_NODES` | `test_multi_end_nodes.py` |
| A2-2 | ENG | P1 | CONFIRMED một phần (bypass không có `paid` guard; chưa khai thác được) | đã sửa: `paid:true` không bao giờ tự duyệt mọi chế độ | `test_paid_gate_bypass.py` (30) |
| A10-1 | TEST | P2 | CONFIRMED (đột biến nối " OK" sống sót) | đã sửa: test tham số hóa trên regex cổng thật | `test_paid_gate_bypass.py` |
| A3-1 | LAB | P1 | CONFIRMED (test đỏ) | đã sửa: mục Evidence ≤1500 ký tự; D1 tìm thêm lỗi mất dòng pass cuối, đã sửa | `test_lab_round2.py` |
| A3-2 | LAB | P1 | CONFIRMED (test đỏ) | đã sửa: manifest bỏ `node_modules`/`.git`/lockfile lớn | `test_lab_round2.py` |
| A3-3 | LAB | P1 | CONFIRMED một phần | đã sửa: temperature=0 (chỉ Gemini), `escalated_from` | `test_lab_round2.py` |
| A3-4 | LAB | P1 | CONFIRMED (test đỏ) | đã sửa: run lỗi/hết giờ/hủy giữ token+cost+giây; chấm lại cộng dồn | `test_lab_round2.py` |
| A3-5 | LAB | P1 | CONFIRMED một phần | đã sửa: cờ `cost_known`/`cost_partial` một quy tắc, `max_tokens` vào `run_limits` | `test_lab_round2.py` |
| A3-7 | LAB | P1 | CONFIRMED (nặng hơn mô tả) | đã sửa: subgraph dùng chung kênh cổng, cancel, tracker (`ScopedTokenTracker`); D1 tìm lỗi trùng tên node, đã sửa | `test_lab_round2.py`, `test_subgraph_tracker.py` |
| D2-5 | LAB | P2 | CONFIRMED (prompt-injection qua Evidence) | đã sửa: khối `<evidence untrusted>`, che bí mật | `test_lab_round2.py` |
| A8-3 | UX | P1 | CONFIRMED (script: tài khoản không tồn tại vẫn PASS) | đã sửa: FAIL kèm mã `unknown_connection` | `test_lab_round2.py` |
| A6-4 | COST | P1 | CONFIRMED (CLI giả: 5800 token ghi 0) | đã sửa: ghi usage trước khi raise, partial usage khi timeout | `test_usage_on_error.py` |
| A6-3 | COST | P1 | CONFIRMED (tiền tố chung 9%) | đã sửa một phần: 9,3% → 44,1% (nhẹ) | `test_conversation_turns.py`, bench |
| A6-1 | COST | P2 | CONFIRMED một phần | đã sửa phần thừa: catalog 695 → 435 ký tự | `test_agent_skill_prompt.py` |
| A8-1 | UX | P1 | CONFIRMED (ảnh) | đã sửa: bỏ ép 100%, "Hoàn thành, N bước lỗi"; tiến độ chỉ tính bước đã chạy | `runProgress.test.js`, `e2e/run.spec.js` |
| A4-1 | API | P1 | CONFIRMED (`curl` + `node`) | đã sửa | `client.test.js` |
| A9-1 | A11Y | P1 | CONFIRMED (31/40 lần Tab ra ngoài) | đã sửa: `SettingsModal` dùng `BaseDialog` | `e2e/a11y.spec.js` |
| A9-2 | A11Y | P1 | CONFIRMED | đã sửa: nhãn + 44×44; gắn lại khi đổi tab | `e2e/a11y.spec.js` |
| A2-3 | ENG | P2 | UNCERTAIN → REFUTED một phần | backlog | — |
| A1-* | REG | P2 | SUSPECTED | backlog (merge `27adf4b` không mất logic) | 121 test pass |
| còn lại P2 | — | P2 | SUSPECTED/CONFIRMED | backlog | `docs/audit/backlog.md` |

Mục "còn mở" từ vòng trước: "xóa đích trước khi move" không tái hiện (REFUTED); "video_studio không có tool render" đúng nhưng có chủ ý; "giám khảo không thấy output tool", "run lỗi mất số giây/token", "chi phí báo thiếu khi native lỗi", "web.py DNS-rebinding", "node đầu thắng" đều CONFIRMED và đã sửa; "UI chưa có trạng thái skipped" còn mở (A8-2, backlog).

## 2. Số liệu trước/sau

| Chỉ số | Baseline (`main`) | Hiện tại |
|---|---|---|
| pytest | 1557 pass, 12 skip | 1663 pass, 12 skip |
| vitest | 66 pass | 73 pass |
| E2E (mới) | không có | 13/13 xanh (3 màn × 375/1024/1440 + run + a11y) |
| Bundle JS (tổng byte) | 1.697.882 | 1.698.311 (+429) |
| Tiền tố chung giữa các lượt (cache), tải nhẹ / vừa | 9,3% / 8,2% | 44,1% / 31,3% (tải nặng không đổi 13,5%; lượt "ok" gần như không đổi) |
| Catalog tool skill mỗi lần gọi | 695 ký tự | 435 ký tự |
| Usage khi CLI lỗi (CLI giả) | 0 token | 5.800 token |
| Job Lab mẫu (2 kịch bản × 1 lặp, Haiku + giám khảo Sonnet) | 2 run + 2 giám khảo, 3.008 + 5.514 token, 0,0008 + 0,02375 USD, 9,4 s | 2 + 2, 3.018 + 5.593 token, 0,0006 + 0,02399 USD, 8,4 s |
| Heap sau 1.120 tin (đo A7, trước sửa) | 20 MB (160 DOM) | không đo lại (không đụng LaunchView) |
| Thời gian tải 3 màn (bản build, A7, LCP) | Chạy 1.024 ms, Lab 300 ms, Quy trình 456 ms | không đo lại |

Chi tiêu model thật vòng này: 2 job Lab, 4 lời gọi giám khảo, khoảng 0,049 USD (trần 40 run và 60 lời gọi). Chi tiết: `docs/audit/lab-baseline-round2.md`, `docs/audit/token-savings-round2.md`.
Mẫu job Lab chỉ n=2, chênh giây và USD nằm trong nhiễu. Hai chỉ số cuối cùng chưa đo lại.

## 3. Ảnh Playwright
- Trước/sau A8-1: `D:\Code\Tuyen\AgentDev\frontend\e2e\artifacts\round2\before.png`, `D:\Code\Tuyen\AgentDev\frontend\e2e\artifacts\round2\after.png`.
- Smoke 3 màn × 3 độ rộng: `D:\Code\Tuyen\AgentDev\frontend\e2e\artifacts\round2-final\`.
- Ảnh khảo sát A8: `C:\Users\TUYEN\AppData\Local\Temp\claude\24849d705c77c59c\1e602c28-7f81-458e-b0a8-bc34659b52b3\scratchpad\a8\`; ảnh A9 (5 độ rộng × sáng/tối) ở `...\scratchpad\shots\`.

## 4. Hạ tầng mới
- `CLAUDE.md`: agent mới đọc là chạy được app và test (lệnh, bản đồ 3 màn, bất biến, quy ước, file lớn).
- `npm run e2e` (trong `frontend/`): dùng lại server đang chạy hoặc tự bật; cổng khác bằng `E2E_API=... E2E_WEB=... npm run e2e`.
- `uv run python -m scripts.bench_tokens --fake [--only ...] --out ../docs/audit/` (từ `backend/`); `--real` có `--max-runs`/`--max-usd`.
- `node scripts/check-i18n.mjs` (từ `frontend/`): đếm key lệch vi/en/zh và chuỗi viết cứng.
- Log `agentdev.run_summary`: mỗi lượt chạy node một dòng JSON.

## 5. Rủi ro và việc còn mở
1. `package-lock.json` đã đồng bộ lại sau khi thêm `@playwright/test` (nằm trong commit hạ tầng).
2. `phong_san_xuat_video.yaml` có 2 end node cùng chạy; kết quả cuối nay là "Đã bỏ qua bước tạo video…" thay vì "Đã lưu". Lint cảnh báo; nên đổi `end` của workflow này.
3. Lab chọn OpenAI làm giám khảo khi `connections.json` không có `default_connection`; cần đặt kết nối mặc định.
4. `WINDOW_STEP=2` trong `conversation_turns.py` làm một nửa số lượt mất một lượt lịch sử (đánh đổi có chủ ý để cache ổn định); CORS cho mọi `localhost:<cổng>` theo thiết kế.
5. Chưa dựng Docker thật; `A8-2` (trạng thái "skipped" riêng) và backlog P2 chưa xử lý; test `runProgress` và `SettingsModal` e2e chưa chạy ở trạng thái đỏ.

## 6. Đề xuất chia PR (không có Claude làm author/co-author)
1. `chore/audit-infra`: `CLAUDE.md`, `frontend/e2e/`, `bench_tokens.py` + test, `check-i18n.mjs`, `docs/audit/` (merge trước).
2. `fix/local-security`: A5-1..4, A5-7, D2-3, Docker/compose.
3. `fix/engine-gates`: A2-1 (+ lint), A2-2, A10-1, cập nhật `test_video_workflow_loops.py`.
4. `perf/token-usage`: A6-1, A6-3, A6-4, `run_summary`, `ScopedTokenTracker`/`cost_known` trong `token_tracker.py`.
5. `fix/lab-scoring`: A3-*, A8-3, subgraph, Evidence hardening (dùng `token_tracker.py` của PR 4).
6. `fix/ui-round2`: A4-1, A8-1, A9-1, A9-2, key i18n.
Thứ tự merge: 1 → 2 → 3 → 4 → 5 → 6.
