# Trợ lý quy trình (chat tạo / giải thích / sửa quy trình bằng AI) — Thiết kế

Ngày: 2026-11-03 · Trạng thái: chờ duyệt

## 1. Mục đích và lý do

Ở trang `/workflows`, hiện người dùng chỉ tạo được quy trình theo hai cách: tạo trống rồi kéo thả từng nút, hoặc chép một mẫu phòng ban. Cả hai đều chậm, và người dùng phải hiểu sẵn cấu trúc YAML/graph.

Người dùng muốn **mô tả bằng lời** quy trình mình cần (có những vị trí nào, quan hệ ra sao, mỗi người xử lý việc gì) rồi để AI dựng giúp. AI phải **hỏi lại như một chuyên gia** (theo skill `brainstorming`) để lấy đủ thông tin, xác nhận những điểm quan trọng như tên quy trình, rồi mới đưa ra bản đề xuất. Cùng khung chat đó còn dùng để **hỏi về một quy trình có sẵn** (ai làm gì, luồng chạy ra sao) và **sửa nó** (thêm, bớt, chỉnh).

Người dùng chọn được chạy trợ lý bằng **Claude hoặc Codex**. Giao diện chat theo phong cách Claude Code trong VS Code.

## 2. Mục tiêu

1. **Tạo mới** quy trình từ mô tả bằng lời. Hỗ trợ đủ hai dạng và dạng trộn:
   - *Đội có trưởng nhóm* (giống `software_company.yaml`): một agent lead có `team` (members, plan_approval, max_delegations…), các thành viên là agent riêng.
   - *Dây chuyền*: các nút nối bằng cạnh, có `condition` trên cạnh (rẽ nhánh), vòng lặp có giới hạn (`loop_counter`), bước người duyệt (`human`), bước gọi đội con (`subgraph`) khi cần.
2. **Giải thích** một quy trình bất kỳ đang có, bằng lời dễ hiểu: các vai trò, ai báo cáo cho ai, việc đi qua những bước nào, khi nào thì rẽ nhánh hay lặp lại, điểm bắt đầu và kết thúc.
3. **Sửa** một quy trình đang có theo yêu cầu. AI chỉ thay đổi đúng phần được yêu cầu, giữ nguyên phần còn lại (gồm comment YAML và bố cục sơ đồ của các nút không đổi).
4. **Hỏi trước khi làm** theo tinh thần brainstorming: hỏi từng câu một, xác nhận tên quy trình (slug file hợp lệ, chưa trùng) và các giả định quan trọng; khi đã đủ thông tin thì mới đề xuất.
5. **Chọn mô hình**: Claude (vendor `anthropic`, `claude_cli`) hoặc Codex (vendor `openai`, `codex_cli`), dùng tài khoản đã đăng nhập ở trang Kết nối.
6. **Không bao giờ có file hỏng**: mọi bản đề xuất đều qua kiểm tra cấu trúc trước khi hiện cho người dùng.

## 3. Ngoài phạm vi

- AI **không** tự chạy quy trình, không chạy Lab, không gọi công cụ ghi file. Nó chỉ đề xuất; người dùng bấm "Áp dụng" thì mới lưu.
- Không thay thế trình sửa kéo thả. Hai cách dùng song song.
- Không tạo skill mới hay kết nối mới. AI chỉ được dùng skill đang có trong `workspace/skills` và các nhà cung cấp đang có.
- Không cần lưu lịch sử chat giữa các lần mở trình duyệt (xem §7, quyết định của mình).

## 4. Điều tuyệt đối không được xảy ra (anti-goals)

- Ghi đè quy trình người dùng đang dùng khi họ chưa bấm "Áp dụng".
- Lưu một YAML mà `static_check` báo FAIL, hoặc mở ra bị lỗi trên canvas.
- Khi sửa, âm thầm thay đổi những phần người dùng không nhắc tới (đổi tên nút, đổi model, xóa comment, xáo trộn bố cục).
- Bỏ qua câu hỏi, đoán bừa rồi tạo ngay một quy trình lớn từ một câu mô tả mơ hồ. Ngược lại cũng không được hỏi lan man: mỗi lượt chỉ hỏi một câu, và khi người dùng nói "cứ làm đi" thì đề xuất ngay với các giả định nêu rõ.
- Trả lời bằng cách dán lại YAML thô khi người dùng chỉ hỏi để hiểu.

