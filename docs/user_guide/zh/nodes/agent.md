# Agent 节点

Agent 节点是 AgentDev 平台中最核心的节点类型，用于调用大语言模型 (LLM) 完成文本生成、对话、推理等任务。它支持多种模型提供商（OpenAI、Gemini、Anthropic Claude 等），并可配置工具调用、思维链、记忆等高级功能。

## 配置项

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `provider` | string | 是 | `openai` | 模型提供商名称，如 `openai`、`gemini`、`anthropic` |
| `name` | string | 是 | - | 模型名称，如 `gpt-4o`、`gemini-2.0-flash-001`、`claude-opus-5-5` |
| `role` | text | 否 | - | 系统提示词 (System Prompt) |
| `base_url` | string | 否 | 提供商默认 | API 端点 URL，支持 `${VAR}` 占位符 |
| `api_key` | string | 否 | - | API 密钥，建议使用环境变量 `${API_KEY}` |
| `params` | dict | 否 | `{}` | 模型调用参数（temperature、top_p 等） |
| `tooling` | object | 否 | - | 工具调用配置，详见 [Tooling 模块](../modules/tooling/README.md) |
| `thinking` | object | 否 | - | 思维链配置，如 chain-of-thought、reflection |
| `memories` | list | 否 | `[]` | 记忆绑定配置，详见 [Memory 模块](../modules/memory.md) |
| `skills` | object | 否 | - | Agent Skills 发现配置，以及内置的技能激活/文件读取工具 |
| `retry` | object | 否 | - | 自动重试策略配置 |

### 重试策略配置 (retry)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `true` | 是否启用自动重试 |
| `max_attempts` | int | `5` | 最大尝试次数（含首次） |
| `min_wait_seconds` | float | `1.0` | 最小退避等待时间 |
| `max_wait_seconds` | float | `6.0` | 最大退避等待时间 |
| `retry_on_status_codes` | list[int] | `[408,409,425,429,500,502,503,504]` | 触发重试的 HTTP 状态码 |

### Agent Skills 配置 (skills)

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | `false` | 是否为该节点启用 Agent Skills |
| `allow` | list[object] | `[]` | 可选的技能白名单，来源于项目级 `workspace/skills/` 目录；每个条目使用 `name` |

### Agent Skills 说明

- 技能统一从固定的项目级 `workspace/skills/` 目录中发现。
- 运行时会暴露两个内置技能工具：`activate_skill` 和 `read_skill_file`。
- `read_skill_file` 只有在对应技能已经激活后才可用。
- 技能 `SKILL.md` 的 frontmatter 可以包含可选的 `allowed-tools`，格式遵循 Agent Skills 规范，例如 `allowed-tools: execute_code`。
- 如果某个已选择技能依赖的工具没有绑定到当前节点，该技能会在运行时被跳过。
- 如果最终没有任何兼容技能可用，Agent 会被明确告知不要声称自己使用了技能。

## 何时使用

- **文本生成**：写作、翻译、摘要、问答等
- **智能对话**：多轮对话、客服机器人
- **工具调用**：让模型调用外部 API 或执行函数
- **复杂推理**：配合 thinking 配置进行深度思考
- **知识检索**：配合 memories 实现 RAG 模式

## 示例

### 基础配置

```yaml
nodes:
  - id: Writer
    type: agent
    config:
      provider: openai
      base_url: ${BASE_URL}
      api_key: ${API_KEY}
      name: gpt-4o
      role: |
        你是一位专业的技术文档撰写者，请用清晰简洁的语言回答问题。
      params:
        temperature: 0.7
        max_tokens: 2000
```

### 配置工具调用

```yaml
nodes:
  - id: Assistant
    type: agent
    config:
      provider: openai
      name: gpt-4o
      api_key: ${API_KEY}
      tooling:
        type: function  # 工具类型：function, mcp_remote, mcp_local
        config:
          tools:  # 函数工具列表，来自 workspace/functions/function_calling/ 目录
            - name: describe_available_files
            - name: load_file
          timeout: 20  # 可选：执行超时（秒）
```

### 配置 MCP 工具（Remote HTTP）

```yaml
nodes:
  - id: MCP Agent
    type: agent
    config:
      provider: openai
      name: gpt-4o
      api_key: ${API_KEY}
      tooling:
        type: mcp_remote
        config:
          server: http://localhost:8080/mcp  # MCP 服务器端点
          headers:  # 可选：自定义请求头
            Authorization: Bearer ${MCP_TOKEN}
          timeout: 30  # 可选：请求超时（秒）
```

### 配置 MCP 工具（Local stdio）

