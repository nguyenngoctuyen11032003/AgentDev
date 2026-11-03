# Workflow assistant: real-model verification (Task 8)

Date: 2026-11-04. The test drove the real UI at `/workflows` with Playwright (headless Chrome). It used real
CLI connections: Claude (`claude-opus-5-5`, anthropic CLI) and Codex (`gpt-6.1-sol`, openai CLI). Messages
were sent in Vietnamese. Each turn's raw `/api/workflow-assistant/chat` response was captured in the page,
which gave `checks.status`, `diff_summary` and `warnings`. Screenshots are `t8-*.png` in the gitignored
`.superpowers/sdd/2026-11-03-workflow-assistant-chat/shots/` folder.

Scenarios (from the plan):
- (a) "Tạo phòng chăm sóc khách hàng: trưởng nhóm tiếp nhận, 1 người tra cứu đơn hàng, 1 người soạn trả lời"
- (b) "Dây chuyền viết bài: Viết → Biên tập; biên tập chưa đạt thì quay lại viết tối đa 3 lần; đạt thì chờ tôi duyệt rồi đăng"
- (c) "Giải thích quy trình software_company chạy thế nào"
- (d) "Thêm QA Tester kiểm tra sau Frontend Developer" (on a copy made with the UI's "Sao chép quy trình" action)

"Turns" counts user messages. A turn can include hidden repair calls.

## Claude (anthropic)

(in progress)

## Codex (openai)

(the Codex agent appends its rows here)