## 5. Ràng buộc từ code hiện có

- Quy trình là file YAML trong `WORKFLOWS_DIR` (`workspace/workflows/`). Đọc, ghi và kiểm tra dùng `workflow_storage.validate_workflow_filename`, `validate_workflow_content`, `persist_workflow`.
- Kiểm tra cấu trúc: `workflow_lab.static_check(yaml_path)` (gồm `check_config`, skill có tồn tại, gắn kết nối mặc định…). Hàm này nhận **đường dẫn file**. Cần tách thành `static_check_data(data)` và giữ `static_check(path)` gọi lại hàm mới, hoặc ghi ra file tạm.
- Lưu bản sửa giữ comment: `PUT /api/workflows/{file}/merge` (`workflow_yaml_merge.py`, client `mergeWorkflowDocument`).
- Tạo mới: `POST /api/workflows/upload/content` (client `postYaml`). Bố cục canvas lưu riêng qua `postVuegraphs`. Quy trình mới chưa có bố cục thì editor tự sắp.
- Gọi mô hình một lần, không công cụ: theo mẫu `workflow_lab._judge_call` (resolve connection → `ProviderRegistry` → `call_model`). Chọn tài khoản theo mẫu `JudgeAccount`, chuyển tài khoản khi hết quota bằng `account_fallback.pick_fallback(..., needs_tools=False)`.
- Gọi CLI mất vài giây đến vài chục giây mỗi lượt. Backend chạy việc này trong thread (giống Lab) để không chặn event loop.
- Giao diện: Vue 3, i18n ba thứ tiếng `en.json`, `vi.json`, `zh.json` (phải thêm khóa cho cả ba). Canvas dùng Vue Flow trong `WorkflowView.vue`.
- Điểm vào "Tạo": `DepartmentTemplatePicker.vue`, mở từ `WorkflowList.vue` (`openFormGenerator`) và từ trạng thái trống của `WorkflowWorkbench.vue`.

## 6. Các cách đã cân nhắc

| Cách | Mô tả | Đánh đổi |
|---|---|---|
| **A. Dịch vụ "Trợ lý quy trình" riêng (đã chọn)** | Mỗi lượt chat, backend gọi Claude/Codex **một lần**, không công cụ. Lời nhắc hệ thống gồm skill `brainstorming`, tài liệu chuẩn YAML, YAML quy trình đang mở. Mô hình trả về JSON có cấu trúc; backend kiểm tra rồi tự cho AI sửa lỗi. Frontend hiện chat, xem trước và nút "Áp dụng". | Nhanh, rẻ, AI không thể tự ghi file. Bước xem trước là chắc chắn. Phải viết khung chat mới. |
| B. Trợ lý là một quy trình agent chạy qua engine chat của LaunchView | Có sẵn streaming, phiên, dự phòng tài khoản. | Agent có công cụ ghi file nên khó đảm bảo bước xem trước. Vòng công cụ chậm và tốn hơn nhiều. |
| C. Như A, nhưng AI trả về danh sách thao tác (add_node, remove_edge…) | Sửa chính xác từng chỗ. | Phải định nghĩa và bảo trì bộ thao tác. Hàm merge có sẵn đã giữ được phần không đổi, nên lợi thêm không đáng công. |

Người dùng chọn **A**.

## 7. Thiết kế

### 7.1 Trải nghiệm người dùng

**Điểm mở trợ lý**
- Trong hộp "Tạo" (`DepartmentTemplatePicker`), thêm thẻ thứ ba **"Tạo bằng AI"** (icon chat, nổi bật nhất), đặt cạnh "Trống" và "Mẫu phòng ban". Bấm vào thì đóng hộp và mở bảng trợ lý ở **chế độ tạo mới**.
- Trên thanh công cụ của trang `/workflows` (workbench), thêm một nút icon chat cố định. Đang mở một quy trình thì bảng trợ lý mở ở **chế độ quy trình này**: AI đã có nội dung quy trình, sẵn sàng giải thích hoặc sửa. Chưa mở quy trình nào thì vào chế độ tạo mới.

