# Trợ lý quy trình — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm khung chat AI ở trang `/workflows` để tạo mới, giải thích và sửa quy trình. AI hỏi lại theo kiểu brainstorming, chạy bằng Claude hoặc Codex, và chỉ lưu khi người dùng bấm "Áp dụng" trên thẻ đề xuất đã được kiểm tra.

**Architecture:**
- Backend có service mới, stateless. Mỗi lượt chat gọi provider CLI một lần, không có công cụ, theo mẫu `workflow_lab._judge_call`.
- Mô hình phải trả về JSON `{reply, quick_replies, proposal}`. Backend kiểm tra bản đề xuất bằng `static_check_data`, tự gửi lại cho mô hình sửa tối đa 2 lần, rồi tính diff đến từng trường so với file đã lưu.
- Frontend là bảng chat bên phải trong `WorkflowWorkbench`, có thẻ đề xuất kèm sơ đồ xem trước. Áp dụng dùng lại `postYaml` (tạo mới) và `mergeWorkflowDocument` (sửa).

**Tech Stack:** FastAPI + pydantic, PyYAML, pytest (`cd backend && uv run pytest`); Vue 3 `<script setup>`, vue-i18n, Vue Flow (`@vue-flow/core`); frontend kiểm bằng `npm run build` + `npm run lint` và chạy thật trên trình duyệt (repo chưa có unit test frontend).

**Spec:** `docs/superpowers/specs/2026-11-03-workflow-assistant-chat-design.md`

## Global Constraints

