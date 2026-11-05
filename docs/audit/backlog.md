# Backlog vòng 2 (CONFIRMED hoặc còn nghi, chưa sửa trong vòng này)

Nguồn: Pha A (A1-A10) + Pha B (phản biện B1-B5). Chiều: ENG engine, LAB, API, SEC, COST, FE, UX, A11Y, TEST.

| id | mức | trạng thái | file:line | mô tả ngắn |
|---|---|---|---|---|
| A2-3 | P2 | UNCERTAIN→tối ưu | workflow/executor/parallel_executor.py:27-141 | Node song song đã chạy không bị dừng khi anh em lỗi (không ngắt được lời gọi model giữa chừng; chỉ node chưa bắt đầu được chặn đúng) |
| A6-1 | P2 | CONFIRMED một phần | executor/agent_executor.py:627-646, skills/manager.py:250 | Catalog tool skill gửi lại mỗi node; chỉ phần "skill đã preload hết nhưng còn file phụ" là thừa (~1-1,5k ký tự/node) |
| A6-5 | P2 | SUSPECTED | agent_executor.py:505 | `max_tokens` trong YAML không có tác dụng với CLI |
| A6-6 | P2 | UNCERTAIN | autobind.py:161-170 | Node không gán model → model đắt nhất; template hiện không bị |
| A6-7 | P2 | SUSPECTED | team.py:1389-1430 | MEMBER_PROTOCOL (1,2k ký tự) nằm trong brief, không vào system/cache |
| A8-2 | P2 | SUSPECTED | utils/runTracker.js:369 | Bước bị bỏ qua chưa có trạng thái "skipped" riêng trên UI |
| A8-4 | P2 | CONFIRMED (code) | LabView.vue:688 | Lab không có nút sang trang Chạy |
| A8-5 | P2 | CONFIRMED (code) | locales vi.json lab.checks | Lỗi kiểm cấu hình chỉ chữ, không link sửa |
| A8-6 | P2 | CONFIRMED (ảnh) | DashboardView.vue ~383 | "Lượt gọi model" đếm cả bước literal/human là agent |
| A9-3/4 | P2 | CONFIRMED (đo) | LaunchView.vue, Sidebar.vue | ≤375px: tiêu đề "Chạy" 9px, nhiều điều khiển <44px |
| A9-5 | P2 | CONFIRMED | LabRunPreview.vue:132-134 + 15 chỗ | 16 chuỗi viết cứng thật |
| A9-6 | P2 | CONFIRMED (đo) | main.css --text-muted-* | Tương phản 4,17-4,43 trên surface-2 tối |
| A9-7/8/9 | P2 | SUSPECTED | LaunchView.vue:174 ... | aria-live bị v-if; outline:none; chồng lấn 768px |
| A7-1..4 | P2 | CONFIRMED (đo) | LaunchView.vue:272,1134 | Mở hết lịch sử → 23k DOM; vueflow nạp tĩnh; CSS 172KB; >200 node giật |
| A5-5 | P2 | SUSPECTED | skill_library.py:244-246 | rmtree đích trước copytree (mất cả 2 nếu copy lỗi) |
| A5-6 | P2 | SUSPECTED | app_preview.py:340-395 | Preview Node/script chỉ dựa env HOST, có thể bind mọi giao diện |
| A5-7 | P2 | SUSPECTED | utils/middleware.py | log_request ghi query OAuth (code/state) |
| A1-1/2/3 | P2 | SUSPECTED | workflow_assistant_prompt.py; lab_outputs.py:698; workflow_lab.py:737 | Test diff bị xóa không thay thế; _remove_tree nuốt OSError; nhánh `basic` có thể chết |
| A4-2..6 | P2 | SUSPECTED | client.js:127,1105 ... | fetch thô openLocalProjectFile; 409/500 chỉ chuỗi chung; endpoint không ai gọi |
| A10-2/3 | P3 | CONFIRMED | test_workflow_lab.py ... | Nhánh trọng yếu chỉ 1 test; 5 test chỉ kiểm mock |
| A3-8/9/10 | P2 | SUSPECTED | workflow_lab.py:511,1497,routes/lab.py:72 | Chi phí TB lệch do run lỗi; 2 job Lab cùng lúc |