**Bảng trợ lý** (kiểu Claude Code trong VS Code, quyết định của mình)
- Bảng trượt ra từ cạnh phải, rộng khoảng 420px, kéo giãn được, không che hết canvas, để vừa chat vừa nhìn sơ đồ.
- Đầu bảng: tiêu đề, nhãn ngữ cảnh ("Tạo mới" hoặc "Quy trình: <tên>"), nút "Cuộc trò chuyện mới", nút đóng.
- Thân bảng: tin nhắn của người dùng nằm bên phải trong bong bóng. Tin của AI hiển thị phẳng toàn chiều rộng, render markdown. Đang chờ AI thì hiện dòng trạng thái ("Đang suy nghĩ…", "Đang kiểm tra bản đề xuất…"), có nút Dừng.
- Ô nhập ở đáy: textarea tự giãn. Enter để gửi, Shift+Enter để xuống dòng. Bên trái ô nhập có **ô chọn mô hình** (Claude / Codex). Chỉ liệt kê các nhà cung cấp có tài khoản đã đăng nhập. Không có tài khoản nào thì hiện liên kết sang trang Kết nối.
- Khi AI hỏi lại, nó có thể kèm 2–4 **gợi ý trả lời nhanh** dạng nút bấm (bấm là gửi câu đó). Người dùng vẫn gõ tự do được.
- Lần đầu mở ở chế độ tạo mới, hiện vài câu gợi ý khởi đầu (dùng lại kiểu `ChatSuggestions.vue`).

**Thẻ đề xuất** (khi AI có bản tạo mới hoặc bản sửa)
- Nằm trong luồng chat, gồm:
  - tên file (khi tạo mới);
  - **tóm tắt thay đổi** do backend tính từ hai bản YAML, không lấy từ lời AI: nút thêm/xóa/sửa, cạnh thêm/xóa, thay đổi lead/team;
  - **sơ đồ xem trước** chỉ đọc (Vue Flow, tự sắp bố cục; khi sửa thì tô màu nút mới, nút bị xóa, nút đã đổi);
  - nút "Xem YAML" thu gọn;
  - nút **Áp dụng** / **Bỏ qua**.
- **Áp dụng khi tạo mới**: lưu qua `upload/content`, điều hướng tới `/workflows/<tên>`, toast thành công. Bảng trợ lý chuyển sang chế độ quy trình này để chat tiếp.
- **Áp dụng khi sửa**: lưu qua `merge`, canvas tải lại, toast thành công. Nếu file đã bị sửa ở nơi khác sau khi đề xuất được tạo (hash nội dung khác) thì báo xung đột, không ghi, và đề nghị AI làm lại trên bản mới.
- Đề xuất mới thay thế đề xuất cũ chưa áp dụng (thẻ cũ bị mờ đi, ghi "đã có bản mới hơn").
- Sau khi áp dụng sửa, có nút **Hoàn tác** trên toast trong khoảng 10 giây. Hoàn tác ghi lại nội dung YAML cũ qua `update` **và** bố cục cũ qua `postVuegraphs`.
- **Bố cục khi áp dụng sửa**: nút không đổi giữ nguyên vị trí; nút bị xóa thì bỏ khỏi bố cục; nút mới thì đặt cạnh các nút nó nối tới.
- **Canvas có thay đổi chưa lưu**: trợ lý đọc **file đã lưu**. Lúc này nút Áp dụng bị chặn và hiện lựa chọn "Lưu thay đổi trên canvas trước" / "Bỏ thay đổi trên canvas". Sau khi người dùng chọn, nếu file khác bản AI đã dùng thì xử lý như xung đột.

