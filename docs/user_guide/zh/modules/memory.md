# Memory 模块指南

本文档解释 AgentDev 的 Memory 体系：memory 列表配置、内置存储实现、Agent 节点如何引用记忆，以及排障建议。代码主要位于 `backend/agentdev/entity/configs/node/memory.py`、`backend/agentdev/runtime/node/agent/memory/*.py`。

## 1. 体系结构
1. **Memory Store**：在 YAML `memory[]` 中声明，包含 `name`、`type` 和 `config`。`type` 由 `register_memory_store()` 注册，并映射到具体实现。
2. **Memory Attachment**：在 Agent 节点（`AgentConfig.memories`）中引用 `MemoryAttachmentConfig`，指定读取/写入策略及检索阶段。
3. **MemoryManager**：运行期根据 Attachment+Store 构建 Memory 实例，负责 `load()`、`retrieve()`、`update()`、`save()`。
4. **检索**：`simple` 与 `file` 存储按关键词相关度（BM25，支持越南语/中日韩文本）检索，无需 embedding 或 API 密钥。可选的 `EmbeddingConfig` 可切换为使用本地模型的向量检索（`EmbeddingFactory` 仅支持 `provider: local`）。

## 2. Memory 配置示例
```yaml
memory:
  - name: convo_cache
    type: simple
    config:
      memory_path: shared/simple.json   # 相对路径 -> storage/memory/shared/simple.json
  - name: project_docs
    type: file
    config:
      index_path: index/project_docs.json   # 相对路径 -> storage/memory/index/project_docs.json
      file_sources:
        - path: docs/
          file_types: [".md", ".mdx"]
          recursive: true
      # 可选：使用本地 sentence-transformers 模型进行向量检索
      # embedding:
      #   provider: local
      #   params:
      #     model_path: /path/to/sentence-transformers-model
```

> [!NOTE]
> Mem0 记忆已被移除。`type: mem0` 现在会报错并提示不再支持 Mem0；请改用 `simple`、`file` 或 `blackboard`。

## 3. 内置 Memory Store 对比
| 类型 | 路径 | 特点 | 适用场景 |
| --- | --- | --- | --- |
| `simple` | `node/agent/memory/simple_memory.py` | 运行结束后可选择落盘（JSON）；使用 BM25 关键词检索（配置本地 embedding 时为 FAISS 向量搜索 + 语义重打分）；支持读写 | 小规模对话记忆、快速原型 |
| `file` | `node/agent/memory/file_memory.py` | 将指定文件/目录切片建立索引（BM25 关键词检索，或配置本地 embedding 时使用向量），只读；自动检测文件变更并更新索引 | 知识库、文档问答 |
| `blackboard` | `node/agent/memory/blackboard_memory.py` | 轻量附加日志，按时间/条数裁剪；不依赖向量检索 | 简易广播板、流水线调试 |

> 所有内置 store 都会在 `register_memory_store()` 中注册，摘要可通过 `MemoryStoreConfig.field_specs()` 在 UI 中展示。

## 4. MemoryAttachmentConfig 说明
| 字段 | 说明 |
| --- | --- |
| `name` | 引用的 Memory Store 名称（需在 `stores[]` 中存在且唯一）。|
| `retrieve_stage` | 可选数组，限制检索发生的阶段（`AgentExecFlowStage`：`pre`, `plan`, `gen`, `critique` 等）。缺省表示所有阶段。|
| `top_k` | 每次检索返回的条数，默认 3。|
| `similarity_threshold` | 过滤相似度下限（-1 表示不限制）。|
| `read` / `write` | 是否允许在该节点读取/写回此记忆。|

Agent 节点示例：
```yaml
nodes:
  - id: answer
    type: agent
    config:
      connection: <your-connection-id>
      name: claude-haiku-5-5
      prompt_template: answer_user
      memories:
        - name: convo_cache
          retrieve_stage: ["gen"]
          top_k: 5
          read: true
          write: true
        - name: project_docs
          read: true
          write: false
```
执行顺序：
1. `MemoryManager` 在节点进入 `gen` 阶段时，遍历 Attachments。
2. 满足阶段与 `read=true` 的 Attachment 调用对应 Memory Store 的 `retrieve()`。
3. 结果格式化并拼接为“===== 相关记忆 =====”文本写入 Agent 输入上下文。
4. 节点完成后，`write=true` 的 Attachment 将调用 `update()` 并在必要时 `save()`。

