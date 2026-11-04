# Agent 节点

Agent 节点是 AgentDev 平台中最核心的节点类型，用于调用大语言模型 (LLM) 完成文本生成、对话、推理等任务。它运行在 Web 控制台 Connections（连接）页面创建的已登录账号（Claude、ChatGPT、Gemini）上，并可配置工具调用、思维链、记忆等高级功能。

## 配置项

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `connection` | string | 否 | 默认连接 | Connections 页面中的账号连接 ID（节点表单字段 "Account connection"，默认连接会被预先选中）。省略时在运行时自动绑定（见下文） |
| `provider` | string | 否 | - | 旧工作流保留的厂商提示（`anthropic`、`openai`、`gemini`），仅在缺少 `connection` 时用于挑选账号 |
| `name` | string | 是 | - | 模型名称，如 `claude-opus-5-5`、`gpt-6.1-sol`、`gemini-3-flash-preview`。未在任何地方设置的 `${MODEL_NAME}` 类占位符会回退为该账号的默认模型 |
| `role` | text | 否 | - | 系统提示词 (System Prompt) |
| `params` | dict | 否 | `{}` | 模型调用参数（temperature、top_p 等） |
| `tooling` | object | 否 | - | 工具调用配置，详见 [Tooling 模块](../modules/tooling/README.md) |
| `thinking` | object | 否 | - | 思维链配置，如 chain-of-thought、reflection |
| `memories` | list | 否 | `[]` | 记忆绑定配置，详见 [Memory 模块](../modules/memory.md) |
| `skills` | object | 否 | - | Agent Skills 发现配置，以及内置的技能激活/文件读取工具 |
| `retry` | object | 否 | - | 自动重试策略配置 |

不再使用 API 密钥：`api_key` 与 `base_url` 字段已移除，旧 YAML 中若存在会被忽略。

### 账号连接

在 Web 控制台的 Connections（连接）页面登录账号：

| 账号 | 提供商 | 登录方式 |
|------|--------|----------|
| Claude | `claude_cli` | 本地 `claude` CLI（Claude Code 登录） |
| ChatGPT | `codex_cli` | 本地 `codex` CLI（`codex login`，使用 ChatGPT 登录；以 API key 登录的 Codex 会被拒绝） |
| Gemini | `gemini` | Google 账号登录（服务端需设置 `GOOGLE_OAUTH_CLIENT_ID`、`GOOGLE_OAUTH_CLIENT_SECRET`、`PUBLIC_BASE_URL`） |

运行时，未设置 `connection` 的节点会自动绑定到默认连接（除非在 Connections 页面修改，否则为 Claude）；否则绑定到与 `provider` 厂商提示相同厂商的已登录账号（`anthropic` → Claude，`openai` → Codex，`gemini` → Google）；再否则绑定到任一已登录账号（模型会切换为该账号的默认模型）。若没有任何已登录账号，运行会失败，并提示前往 Connections 页面。

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
      connection: <your-connection-id>
      name: claude-opus-5-5
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
      connection: <your-connection-id>
      name: claude-opus-5-5
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
      connection: <your-connection-id>
      name: claude-opus-5-5
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
      connection: <your-connection-id>
      name: claude-opus-5-5
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

需要先在 Connections（连接）页面使用 Google 账号登录 Gemini。

```yaml
nodes:
  - id: Vision Agent
    type: agent
    config:
      connection: <your-gemini-connection-id>
      name: gemini-2.5-flash-image
      role: 你需要根据用户的输入，生成相应的图像内容。
```

### 使用 Claude 与 ChatGPT（CLI 账号）

Claude 账号通过本地 `claude` CLI（`claude_cli` 提供商）运行，ChatGPT 账号通过本地 `codex` CLI（`codex_cli` 提供商）运行。两者都支持工具调用（函数工具、MCP 工具、Skills）；Codex 会强制使用 JSON 回复格式（schema）来返回工具调用。

```yaml
nodes:
  - id: Claude Agent
    type: agent
    config:
      connection: <your-claude-connection-id>
      name: claude-opus-5-5          # 也可用：claude-sonnet-5-5、claude-haiku-5-5、claude-fable-5-1
      role: 你是一个乐于助人的助手。
      tooling:
        - type: function
          config:
            auto_load: true
            tools:
              - name: get_weather
      params:
        timeout: 300
```

- 凭据来自已登录的 CLI 账号，无需在 YAML 或 `.env` 中配置任何密钥。
- `params.timeout`：CLI 调用超时（秒，默认 `300`）。
- 可运行示例见 `workspace/workflows/software_company.yaml`（其中使用 `provider: anthropic` 厂商提示，运行时会自动绑定到已登录的 Claude 账号）。

### 配置重试策略

```yaml
nodes:
  - id: Robust Agent
    type: agent
    config:
      connection: <your-connection-id>
      name: claude-opus-5-5
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
      connection: <your-connection-id>
      name: claude-opus-5-5
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