**Lịch sử chat** (quyết định của mình): giữ trong bộ nhớ phía trình duyệt theo từng ngữ cảnh (tạo mới / từng quy trình) trong phiên làm việc; đóng mở lại bảng vẫn còn. Tải lại trang thì mất. Nếu người dùng cần lưu lâu dài thì làm ở bước sau.

### 7.2 Hành vi của AI

Lời nhắc hệ thống do backend dựng mỗi lượt, gồm:
1. Vai trò: kiến trúc sư quy trình đa agent cho AgentDev. Trả lời bằng ngôn ngữ của người dùng.
2. Nội dung `workspace/skills/brainstorming/SKILL.md`, cùng phần chuyển thể ngắn cho bối cảnh này: một câu hỏi mỗi lượt, hỏi mở trước, nhắc lại những gì đã hiểu, nêu rõ giả định. Phải xác nhận **tên quy trình**, **dạng** (đội / dây chuyền / trộn), **các vai trò và nhiệm vụ**, **quan hệ / thứ tự**, **điểm cần người duyệt**, **điều kiện rẽ nhánh / lặp** trước khi đề xuất bản tạo mới. Người dùng nói "cứ làm" thì đề xuất ngay với giả định nêu rõ.
3. **Tài liệu chuẩn YAML** viết tay, gọn, lưu trong repo (ví dụ `backend/agentdev/api/services/workflow_assistant_reference.md`):
   - các trường `graph` (id, description, start, end, nodes, edges);
   - các loại nút hay dùng (`agent`, `human`, `literal`, `passthrough`, `loop_counter`, `subgraph`) với trường bắt buộc;
   - cạnh với `condition`, `trigger`, `carry_data`;
   - khối `team` của agent lead, khối `skills.allow`;
   - quy ước tên node;
   - hai ví dụ ngắn: một đội, một dây chuyền có rẽ nhánh và vòng lặp.

   Builder lấy chính xác từ schema trong `agentdev/entity/configs/node/*` và `edge/*`.
4. Danh sách skill đang có (tên và mô tả một dòng) để AI chỉ gán skill tồn tại. Danh sách model của các kết nối đang đăng nhập, để gán `provider`/`name` mặc định hợp lệ cho từng agent (mặc định giống cách autobind đang làm).
5. Danh sách tên file quy trình đã có, để tránh trùng tên.
6. Ở chế độ quy trình này: toàn bộ YAML hiện tại của quy trình.

**Định dạng trả về**: mô hình trả về **một đối tượng JSON** (không có văn bản ngoài JSON):
```json
{
  "reply": "markdown hiển thị cho người dùng",
  "quick_replies": ["…"],
  "proposal": null | { "kind": "create" | "edit", "filename": "slug.yaml", "yaml": "…toàn bộ YAML…" }
}
```
- Khi chỉ hỏi hoặc giải thích: `proposal = null`.
- Khi sửa: `yaml` là toàn bộ tài liệu mới; backend tự tính khác biệt và merge.
- Parse lỗi (mô hình trả về văn bản thường) thì backend coi toàn bộ là `reply`, `proposal = null`.

**Vòng tự sửa**: có `proposal` thì backend chạy `validate_workflow_content` và `static_check_data`. Có FAIL thì backend gửi lại cho mô hình (cùng hội thoại, thêm một tin nhắn "bản đề xuất bị lỗi: …, hãy sửa") **tối đa 2 lần**. Vẫn lỗi thì trả về `reply` kèm thông báo không tạo được bản hợp lệ và danh sách lỗi, không có thẻ Áp dụng. WARN (ví dụ chưa gắn được kết nối) vẫn cho áp dụng, nhưng hiện cảnh báo trên thẻ.

**Kiểm tra phía backend khi sửa**: backend tính khác biệt **đến từng trường** (nút/cạnh thêm, xóa; với nút đổi thì liệt kê trường nào đổi, ví dụ `role`, `name`, `team.members`). Thẻ đề xuất liệt kê đầy đủ, nên không có thay đổi nào âm thầm. Nút/cạnh bị xóa hoặc đổi mà tin nhắn người dùng không nhắc tên thì được tô cảnh báo ("Bản này cũng đổi role của X"). Lời nhắc yêu cầu AI chép nguyên văn mọi phần không được yêu cầu sửa và giữ nguyên anchor/alias. Không tự hoàn nguyên (quyết định của mình).