- Vendor: chỉ `anthropic` (nhãn "Claude", `claude_cli`) và `openai` (nhãn "Codex", `codex_cli`). Chỉ dùng kết nối đã đăng nhập (`auth_type` là `cli` hoặc `oauth`).
- Hết quota: **dừng**, trả lỗi `quota_exhausted`. Không dùng `pick_fallback`, không tự chuyển vendor.
- AI không có công cụ và không ghi file. Chỉ frontend được ghi, và chỉ khi người dùng bấm Áp dụng.
- Mỗi bản đề xuất tự sửa tối đa **2** lần. Vẫn FAIL thì không trả `proposal`. WARN vẫn cho áp dụng.
- Mỗi đề xuất là **một** file quy trình; tên khớp `^[a-zA-Z0-9._-]+$`, không chứa `..`, kết thúc `.yaml`; khi tạo mới, tên chưa được tồn tại.
- Timeout gọi mô hình 180 giây; chạy trong threadpool; `cli_cancel_scope` phải được đặt **bên trong** thread (contextvar không đi qua thread).
- Mọi chuỗi giao diện có khóa i18n ở cả `en.json`, `vi.json`, `zh.json`, dưới nhánh `workflow_assistant.*`.
- AI trả lời bằng ngôn ngữ của người dùng; không dán YAML thô khi chỉ được hỏi để hiểu.
- Router mới đặt `dependencies=[Depends(require_local_origin)]` như `lab.py`.
- **Sai lệch so với spec, cần biết:** spec §7.1 nói "canvas có thay đổi chưa lưu". Thực tế `WorkflowView` lưu ngay khi sửa trên sơ đồ ([WorkflowView.vue:2249](frontend/src/views/WorkflowView.vue#L2249)). Thứ duy nhất có thể chưa lưu là form sửa nút hoặc cạnh đang mở (`showDynamicFormGenerator`). Vì vậy nút Áp dụng bị chặn khi form đó đang mở.

## Review Focus

1. Mô hình trả JSON bọc trong ```` ```json ```` hoặc kèm lời dẫn trước/sau → vẫn parse được đối tượng JSON đầu tiên hợp lệ; không có thì toàn bộ văn bản là `reply`. (Task 4)
2. Người dùng sửa file ở tab khác sau khi có đề xuất → Áp dụng báo xung đột, không ghi; so `base_hash` (sha256 nội dung file đã lưu, chuẩn hóa `\r\n`→`\n`). (Task 4 tạo hash, Task 7 kiểm)
3. Mô hình đặt tên file tạo mới trùng hoặc sai quy tắc → backend coi như lỗi kiểm tra và cho mô hình sửa trong vòng tự sửa, không trả đề xuất hỏng. (Task 4)
4. Lịch sử hội thoại rất dài (20+ lượt, YAML lớn) → backend cắt các lượt giữa, luôn giữ tin đầu tiên của người dùng và 12 tin gần nhất; không vượt giới hạn CLI. (Task 4)
5. Người dùng bấm Dừng hoặc đóng bảng khi đang chờ → tiến trình CLI bị kill, request trả `cancelled`, giao diện không hiện lỗi đỏ. (Task 4, Task 7)

---

## File Structure

| File | Trách nhiệm |
|---|---|
| `backend/agentdev/api/services/workflow_lab.py` (sửa) | tách `static_check_data(data)` |
| `backend/agentdev/api/services/workflow_diff.py` (mới) | diff hai tài liệu quy trình đến từng trường, cảnh báo thay đổi ngoài yêu cầu |
| `backend/agentdev/api/services/workflow_assistant_reference.md` (mới) | tài liệu chuẩn YAML gọn cho mô hình |
| `backend/agentdev/api/services/workflow_assistant_prompt.py` (mới) | dựng system prompt từ skill, tài liệu chuẩn, catalog |
| `backend/agentdev/api/services/workflow_assistant.py` (mới) | providers, một lượt chat, parse, vòng tự sửa, hủy |
| `backend/agentdev/api/routes/workflow_assistant.py` (mới) + `routes/__init__.py` | HTTP |
| `backend/tests/test_workflow_diff.py`, `test_workflow_assistant.py`, `test_workflow_assistant_route.py`, thêm vào `test_workflow_lab.py` | test |
| `frontend/src/api/client.js` (sửa) | 3 hàm client |
| `frontend/src/composables/useWorkflowAssistant.js` (mới) | state chat, gửi, hủy, áp dụng, hoàn tác |
| `frontend/src/utils/layoutReconcile.js` (mới) | ghép bố cục vuegraph với graph mới |
| `frontend/src/components/workflow/assistant/WorkflowGraphPreview.vue` (mới) | Vue Flow chỉ đọc + tô màu diff |
| `frontend/src/components/workflow/assistant/ProposalCard.vue` (mới) | thẻ đề xuất |
| `frontend/src/components/workflow/assistant/WorkflowAssistantPanel.vue` (mới) | bảng chat |
| `DepartmentTemplatePicker.vue`, `WorkflowList.vue`, `WorkflowWorkbench.vue`, `WorkflowView.vue`, 3 file locale (sửa) | điểm mở + tích hợp |

---

### Task 1: `static_check_data`

**Files:**
- Modify: `backend/agentdev/api/services/workflow_lab.py:60-166`
- Test: `backend/tests/test_workflow_lab.py`

**Interfaces:**
- Produces: `static_check_data(data: Any) -> Dict[str, Any]` (cùng dạng `{"status", "checks"}` như `static_check`); `static_check(yaml_path)` chỉ còn đọc + parse file rồi gọi hàm này.

- [ ] **Step 1: Write the failing test** `test_static_check_data_matches_file_check`: với mỗi file trong `workspace/workflows/*.yaml` (dùng `tmp_path` copy `software_company.yaml` và `demo_loop_counter.yaml`), `static_check_data(yaml.safe_load(text)) == static_check(path)`. Thêm `test_static_check_data_rejects_non_mapping`: `static_check_data(["x"])["status"] == "fail"` và có check `structure` FAIL.
- [ ] **Step 2:** `cd backend && uv run pytest tests/test_workflow_lab.py -k static_check_data -v` → FAIL (ImportError).
- [ ] **Step 3:** Tách thân hàm từ `error = check_config(data)` trở đi thành `static_check_data`. Dữ liệu không phải dict thì FAIL `structure` với thông điệp `"Workflow must be a mapping"`.
- [ ] **Step 4:** Chạy lại cả file test → PASS.
- [ ] **Step 5:** `git commit -m "refactor(lab): tách static_check_data để kiểm tra YAML chưa ghi file"`

---

### Task 2: Diff tài liệu quy trình

**Files:**
- Create: `backend/agentdev/api/services/workflow_diff.py`
- Test: `backend/tests/test_workflow_diff.py`

**Interfaces:**
- Produces:
  - `diff_workflows(old: Optional[dict], new: dict) -> dict` trả về
    `{"nodes_added": [id], "nodes_removed": [id], "nodes_changed": [{"id", "fields": [dotted path]}], "edges_added": [{"from","to"}], "edges_removed": [{"from","to"}], "graph_fields_changed": [dotted path]}`.
    `old=None` (tạo mới) → mọi nút là `nodes_added`.
  - `unrequested_changes(diff: dict, user_text: str) -> List[str]`: id nút bị xóa/đổi, hoặc cạnh bị xóa, mà **không** xuất hiện trong `user_text` (so không phân biệt hoa thường, cũng thử dạng thay `_`/`-` bằng khoảng trắng).

- [ ] **Step 1: Write the failing tests**
  - `test_diff_detects_added_removed_changed`: old có nút A,B và cạnh A→B; new bỏ B, thêm C, đổi `A.config.role`, cạnh A→C. Kỳ vọng `nodes_added==["C"]`, `nodes_removed==["B"]`, `nodes_changed==[{"id":"A","fields":["config.role"]}]`, `edges_added==[{"from":"A","to":"C"}]`, `edges_removed==[{"from":"A","to":"B"}]`.
  - `test_diff_field_paths_are_leaf_level`: đổi `config.team.members` (list) → field `"config.team.members"`; đổi `config.team.max_delegations` → `"config.team.max_delegations"`.
  - `test_diff_create_lists_all_nodes_added` (`old=None`).
  - `test_diff_identical_is_empty`: mọi list rỗng.
  - `test_unrequested_flags_unmentioned`: diff đổi `Bug Fixer` và `QA Tester`, `user_text="sửa role của qa tester"` → `["Bug Fixer"]`.
  - `test_unrequested_ignores_added_nodes`: nút thêm mới không bao giờ bị cảnh báo.
- [ ] **Step 2:** `uv run pytest tests/test_workflow_diff.py -v` → FAIL.
- [ ] **Step 3:** Implement. So nút theo `id`. Đệ quy dict để lấy đường dẫn lá; list và giá trị vô hướng tính là lá. Cạnh xác định bằng cặp `(from, to)`; một cạnh đổi thuộc tính (condition…) thì báo là `edges_changed: [{"from","to","fields"}]`, thêm khóa này vào kết quả.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** `git commit -m "feat(assistant): diff quy trình đến từng trường"`

---

### Task 3: Tài liệu chuẩn YAML + system prompt

**Files:**
- Create: `backend/agentdev/api/services/workflow_assistant_reference.md`
- Create: `backend/agentdev/api/services/workflow_assistant_prompt.py`
- Test: `backend/tests/test_workflow_assistant.py` (phần prompt)

**Interfaces:**
- Produces: `build_system_prompt(*, current_yaml: Optional[str], current_name: Optional[str], pending_yaml: Optional[str], existing_files: List[str], skills: List[Tuple[str, str]], tools: List[Tuple[str, str]], models: Dict[str, List[str]]) -> str`; `load_context() -> dict` gom `existing_files` (từ `YAML_DIR`), `skills` (`skill_library.list_skills()`, chỉ `valid`), `tools` (`get_function_catalog().list_metadata()`), `models` (vendor → model list từ `connections.catalog`).

- [ ] **Step 1: Write the reference** `workflow_assistant_reference.md` (~150–250 dòng). Viết từ schema thật trong `backend/agentdev/entity/configs/node/{agent,human,literal,passthrough,loop_counter,subgraph,team,skills,tooling}.py` và `entity/configs/edge/{edge,edge_condition}.py`. Gồm:
  - khung `version`/`graph`;
  - các trường bắt buộc của từng loại nút;
  - cạnh với `condition`, `trigger`, `carry_data`, `keep_message`;
  - khối `team` và `skills.allow`;
  - 2 ví dụ đầy đủ (rút gọn từ `software_company.yaml`, và một dây chuyền Viết → Duyệt có điều kiện + `loop_counter` + `human`);
  - quy tắc: mọi agent có `provider` + `name` lấy từ danh sách model được cung cấp; chỉ dùng skill/tool trong danh mục; `subgraph` chỉ trỏ quy trình đã có hoặc graph inline.

  Cả hai ví dụ phải qua `static_check_data` (kiểm ở Step 2).
- [ ] **Step 2: Write the failing tests**
  - `test_reference_examples_pass_static_check`: tách các khối ```` ```yaml ```` trong file reference, mỗi khối `static_check_data(...)["status"] != "fail"`.
  - `test_prompt_includes_context`: prompt chứa từng tên skill, tên tool, tên file đã có, model `claude-opus-5-5`, và `current_yaml` khi được truyền.
  - `test_prompt_pending_yaml_section`: có `pending_yaml` thì prompt có mục "Bản đề xuất chưa áp dụng" chứa nó, và dặn sửa tiếp từ bản đó.
  - `test_prompt_brainstorming_override`: prompt chứa nội dung `workspace/skills/brainstorming/SKILL.md`, **và** sau nó là đoạn ghi đè, gồm đúng cụm `"Do not write files, commit, or invoke other skills"`, `"one question per turn"` và `"Reply with a single JSON object"`.
- [ ] **Step 3:** `uv run pytest tests/test_workflow_assistant.py -k "prompt or reference" -v` → FAIL.
- [ ] **Step 4: Implement `build_system_prompt`.** Thứ tự các mục:
  1. vai trò;
  2. SKILL.md brainstorming;
  3. đoạn ghi đè cho bối cảnh này, gồm: mỗi lượt một câu hỏi; phải xác nhận tên, dạng, vai trò/nhiệm vụ, quan hệ/thứ tự, điểm duyệt, điều kiện rẽ nhánh/lặp trước khi đề xuất tạo mới; "cứ làm" thì đề xuất ngay với giả định nêu rõ; giải thích bằng lời, không dán YAML; khi sửa thì chép nguyên văn phần không được yêu cầu, giữ anchor/alias;
  4. hợp đồng JSON (copy đúng schema ở spec §7.2);
  5. tài liệu chuẩn;
  6. danh mục skill/tool/model/file;
  7. quy trình hiện tại / bản đề xuất chưa áp dụng.
- [ ] **Step 5:** PASS.
- [ ] **Step 6:** `git commit -m "feat(assistant): tài liệu chuẩn YAML và system prompt"`

---

### Task 4: Service một lượt chat

**Files:**
- Create: `backend/agentdev/api/services/workflow_assistant.py`
- Test: `backend/tests/test_workflow_assistant.py`

**Interfaces:**
- Consumes: Task 1 `static_check_data`; Task 2 `diff_workflows`, `unrequested_changes`; Task 3 `build_system_prompt`, `load_context`.
- Produces:
  - `list_providers() -> List[dict]`: `{vendor, label, connection_id, model, available}`. Luôn có 2 mục (anthropic, openai). `available=False` khi không có kết nối đăng nhập. Chọn kết nối: ưu tiên kết nối mặc định nếu cùng vendor, rồi kết nối đầu tiên. Model: `account_fallback.default_model_for(conn)`.
  - `class AssistantError(Exception)` có `code: str` ∈ {`quota_exhausted`, `not_signed_in`, `timeout`, `cancelled`, `provider_error`, `bad_request`}.
  - `run_turn(*, vendor: str, workflow: Optional[str], messages: List[dict], pending_yaml: Optional[str], request_id: str, call: Callable[[str, List[dict]], str] | None = None) -> dict`. Trả `{reply, quick_replies, proposal, model_used}` với `proposal = {kind, filename, yaml, base_hash, diff_summary, warnings, checks} | None`. `call(system, messages) -> text` có thể tiêm vào để test; mặc định gọi provider thật.
  - `cancel(request_id: str) -> bool`.
  - `content_hash(text: str) -> str` = sha256 hex của text sau khi thay `\r\n`→`\n`.
  - `parse_model_output(text: str) -> dict`.

- [ ] **Step 1: Write the failing tests.** Tiêm `call` giả:
  - `test_parse_plain_json`, `test_parse_fenced_json_with_prose` (lời dẫn + ```` ```json {...} ``` ```` + lời kết → lấy được object), `test_parse_non_json_becomes_reply` (`proposal is None`, `reply == text.strip()`).
  - `test_question_turn_has_no_proposal`.
  - `test_valid_create_proposal`: call trả về proposal create `"tong_dai.yaml"` hợp lệ → `proposal["kind"]=="create"`, `checks["status"]!="fail"`, `base_hash is None`, `diff_summary["nodes_added"]` khác rỗng.
  - `test_repair_loop_fixes_on_second_try`: lần 1 YAML sai (thiếu `graph.start`), lần 2 đúng → có proposal. Tin nhắn thứ hai gửi cho `call` chứa chi tiết lỗi.
  - `test_repair_loop_gives_up_after_two_repairs`: luôn sai → `call` được gọi đúng **3** lần; `proposal is None`; `reply` chứa danh sách lỗi.
  - `test_create_name_taken_is_repaired`: lần 1 đặt `software_company.yaml` (đã tồn tại trong `YAML_DIR` được monkeypatch sang `tmp_path`) → bị coi là lỗi, lần 2 tên khác → ok.
  - `test_invalid_filename_is_repaired` (`../x.yaml`).
  - `test_edit_proposal_diff_and_warnings`: workflow có sẵn trong tmp, messages cuối `"thêm QA sau Frontend"`, proposal đổi cả role của `Bug Fixer` → `warnings` chứa `"Bug Fixer"`; `base_hash == content_hash(file_text)`.
  - `test_edit_kind_forced_for_workflow_context`: có `workflow` mà mô hình trả `kind:"create"` cùng tên file đó → coi là `edit`. Tên khác → giữ `create` (cho phép tạo bản mới từ ngữ cảnh).
  - `test_quota_error_maps_to_code`: `call` raise exception mà `account_fallback.is_quota_error` nhận ra → `AssistantError.code=="quota_exhausted"`, `call` chỉ được gọi 1 lần.
  - `test_history_trimmed`: 30 tin → `call` nhận tin đầu + 12 tin cuối.
  - `test_unknown_vendor_bad_request`.
  - `test_cancel_sets_event`: `call` chặn cho tới khi event được set; `cancel(request_id)` từ thread khác → `AssistantError.code=="cancelled"`.
- [ ] **Step 2:** Chạy → FAIL.
- [ ] **Step 3: Implement.**
  - `call` mặc định: resolve kết nối của vendor qua `list_providers`, rồi làm như `_judge_call` với `SimpleConfig(... params={"timeout": 180}, node_id="workflow_assistant")`. Ghép `system` thành `Message(SYSTEM)`, từng tin thành `Message(USER|ASSISTANT)`. Bọc trong `with cli_cancel_scope(event)`, với `event` là `threading.Event` đăng ký theo `request_id` trong dict có lock, xóa trong `finally`.
  - Map `CliCancelled` → `cancelled`; `is_quota_error`/`is_exhaustion_error` → `quota_exhausted`; timeout → `timeout`; lỗi khác → `provider_error`.
  - Kiểm tra proposal theo thứ tự: tên file (`validate_workflow_filename`, đuôi `.yaml`, chưa tồn tại nếu create) → `yaml.safe_load` → `static_check_data`. Lỗi gom thành văn bản gửi lại dưới dạng tin user: `"Your proposal failed validation:\n- …\nReturn the corrected full JSON."`
  - Với `edit`: đọc file đã lưu → `base_hash`, `diff_workflows(old,new)`. `warnings` = `unrequested_changes(diff, last_user_text)` + các check WARN.
- [ ] **Step 4:** PASS toàn bộ `tests/test_workflow_assistant.py`.
- [ ] **Step 5:** `git commit -m "feat(assistant): một lượt chat với vòng tự sửa và diff"`

---

### Task 5: HTTP routes

**Files:**
- Create: `backend/agentdev/api/routes/workflow_assistant.py`
- Modify: `backend/agentdev/api/routes/__init__.py` (import + thêm `workflow_assistant.router` vào `ALL_ROUTERS`)
- Test: `backend/tests/test_workflow_assistant_route.py`

**Interfaces:**
- Consumes: Task 4.
- Produces (prefix `/api/workflow-assistant`):
  - `GET /providers` → `{"providers": [...]}`
  - `POST /chat` body `ChatRequest{vendor: str, workflow: Optional[str], messages: List[{role: Literal["user","assistant"], content: str(max 50_000)}] (1..200), pending_yaml: Optional[str](max 200_000), request_id: str(1..64)}` → 200 kết quả `run_turn`; `AssistantError` → **200** `{"error": code, "message": str}` (để frontend xử lý thống nhất; `bad_request` → 400).
  - `POST /cancel` body `{request_id}` → `{"cancelled": bool}`.
  - `/chat` gọi `run_turn` qua `await run_in_threadpool(...)`.

- [ ] **Step 1: Write the failing tests** (TestClient, monkeypatch `run_turn`/`list_providers`):
  - `test_providers_route`;
  - `test_chat_route_ok`;
  - `test_chat_route_quota_returns_error_payload` (status 200, `error=="quota_exhausted"`);
  - `test_chat_route_validates_roles` (role `"system"` → 422);
  - `test_cancel_route`;
  - `test_rejects_non_local_origin` (header `Origin: http://evil.example` → 403, như test hiện có cho lab nếu có).
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** PASS. Chạy thêm toàn bộ `uv run pytest -q` để không vỡ test cũ.
- [ ] **Step 5:** `git commit -m "feat(assistant): API /api/workflow-assistant"`

---

### Task 6: Client + composable + ghép bố cục

**Files:**
- Modify: `frontend/src/api/client.js` (thêm sau `checkWorkflowConnections`)
- Create: `frontend/src/composables/useWorkflowAssistant.js`
- Create: `frontend/src/utils/layoutReconcile.js`

**Interfaces:**
- Consumes: Task 5.
- Produces:
  - `fetchAssistantProviders()`, `sendAssistantMessage({vendor, workflow, messages, pendingYaml, requestId})`, `cancelAssistantRequest(requestId)`. Cùng kiểu trả `{success, ...data}` / `networkFailure` như các hàm hiện có.
  - `useWorkflowAssistant()` trả về (singleton ở module scope, để đóng mở bảng không mất lịch sử):
    `{ context: Ref<{mode:'create'|'workflow', workflow: string|null}>, providers, vendor, threads /* Map key 'create' | tên quy trình */, currentThread: ComputedRef<{messages, pendingProposal, status}>, setContext(mode, workflow), send(text), stop(), newConversation(), applyProposal({formOpen:boolean}) -> Promise<{ok, reason?: 'conflict'|'form_open'|'failed', filename?}>, discardProposal(), undoLast() }`.
    `vendor` nhớ trong `localStorage['agentdev:assistant-vendor']` (đọc/ghi trong try/catch).
  - `reconcileLayout(flowJson: object|null, newGraph: object, diff: object) -> object|null`: giữ node Vue Flow có id còn trong graph; bỏ node có id trong `diff.nodes_removed`; với nút mới, đặt `position` = vị trí nút nối với nó (qua cạnh) + `{x: 260, y: 0}`, không có hàng xóm thì dưới nút thấp nhất + `{x: 0, y: 160}`. Bỏ các edge Vue Flow không còn trong graph. `flowJson=null` → `null` (editor tự sắp).
- Hành vi `applyProposal`:
  - **create**: `postYaml(filename, yaml)`. Thành công thì `setContext('workflow', name)` và trả `{ok, filename}`.
  - **edit**: `fetchWorkflowYAML(name)` rồi tính sha256 (`crypto.subtle`, sau khi thay `\r\n`→`\n`). Khác `base_hash` → `{ok:false, reason:'conflict'}` và thêm tin hệ thống vào thread. Nếu `formOpen` → `form_open`. Nếu không: lưu `{oldYaml, oldLayout}` để hoàn tác → `mergeWorkflowDocument(name, yaml.load(proposal.yaml))` → `fetchVueGraph` + `reconcileLayout` + `postVuegraphs`.
  - `undoLast()`: `updateYaml(name, oldYaml)` + `postVuegraphs(oldLayout)` (nếu có).
  - Đề xuất mới thay thế `pendingProposal`; tin chứa đề xuất cũ đánh dấu `superseded: true`.
  - Lỗi `quota_exhausted` → tin hệ thống `{kind:'quota', vendor, retryText}` để Panel hiện nút chuyển. `cancelled` → bỏ trạng thái chờ, không thêm lỗi.
  - `send` gửi `pendingYaml = pendingProposal?.yaml`.
- [ ] **Step 1:** Implement ba file. Dùng thư viện YAML frontend đang có (kiểm `package.json`: `js-yaml`/`yaml`; không thêm dependency mới).
- [ ] **Step 2:** `cd frontend && npm run lint && npm run build` → không lỗi.
- [ ] **Step 3:** `git commit -m "feat(assistant): client, composable và ghép bố cục"`

---

### Task 7: Giao diện chat, thẻ đề xuất, tích hợp

**Files:**
- Create: `frontend/src/components/workflow/assistant/WorkflowGraphPreview.vue`, `ProposalCard.vue`, `WorkflowAssistantPanel.vue`
- Modify: `DepartmentTemplatePicker.vue` (thẻ "Tạo bằng AI", emit `ai`), `WorkflowList.vue` (bắt `ai`, emit `open-assistant` lên workbench), `WorkflowWorkbench.vue` (nút icon chat cố định, giữ Panel, `reloadKey` remount `WorkflowView` sau khi áp dụng, điều hướng sau khi tạo), `WorkflowView.vue` (`defineExpose({ hasOpenForm: () => showDynamicFormGenerator.value })`), `en.json`/`vi.json`/`zh.json`.

**Interfaces:**
- Consumes: Task 6.
- `WorkflowGraphPreview` props: `{ graph: object, diff: object|null }`. Đây là Vue Flow `readonly`, `fit-view-on-init`, dùng lại `WorkflowNode`/`WorkflowEdge`. Bố cục tự xếp theo lớp: BFS từ `graph.start`, cột = độ sâu, lead → member xếp cột kế tiếp. Lớp CSS `added`/`changed`/`removed`; nút bị xóa lấy từ `diff` và vẽ mờ, gạch ngang.
- `ProposalCard` props: `{ proposal, superseded: boolean, busy: boolean }`; emits `apply`, `discard`. Thẻ gồm:
  - tên file;
  - danh sách thay đổi từ `diff_summary`, nhóm: thêm / xóa / đổi (kèm field) / cạnh;
  - `warnings` dạng nhãn vàng;
  - các check WARN;
  - preview;
  - `<details>` YAML;
  - nút Áp dụng / Bỏ qua.
- Panel:
  - Header: tiêu đề, nhãn ngữ cảnh, nút "Cuộc trò chuyện mới", nút đóng.
  - Danh sách tin: user là bong bóng phải; AI phẳng, render markdown bằng thư viện markdown sẵn có trong repo (kiểm `LaunchView`/chat hiện có; không thêm dependency).
  - Trạng thái chờ có nút Dừng; `quick_replies` là chip; gợi ý mở đầu ở chế độ create.
  - Composer: textarea tự giãn, Enter gửi, Shift+Enter xuống dòng; select vendor chỉ bật mục `available`; không có mục nào thì hiện link `/connections`.
  - Tin quota: nút "Chuyển sang {other}" → đặt vendor rồi gửi lại `retryText`.
  - Bảng rộng mặc định 420px, kéo cạnh trái để đổi (min 340, max 720), lưu localStorage; ở màn hẹp < 900px thì phủ toàn chiều rộng.
  - Đóng bảng khi đang chờ thì gọi `stop()`.
- Sau `applyProposal`:
  - `conflict` → toast lỗi `workflow_assistant.conflict`;
  - `form_open` → toast `workflow_assistant.close_form_first`;
  - ok + edit → toast thành công có nút Hoàn tác 10 giây (kiểm `utils/toast.js` có hỗ trợ action không; không có thì thêm tham số `action: {label, onClick}` và `duration`), rồi tăng `reloadKey`;
  - ok + create → `handleSelect(name)`.

- [ ] **Step 1:** Implement các component và chỗ sửa. Thêm khóa i18n đủ 3 ngôn ngữ.
- [ ] **Step 2:** `npm run lint && npm run build` → sạch.
- [ ] **Step 3: Kiểm trên trình duyệt** (skill `run`/`playwright-cli`, backend + `npm run dev`, mở `http://localhost:5173/workflows`). Backend chưa tiêm mô hình thật thì dùng tài khoản thật. Các bước:
  - (a) bấm Tạo → "Tạo bằng AI" → panel mở chế độ tạo mới;
  - (b) mở `software_company` → nút chat → nhãn "Quy trình: software_company";
  - (c) đóng/mở panel vẫn còn lịch sử;
  - (d) mở form sửa nút rồi bấm Áp dụng → bị chặn;
  - (e) sửa file ở tab khác rồi Áp dụng → báo xung đột;
  - (f) Dừng khi đang chờ → không có lỗi đỏ;
  - (g) màn hẹp 800px panel phủ toàn màn.

  Chụp màn hình kết quả.
- [ ] **Step 4:** `git commit -m "feat(assistant): bảng chat tạo/giải thích/sửa quy trình trên trang workflows"`

---

### Task 8: Kiểm chất lượng thật với Claude và Codex

**Files:**
- Create: `docs/superpowers/plans/2026-11-03-workflow-assistant-verification.md` (ghi kết quả)

- [ ] **Step 1:** Với **mỗi** vendor đã đăng nhập, chạy 4 kịch bản trên giao diện thật (làm (d) trên bản sao `software_company_copy` tạo bằng nút Sao chép):
  - (a) "Tạo phòng chăm sóc khách hàng: trưởng nhóm tiếp nhận, 1 người tra cứu đơn hàng, 1 người soạn trả lời" → AI phải hỏi ít nhất một câu và xác nhận tên trước khi đề xuất;
  - (b) "Dây chuyền viết bài: Viết → Biên tập; biên tập chưa đạt thì quay lại viết tối đa 3 lần; đạt thì chờ tôi duyệt rồi đăng";
  - (c) "Giải thích quy trình software_company chạy thế nào";
  - (d) "Thêm QA Tester kiểm tra sau Frontend Developer".
- [ ] **Step 2:** Mỗi kịch bản ghi: số lượt, có hỏi đúng kiểu không, `checks.status`, mở được trên canvas không, và với (d) thì `diff_summary` có thay đổi ngoài yêu cầu không.

  Một kịch bản fail thì sửa prompt hoặc tài liệu chuẩn (Task 3), chạy lại `uv run pytest tests/test_workflow_assistant.py`, rồi lặp lại kịch bản đó.
- [ ] **Step 3:** `git commit -m "test(assistant): kiểm chất lượng thật với Claude và Codex"`
