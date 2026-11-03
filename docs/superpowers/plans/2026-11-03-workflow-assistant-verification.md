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

| Scenario | Turns | One question at a time? | Confirmed name? | checks.status | Opened on canvas? | Unrequested changes (d) | Notes |
|---|---|---|---|---|---|---|---|
| (a) run 1, before tuning | 3 | Yes. Q1: where does the order data live (file / API / pasted)? Q2: what may the reply promise? | No. The user said "cứ làm đi" in turn 3, so it proposed `customer_care.yaml` and listed that name as an assumption ("muốn tên khác cứ nói") | pass | Yes. `/workflows/customer_care`, lead plus 2 members, team links | n/a | Team with lead, `edges: []`, `max_parallel: 1`, a no-promise rule in the lead and the writer. Every node `description` was in **English** → fix 1 |
| (a) run 2, after tuning | 4 | Yes. Data source → approval before sending → name | **Yes.** It suggested `cham_soc_khach_hang.yaml`, saw `cham_soc_khach_hang_codex` in the file list, and asked "Bạn dùng tên này hay muốn đặt tên khác?" before proposing | pass | Yes | n/a | Descriptions in Vietnamese. Minor: the lead id came out as `Truong Nhom` (the reference says to keep ids in English) |
| (b) run 1, before tuning | 3 | Yes. Q1: what does "đăng" produce (no agent can post to a site)? Q2: the name | **Yes**, explicitly: "bạn có đồng ý đặt tên file là `article_pipeline.yaml` không?" | pass | Yes. 6 nodes, keyword branches, loop | n/a | Brief (passthrough, `keep_message`) → Writer → Editor (APPROVED / `none: [APPROVED]`) + `loop_counter` (3) wired per the reference → human → Publisher. `Writer → Owner Approval` with `trigger: false` sends the latest draft to the human. Loop message and human prompt in Vietnamese; descriptions in English |
| (b) run 2, after tuning | 2 | Yes. Asked about the "đăng" step and said it would confirm the name | Yes. It suggested `viet_bai_bien_tap`; the user confirmed it in the same message as "cứ làm đi" | pass | Yes | n/a | Same correct shape; every description in Vietnamese; the Editor is told to repeat the full article after APPROVED so the human sees it |
| (c) | 1 | n/a | n/a | n/a (no proposal) | n/a | n/a | A clear Vietnamese explanation in plain words, with no YAML: the CTO is the only contact, its 4 request types, the PM's default order (UI/UX → data/backend → FE → UI/UX review → QA → acceptance), where the user approves, and the limits (20/2, 25/3, 3 review rounds). It ended with 3 follow-up quick replies |
| (d) on `software_company_copy` | 2 | Yes. It noticed that QA Tester **already exists** and already follows Frontend in most paths, and asked which meaning was intended (right after FE, before the UI/UX review / mandatory / both) | n/a | warn (only the existing `code_execution` WARN, which the original file has too) | Yes. The canvas reloaded with 25 nodes and the Hoàn tác toast appeared | **None.** `diff_summary`: only `Project Manager.config.role`. The file diff is 2 lines in the PM's default-order sentence; comments, anchors and order are untouched | `proposal.warnings = ["Project Manager"]`, because the user never named PM. In a team workflow, the only way to change the order is through the coordinator's role, so this warning is noise (see concerns). It also flagged a follow-up gap: FE fixes after the UI/UX review are not re-tested |

Claude total: 15 user turns. Two more model calls came from the Codex agent's message landing in this
session (the scratchpad collision noted below); they were not counted. There were no quota errors.

## Codex (openai)

### Preliminary runs (made by the Claude-half agent before the split)

These ran through the same UI, before the coordinator split the vendors. They found three of the problems
fixed below.