**Điều chỉnh skill brainstorming**: SKILL.md gốc có các bước như viết file thiết kế, commit, gọi skill khác. Những bước này không hợp với lời gọi một lần chỉ trả JSON. Phần chuyển thể **ghi đè** các bước đó: chỉ giữ cách hỏi (một câu mỗi lượt, hỏi mở, nhắc lại, nêu giả định). "Bản thiết kế" ở đây chính là thẻ đề xuất.

**Công cụ (tooling)**: `static_check` báo FAIL khi gặp tên công cụ không tồn tại. Vì vậy tài liệu chuẩn có thêm danh mục công cụ đang có (tên và mô tả một dòng, lấy từ registry công cụ), và AI chỉ được dùng tên trong danh mục đó.

**Phạm vi file**: mỗi đề xuất chỉ là **một file** quy trình. Cần đội con thì AI dùng `subgraph` trỏ tới quy trình đã có hoặc graph viết trong cùng file, không tạo file mới (quyết định của mình).

### 7.3 Backend

Service mới `backend/agentdev/api/services/workflow_assistant.py` và route mới `backend/agentdev/api/routes/workflow_assistant.py`:

- `GET /api/workflow-assistant/providers` → danh sách `{vendor: "anthropic"|"openai", label: "Claude"|"Codex", connection_id, model, available}` lấy từ các kết nối CLI/OAuth đã đăng nhập.
- `POST /api/workflow-assistant/chat` với body `{vendor, workflow: string|null, messages: [{role, content}], pending_yaml?, base_hash?}` → `{reply, quick_replies, proposal: {kind, filename, yaml, base_hash, diff_summary, warnings, checks} | null, model_used}`, hoặc lỗi `{error: "quota_exhausted" | "not_signed_in" | "timeout" | ..., message}`.
  - Stateless: frontend gửi lại toàn bộ lịch sử mỗi lượt. Backend cắt bớt các lượt cũ nếu quá dài, nhưng luôn giữ tin nhắn đầu tiên của người dùng.
  - Chạy lời gọi mô hình trong threadpool, timeout khoảng 180 giây.
  - Hết quota (người dùng đã quyết): **dừng, không tự chuyển**. Trả lỗi có mã `quota_exhausted`. Chat hiện thông báo rõ "Claude đã hết quota" kèm nút chuyển nhanh sang mô hình còn lại (nếu đã đăng nhập). Bấm nút thì gửi lại đúng lượt đó bằng mô hình mới. Không dùng `pick_fallback`. Lưu ý: Claude và Codex chỉ đăng nhập qua CLI, và mỗi máy chỉ có một phiên đăng nhập CLI cho mỗi vendor. Vì vậy không có "tài khoản khác cùng vendor" để chuyển sang. `pick_fallback` cũng ưu tiên chuyển sang vendor khác.
  - Body có thêm `pending_yaml` (bản đề xuất chưa áp dụng gần nhất, nếu có). Khi người dùng muốn chỉnh tiếp bản đề xuất, AI làm tiếp từ bản đó. `diff_summary` và các cảnh báo luôn so với **file đã lưu**.
- `POST /api/workflow-assistant/cancel` (hoặc hủy theo request id) để nút Dừng kết thúc lời gọi CLI (`cli_cancel.py` đã có).
- Áp dụng **không** cần endpoint mới: frontend gọi `postYaml` (tạo) hoặc `mergeWorkflowDocument` (sửa). Trước khi merge, frontend so `base_hash` với nội dung hiện tại để phát hiện xung đột. Builder có thể chuyển việc so hash sang backend nếu thấy gọn hơn.
- Tách `static_check` thành `static_check_data(data)`.

### 7.4 Frontend