```yaml
nodes:
  - id: Local MCP Agent
    type: agent
    config:
      provider: openai
      name: gpt-4o
      api_key: ${API_KEY}
      tooling:
        type: mcp_local
        config:
          command: uvx  # 启动命令
          args: ["mcp-server-sqlite", "--db-path", "data.db"]
          cwd: ${WORKSPACE}  # 可选，一般不需要配置
          env:  # 可选，一般不需要配置
            DEBUG: "true"
          startup_timeout: 10  # 可选：启动超时（秒）
```

### Gemini 多模态配置

```yaml
nodes:
  - id: Vision Agent
    type: agent
    config:
      provider: gemini
      base_url: https://generativelanguage.googleapis.com
      api_key: ${GEMINI_API_KEY}
      name: gemini-2.5-flash-image
      role: 你需要根据用户的输入，生成相应的图像内容。
```

### 使用 Claude (Anthropic)

`anthropic` 提供商通过官方 `anthropic` Python SDK 调用 Claude 模型（Messages API，内部使用流式传输，长输出不会超时）。

```yaml
nodes:
  - id: Claude Agent
    type: agent
    config:
      provider: anthropic
      name: claude-opus-5-5          # 也可用：claude-sonnet-5-5、claude-haiku-5-5、claude-fable-5-1
      api_key: ${ANTHROPIC_API_KEY}  # 不要复用 ${API_KEY}/${BASE_URL}（它们是 OpenAI 的配置）
      # base_url: ${ANTHROPIC_BASE_URL}  # 可选；省略则使用官方端点
      role: 你是一个乐于助人的助手。
      tooling:
        - type: function
          config:
            auto_load: true
            tools:
              - name: get_weather
      params:
        effort: medium
        max_tokens: 16000
```

- `api_key`：优先使用节点配置，否则读取环境变量 `ANTHROPIC_API_KEY`。`base_url`：优先使用节点配置，否则使用 `ANTHROPIC_BASE_URL` 或官方端点。
- 支持：文本、系统提示词、工具调用（函数工具、MCP 工具、Skills）、并行工具调用、图片输入（png/jpeg/gif/webp）、PDF 输入、文本文件附件（以文本内联）、自适应思考 (adaptive thinking)、提示缓存（默认开启）、Token 用量统计（含缓存读/写 Token）。
- 可运行示例见 `workspace/workflows/demo_claude.yaml`。

| 参数 | 说明 |
|------|------|
| `max_tokens` | 最大输出 Token 数（默认 `64000`） |
| `effort` | `low` / `medium` / `high` / `xhigh` / `max`（映射为 `output_config.effort`） |
| `thinking` | 思考配置字典，原样透传；设为 `false` 或 `"off"` 则不发送 |
| `thinking_display` | `summarized` 或 `omitted` |
| `prompt_caching` | 是否启用提示缓存（布尔值，默认 `true`） |
| `tool_choice` | `auto` / `none` / `required`，或原生 Anthropic `tool_choice` 字典 |
| `stop_sequences` | 自定义停止序列列表 |
| `timeout` | 请求超时（秒） |
| `fallbacks` | 服务端拒答回退。使用官方端点时，`claude-opus-5-5`、`claude-fable-5-1`、`claude-opus-5`、`claude-sonnet-5-5` 默认为 `"default"`；设为 `false` 可关闭 |
| `metadata` | 请求元数据字典 |
| `inference_geo` | 推理地域 |
| `extra_headers` | 额外 HTTP 请求头 |
| `temperature` / `top_p` / `top_k` | 当前 Claude 模型不接受这些参数，会被丢弃并给出警告；设置 `allow_sampling_params: true` 可保留 |

**限制**

- 仅输出文本：不支持图片/音频/视频生成。
- 音频/视频输入不会原生发送，而是以文本描述的形式提供给模型。
- Anthropic 没有 embedding 模型：记忆模块的 `embedding` 仍需使用 `openai` 或 `local`。

### 配置重试策略

```yaml
nodes:
  - id: Robust Agent
    type: agent
    config:
      provider: openai
      name: gpt-4o
      api_key: ${API_KEY}
      retry:  # retry 默认启用，可以自己配置
        enabled: true
        max_attempts: 3
        min_wait_seconds: 2.0
        max_wait_seconds: 10.0
```

### 配置 Agent Skills

```yaml
nodes:
  - id: Skilled Agent
    type: agent
    config:
      provider: openai
      name: gpt-4o
      api_key: ${API_KEY}
      skills:
        enabled: true
        allow:
          - name: python-scratchpad
          - name: rest-api-caller
```

## 相关文档

- [Tooling 模块配置](../modules/tooling/README.md)
- [Memory 模块配置](../modules/memory.md)
- [工作流编排指南](../workflow_authoring.md)