## 5. Store 细节
所有 Memory Store 都持久化统一的 `MemoryItem` 结构：
- `content_summary`：用于检索的精简文本；
- `input_snapshot` / `output_snapshot`：序列化的消息块（含 base64 附件），确保多模态上下文不会丢失；
- `metadata`：记录角色、输入预览、附件 ID 等附加信息。
这使得 Memory 与 Thinking 模块可以共享多模态内容，无需额外适配。
### 5.1 SimpleMemory
- **路径**：`SimpleMemoryConfig.memory_path`（可为 `auto`），缺省仅驻留内存。
- **检索**：
  1. 以 prompt 构建查询文本并做裁剪。
  2. 按 BM25 关键词相关度对已存摘要排序；若配置了本地 `embedding`，则改为生成向量 → FAISS `IndexFlatIP` 检索 → 语义重打分（Jaccard/LCS）。
- **写入**：`update()` 根据输入/输出生成 `MemoryContentSnapshot`，计算摘要哈希去重，再写入 snapshot + 附件元信息（仅在配置本地 embedding 时同时写入向量）。
- **适配建议**：控制 `max_content_length` 避免爆 context；结合 `top_k`/`similarity_threshold` 防止无关内容。

### 5.2 FileMemory
- **配置**：至少一个 `file_sources`（路径、后缀过滤、递归、编码）。`index_path` 必填，方便增量更新。
- **索引流程**：扫描文件 → 切片（默认 500 字符、重叠 50）→ Embedding（仅在配置本地 embedding 时）→ 写入 JSON（包括 `file_metadata`）。
- **检索**：默认使用 BM25 关键词相关度；配置本地 embedding 时使用 FAISS 余弦相似度。只读，不支持 `update()`。
- **维护**：`load()` 时校验文件哈希，必要时重建索引；建议将 `index_path` 放在持久卷。

### 5.3 BlackboardMemory
- **配置**：`memory_path`（可 `auto`）、`max_items`。若路径不存在则在 Session 目录内创建。
- **检索**：直接返回最近 `top_k` 条，按时间排序。
- **写入**：`update()` 以 append 方式存储最新的输入/输出 snapshot（文本 + 块 + 附件信息），不生成向量，适合事件流或人工批注。

## 6. EmbeddingConfig 提示
- Embedding 为可选项：未配置时，`simple` 与 `file` 存储使用 BM25 关键词检索。
- 字段：`provider`, `model`, `params`。唯一支持的 provider 是 `local`，需提供 `params.model_path`，依赖 `sentence-transformers`。
- `params` 支持 `use_chunking`, `chunk_strategy`, `max_length` 等自定义键。
- OpenAI embedding 已移除：旧的 `provider: openai` embedding 配置会被忽略并给出警告（改用关键词检索）。

## 7. 排错与最佳实践
- **重复命名**：内存列表会校验 `memory[]` 名称唯一；重复时抛出 `ConfigError`。
- **无需 embedding**：`SimpleMemory`/`FileMemory` 未配置 embedding 时使用 BM25 关键词检索；仅在需要向量检索时才添加 `local` embedding。
- **权限**：确保 `memory_path`/`index_path` 所在目录可写；容器化部署应挂载卷。
- **性能**：
  - 大型 FileMemory 建议离线构建索引并缓存。
  - 通过 `retrieve_stage` 控制检索次数，减少模型输入冗余。
  - 调整 `top_k`、`similarity_threshold` 以平衡召回与 token 成本。

## 8. 扩展自定义 Memory
1. 新建 Config + Store（继承 `MemoryBase`）。
2. 在 `node/agent/memory/registry.py` 中调用 `register_memory_store("my_store", config_cls=..., factory=..., summary="用途")`。
3. 补充 `FIELD_SPECS`，运行 `cd backend && uv run python -m scripts.export_design_template ...` 以让前端获取新枚举。
4. 更新本指南或附带 README，说明新 store 的配置项与边界条件。