- `frontend/src/components/workflow/assistant/WorkflowAssistantPanel.vue`: bảng chat, ô chọn mô hình, trạng thái.
- `frontend/src/components/workflow/assistant/ProposalCard.vue`: tóm tắt, xem trước, YAML, Áp dụng/Bỏ qua.
- Phần xem trước dùng lại `WorkflowNode`/`WorkflowEdge` trong một Vue Flow chỉ đọc. Có thể tách một component `WorkflowGraphPreview.vue` nhỏ khỏi `WorkflowView.vue`.
- State (lịch sử theo ngữ cảnh, đề xuất hiện tại, vendor đã chọn) nằm trong một composable `useWorkflowAssistant.js`. Vendor đã chọn nhớ trong localStorage.
- Hàm client mới trong `api/client.js`.
- Khóa i18n cho cả en/vi/zh.
- Sau khi áp dụng, phát thông báo qua `workflowSync` để danh sách và canvas ở các tab khác cập nhật.

### 7.5 Kiểm thử (bắt buộc)

- **Backend (pytest)**, mô hình được giả lập:
  - parse JSON / văn bản thường;
  - vòng tự sửa (lần 1 lỗi, lần 2 đúng; cả 3 lần lỗi);
  - tính `diff_summary`;
  - cảnh báo xóa ngoài yêu cầu;
  - hết quota thì trả `quota_exhausted`, không tự chuyển;
  - chỉnh tiếp từ `pending_yaml`;
  - từ chối tên file không hợp lệ hoặc trùng;
  - `static_check_data` cho kết quả giống `static_check`.
- **Kiểm tra chất lượng thật** (chạy tay, ghi lại kết quả): với cả Claude và Codex, (a) tạo một đội từ mô tả, (b) tạo một dây chuyền có rẽ nhánh và vòng lặp, (c) hỏi giải thích `software_company`, (d) sửa "thêm một QA sau Frontend" trên một bản sao. Mỗi lần đều phải ra YAML qua `static_check`, mở được trên canvas, và với (d) không đổi phần khác.
- **Frontend**: chạy app, thử luồng tạo → áp dụng → mở canvas, và luồng sửa → xung đột → làm lại.

## 8. Những gì người dùng đã quyết định

- Hỗ trợ cả dạng đội có trưởng nhóm, dạng dây chuyền linh hoạt và dạng trộn.
- Cùng khung chat vừa tạo mới, vừa giải thích, vừa sửa quy trình có sẵn.
- AI hỏi lại theo tinh thần brainstorming và xác nhận tên quy trình cùng các thông tin quan trọng.
- Chọn được Claude hoặc Codex.
- Sửa thì xem trước rồi bấm "Áp dụng" mới lưu.
- Hết quota thì dừng và báo; người dùng tự chuyển mô hình.
- Cách làm: A.

## 9. Quyết định của mình (người dùng có thể đổi)

- Bảng chat trượt ra bên phải thay vì hộp thoại giữa màn hình, để vừa chat vừa nhìn sơ đồ.
- Lịch sử chat chỉ giữ trong phiên trình duyệt, chưa lưu xuống ổ đĩa.
- Mỗi đề xuất chỉ một file; không tạo file subgraph mới.
- Thay đổi ngoài yêu cầu thì cảnh báo đến từng trường, không tự hoàn nguyên.
- Canvas có thay đổi chưa lưu thì chặn Áp dụng cho tới khi người dùng lưu hoặc bỏ.
- Tối đa 2 lần tự sửa lỗi.
- Có nút Hoàn tác sau khi áp dụng sửa.
- Trả lời không stream từng chữ. Mỗi lượt hiện trạng thái chờ rồi ra câu trả lời hoàn chỉnh, vì lời gọi trả về JSON có cấu trúc và cần kiểm tra trước khi hiện.

## 10. Để builder tự quyết

- Chi tiết nội dung lời nhắc hệ thống và tài liệu chuẩn YAML (phải khớp schema thật).
- Cách tính và hiển thị diff, thuật toán tự sắp bố cục xem trước.
- Vị trí chính xác của nút trên thanh công cụ, chi tiết giao diện trong khuôn khổ §7.1.
- Giới hạn cắt bớt lịch sử hội thoại.