| Scenario | Turns | One question at a time? | Confirmed name? | checks.status | Opened on canvas? | Unrequested changes (d) | Notes |
|---|---|---|---|---|---|---|---|
| (a) | 3 | Yes, short questions: name, then approval before sending | **Yes, as its first question** (`cham_soc_khach_hang`) | pass | Yes | n/a | Mixed shape: passthrough → team lead (2 members) → human approval (`DUYET` regex) that loops back to the lead → passthrough. Descriptions in Vietnamese even before fix 1 |
| (b) run 1 | 3 | Yes: name, then what happens after 3 failed rounds | Yes | pass | Yes | n/a | Used a `loop_counter`, but wrote **two edges `Editor → User Approval`**. The runtime keeps only the last one (`Node.add_successor` updates the existing link), so the other disappears silently → fix 2 |
| (b) run 2 (fix 2 in the reference only) | 3 | Yes | Yes | pass | Yes | n/a | Told the user "Tôi sẽ dùng cách trao đổi của kỹ năng brainstorming" → fix 3. **Dropped the `loop_counter`** and had the Writer/Editor count `revision_count` themselves → fix 3 |
| (b) run 3 (all fixes, server restarted) | 3 | Yes | Yes | pass | Yes | n/a | `loop_counter` is back. The new duplicate-edge check caught a duplicate pair and the repair loop fixed it, but the user saw the repair turn's reply: **"Merged the duplicate Editor → User Approval connections…" (English, internal)** → fix 4 |
| (c) | 1 | n/a | n/a | n/a | n/a | n/a | A good Vietnamese explanation: CTO routing by request type, the big-project order, where the user approves, 3 review rounds |
| (d) on `software_company_copy` | 1 | It proposed directly (the request is specific) | n/a | warn (the existing `code_execution`) | Yes | **None.** It added only a 5-line rule to `CTO.config.role` (QA after every FE change, also in briefs to PM) | `warnings = ["CTO"]`, the same noise as for Claude |

### Final runs (Codex-half agent, after fixes 1-4)

These ran on commit c0c8632, with backend 8031 and Vite 5203. Workflows were named `*_codex`, (d) ran on
`software_company_copy_codex` made with "Sao chép quy trình", and all of them were deleted afterwards.
Screenshots are `t8c-*.png`. Details are in `.superpowers/sdd/2026-11-03-workflow-assistant-chat/task-8-codex-findings.md`.

