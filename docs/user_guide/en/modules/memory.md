# Memory Module Guide

This document explains AgentDev's memory system: memory list config, built-in store implementations, how agent nodes attach memories, and troubleshooting tips. Core code lives in `backend/agentdev/entity/configs/node/memory.py` and `backend/agentdev/runtime/node/agent/memory/*.py`.

## 1. Architecture
1. **Memory Store** – Declared under `memory[]` in YAML with `name`, `type`, and `config`. Types are registered via `register_memory_store()` and point to concrete implementations.
2. **Memory Attachment** – Referenced inside agent nodes via `AgentConfig.memories`. Each `MemoryAttachmentConfig` defines read/write strategy and retrieval stages.
3. **MemoryManager** – Builds store instances at runtime based on attachments and orchestrates `load()`, `retrieve()`, `update()`, `save()`.
4. **Retrieval** – `simple` and `file` stores retrieve by keyword relevance (BM25, works with Vietnamese/CJK text); no embedding or API key is needed. An optional `EmbeddingConfig` switches them to vector search with a local model (`EmbeddingFactory` only supports `provider: local`).

## 2. Memory Sample Config
```yaml
memory:
  - name: convo_cache
    type: simple
    config:
      memory_path: shared/simple.json   # relative -> storage/memory/shared/simple.json
  - name: project_docs
    type: file
    config:
      index_path: index/project_docs.json   # relative -> storage/memory/index/project_docs.json
      file_sources:
        - path: docs/
          file_types: [".md", ".mdx"]
          recursive: true
      # Optional: vector search with a local sentence-transformers model
      # embedding:
      #   provider: local
      #   params:
      #     model_path: /path/to/sentence-transformers-model
```

> [!NOTE]
> Mem0 memory has been removed. `type: mem0` now fails with an error saying Mem0 is no longer supported; use `simple`, `file`, or `blackboard` instead.

## 3. Built-in Store Comparison
| Type | Path | Highlights | Best for |
| --- | --- | --- | --- |
| `simple` | `node/agent/memory/simple_memory.py` | Optional disk persistence (JSON) after runs; BM25 keyword retrieval (FAISS + semantic rerank when a local embedding is configured); read/write capable. | Small conversation history, prototypes. |
| `file` | `node/agent/memory/file_memory.py` | Chunks files/dirs into an index (BM25 keyword search, or vectors with a local embedding), read-only, auto rebuilds when files change. | Knowledge bases, doc QA. |
| `blackboard` | `node/agent/memory/blackboard_memory.py` | Lightweight append-only log trimmed by time/count; no vector search. | Broadcast boards, pipeline debugging. |

All stores register through `register_memory_store()` so summaries show up in UI via `MemoryStoreConfig.field_specs()`.

## 4. MemoryAttachmentConfig Fields
| Field | Description |
| --- | --- |
| `name` | Target Memory Store name (must be unique inside `stores[]`). |
| `retrieve_stage` | Optional list limiting retrieval to certain `AgentExecFlowStage` values (`pre`, `plan`, `gen`, `critique`, etc.). Empty means all stages. |
| `top_k` | Number of items per retrieval (default 3). |
| `similarity_threshold` | Minimum similarity cutoff (`-1` disables filtering). |
| `read` / `write` | Whether this node can read from / write back to the store. |

Agent node example:
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
Execution order:
1. When the node enters `gen`, `MemoryManager` iterates attachments.
2. Attachments matching the stage and `read=true` call `retrieve()` on their store.
3. Retrieved items are formatted under a "===== Related Memories =====" block in the agent context.
4. After completion, attachments with `write=true` call `update()` and optionally `save()`.

## 5. Store Details
All memory stores persist a unified `MemoryItem` structure containing:
- `content_summary` – trimmed text used for keyword (or embedding) search.
- `input_snapshot` / `output_snapshot` – serialized message blocks (with base64 attachments) preserving multimodal context.
- `metadata` – store-specific telemetry (role, previews, attachment IDs, etc.).
This schema lets multimodal outputs flow into Memory/Thinking modules without extra plumbing.
### 5.1 SimpleMemory
- **Path** – `SimpleMemoryConfig.memory_path` (or `auto`). Defaults to in-memory.
- **Retrieval** – Build a query from the prompt, trim it, and rank stored summaries by BM25 keyword relevance. With a local `embedding`, it instead embeds the query, queries FAISS `IndexFlatIP`, then applies semantic rerank (Jaccard/LCS).
- **Write** – `update()` builds a `MemoryContentSnapshot` (text + blocks) for both input/output, deduplicates via hashed summary, embeds the summary (only when a local embedding is configured), and stores the snapshots/attachments metadata.
- **Tips** – Tune `max_content_length`, `top_k`, and `similarity_threshold` to avoid irrelevant context.

### 5.2 FileMemory
- **Config** – Requires at least one `file_sources` entry (paths, suffix filters, recursion, encoding). `index_path` is mandatory for incremental updates.
- **Indexing** – Scan files → chunk (default 500 chars, 50 overlap) → embed (only with a local embedding) → persist JSON with `file_metadata`.
- **Retrieval** – BM25 keyword relevance by default; FAISS cosine similarity when a local embedding is configured. Read-only; `update()` unsupported.
- **Maintenance** – `load()` checks file hashes and rebuilds if needed. Store `index_path` on persistent storage.

### 5.3 BlackboardMemory
- **Config** – `memory_path` (or `auto`) plus `max_items`. Creates the file in the session directory if missing.
- **Retrieval** – Returns the latest `top_k` entries ordered by time.
- **Write** – `update()` appends the latest snapshot (input/output blocks, attachments, previews). No embeddings are generated, so retrieval is purely recency-based.

## 6. EmbeddingConfig Notes
- Embedding is optional: without it, `simple` and `file` stores use BM25 keyword retrieval.
- Fields: `provider`, `model`, `params`. The only supported provider is `local`, which expects `params.model_path` and depends on `sentence-transformers`.
- `params` can include `use_chunking`, `chunk_strategy`, `max_length`, etc.
- OpenAI embeddings were removed: a legacy `provider: openai` embedding block is ignored with a warning (keyword retrieval is used instead).

## 7. Troubleshooting & Best Practices
- **Duplicate names** – The memory list enforces unique `memory[]` names. Duplicates raise `ConfigError`.
- **No embeddings needed** – `SimpleMemory` and `FileMemory` fall back to BM25 keyword retrieval without an embedding; add a `local` embedding only if you need vector search.
- **Permissions** – Ensure directories for `memory_path`/`index_path` are writable. Mount volumes when running inside containers.
- **Performance** – Pre-build large `FileMemory` indexes offline, use `retrieve_stage` to limit retrieval frequency, and tune `top_k`/`similarity_threshold` to balance recall vs. token cost.

## 8. Extending Memory
1. Implement a Config + Store (subclass `MemoryBase`).
2. Register via `register_memory_store("my_store", config_cls=..., factory=..., summary="...")` in `node/agent/memory/registry.py`.
3. Add `FIELD_SPECS`, then run `cd backend && uv run python -m scripts.export_design_template ...` so the frontend picks up the enum.
4. Update this guide or ship a README detailing configuration knobs and boundaries.