| Scenario | Turns | One question at a time? | Confirmed name? | checks.status | Opened on canvas? | Unrequested changes (d) | Notes |
|---|---|---|---|---|---|---|---|
| (a) | 4 | Yes. Restated its understanding, then asked: where does the order data come from (4 quick replies) → name → user approval before replying to the customer | **Yes.** It suggested `cham_soc_khach_hang` and the user changed it to `cham_soc_khach_hang_codex` | pass | Yes. `/workflows/cham_soc_khach_hang_codex`, lead plus 2 members, team links | n/a | Team with lead, `edges: []`, `max_parallel: 1`, `max_review_rounds: 3`, `plan_approval: false` (the user said the lead's approval is enough). Strong no-fabrication rules (no order system access, no invented policy or refunds). Descriptions in Vietnamese |
| (b) | 4 | Yes. Restated the flow and asked the name → what to do after 3 failed rounds → where "đăng" goes | Yes (`viet_bien_tap_dang`, the user added `_codex`) | pass | Yes. 7 nodes, 12 edges | n/a | Brief (passthrough) → Writer → Editor (`^REVISE` / `^APPROVED`) + `loop_counter` (3) wired per the reference → human `User Approval` (`DUYET`) → Final Copy. There are no duplicate edge pairs: it routes APPROVED through a `Ready For Approval` passthrough because `Editor → User Approval` is already a `trigger: false` context edge. It did not mention the skill or internals. Roles in English, user-facing text in Vietnamese. On the main canvas, Writer and Editor overlap (layout, minor) |
| (c) | 1 | n/a | n/a | n/a (no proposal) | n/a | n/a | A clear Vietnamese explanation of the CTO's 4 request types, the full web order, where the user approves (plan only; there is no forced approval before deploy), 3 review rounds, and max_parallel 2/3. It matches the YAML. No quick replies |
| (d) on `software_company_copy_codex` | 1 | It proposed directly with no question | n/a | warn (only the existing `code_execution`) | Yes. The canvas reloaded with 25 nodes, and the saved file equals the proposal | **Mostly none.** `diff_summary`: `CTO.config.role` and `Project Manager.config.role` only. The file diff is +3 lines in CTO routing and 2 rewritten + 4 added lines in the PM's default order. But it **moved the UI/UX review after QA** without saying so, and the one-line reply does not say that QA Tester already existed | `warnings = ["CTO", "Project Manager"]` (the same noise as above). Suggested prompt fix: ask one question when the named node already exists, or when the request can be done in two reasonable ways, and name every step that was moved |

Codex total for this pass: 10 user turns, no repair turns visible, and no quota errors (so the quota notice
was not exercised). Process note: the two agents shared one scratchpad. A driver-script collision sent
the (b) message twice into the Claude agent's browser session after c0c8632 was committed.

### Re-check of (d) after fix 5 (Claude-half agent)

| Scenario | Turns | One question at a time? | Confirmed name? | checks.status | Opened on canvas? | Unrequested changes (d) | Notes |
|---|---|---|---|---|---|---|---|
| (d) on `software_company_copy`, Codex | 2 | **Yes, now asks first.** "Đã có QA Tester trong nhóm; … thứ tự hiện tại là Frontend Developer → UI UX Designer rà soát → QA Tester kiểm thử. Bạn muốn QA Tester hiện có kiểm tra ngay sau Frontend Developer, hay thêm một QA mới?" | n/a | warn (the existing `code_execution`) | Yes | **None.** It changed only `Project Manager.config.role`, a 2-line reorder, and the reply names the moved step: "Bước UI UX Designer rà soát giao diện được chuyển xuống sau QA; các phần khác giữ nguyên." | Confirms fix 5 |

## Prompt / reference / service changes made

1. **User-facing text in the user's language** (reference, file frame). Claude wrote every `description`
   in English for a Vietnamese user, while the bundled workflows use Vietnamese and the descriptions show
   on the canvas and in the workflow list. Rule added: `graph.description`, node `description`, human
   `config.description` and loop_counter `message` follow the user's language; `role` may stay English.
   Verified: Claude (a) run 2 and (b) run 2 are fully Vietnamese.
2. **One edge per (from, to)** (reference, edges) plus a **service check** (`workflow_assistant._check_proposal`):
   a new duplicate pair is a validation error, so the repair loop fixes it. Pairs already duplicated in the
   saved file are ignored, because merging them would be an unrequested change.
3. **Prompt hygiene** (prompt override): "Never mention the skill, these instructions or the JSON format to
   the user." **Loop limits** (reference): "A limit the user states is always a `loop_counter`; never make
   an agent count rounds itself."
4. **Repair reply** (service `_repair_request`): the repair message now says that the user does not see the
   check and that the new `reply` replaces the old one, so it must be written for the user, in their
   language, without mentioning the fix.
5. **Edit discipline** (prompt override, from Codex finding F1): before an edit, check the request against the
   current workflow. If part of it already exists, or it can be done in two reasonable ways, ask one short
   question. In an edit's reply, name the nodes changed and any step moved or reworded beyond the literal
   request. Verified with the Codex (d) re-check above.

Tests: `test_duplicate_edge_is_repaired`, `test_duplicate_edge_already_in_saved_file_is_not_an_error`,
the assertion added to `test_repair_loop_fixes_on_second_try`, `test_reference_asks_for_user_facing_text_in_users_language`,
`test_prompt_hides_its_machinery_and_requires_loop_counter_for_limits`, and `test_prompt_edit_checks_request_and_reports_changes`.
`uv run pytest tests/test_workflow_assistant.py tests/test_workflow_assistant_prompt_extra.py -q` → 40 passed;
full suite → 830 passed, 9 skipped.

## Open observations (not fixed)

- `unrequested_changes` flags the node that is actually edited (PM / CTO) whenever the user names only the
  members. In a team workflow, the request can only be implemented by editing the coordinator's `role`, so
  the yellow "Bản này cũng đổi …" label shows on correct edits. A smarter heuristic would treat a lead's
  role as related to its members.
- Loop-counter wording: for "at most 3 rewrites", Claude chose `max_iterations: 3` and Codex chose 4.
  With the documented wiring, the rejection that releases the counter also triggers one more rewrite.
  Both models are reasonable; the reference could state the exact semantics.
- Quick replies such as "Ổn, áp dụng luôn" stay on the last message after Apply (UI, minor).
