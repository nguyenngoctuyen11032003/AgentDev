# Agent Node

The Agent node is the most fundamental node type in the AgentDev platform, used to invoke Large Language Models (LLMs) for text generation, conversation, reasoning, and other tasks. It supports multiple model providers (OpenAI, Gemini, Anthropic Claude, etc.) and can be configured with advanced features like tool calling, chain-of-thought, and memory.

## Configuration

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `provider` | string | Yes | `openai` | Model provider name, e.g., `openai`, `gemini`, `anthropic` |
| `name` | string | Yes | - | Model name, e.g., `gpt-4o`, `gemini-2.0-flash-001`, `claude-opus-5-5` |
| `role` | text | No | - | System prompt |
| `base_url` | string | No | Provider default | API endpoint URL, supports `${VAR}` placeholders |
| `api_key` | string | No | - | API key, recommend using environment variable `${API_KEY}` |
| `params` | dict | No | `{}` | Model call parameters (temperature, top_p, etc.) |
| `tooling` | object | No | - | Tool calling configuration, see [Tooling Module](../modules/tooling/README.md) |
| `thinking` | object | No | - | Chain-of-thought configuration, e.g., chain-of-thought, reflection |
| `memories` | list | No | `[]` | Memory binding configuration, see [Memory Module](../modules/memory.md) |
| `skills` | object | No | - | Agent Skills discovery and built-in skill activation/file-read tools |
| `retry` | object | No | - | Automatic retry strategy configuration |

### Retry Strategy Configuration (retry)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `true` | Whether to enable automatic retry |
| `max_attempts` | int | `5` | Maximum number of attempts (including first attempt) |
| `min_wait_seconds` | float | `1.0` | Minimum backoff wait time |
| `max_wait_seconds` | float | `6.0` | Maximum backoff wait time |
| `retry_on_status_codes` | list[int] | `[408,409,425,429,500,502,503,504]` | HTTP status codes that trigger retry |

### Agent Skills Configuration (skills)

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `enabled` | bool | `false` | Enable Agent Skills discovery for this node |
| `allow` | list[object] | `[]` | Optional allowlist of skills from the project-level `workspace/skills/` directory; each entry uses `name` |

### Agent Skills Notes

- Skills are discovered from the fixed project-level `workspace/skills/` directory.
- The runtime exposes two built-in skill tools: `activate_skill` and `read_skill_file`.
- `read_skill_file` only works after the relevant skill has been activated.
- Skill `SKILL.md` frontmatter may include optional `allowed-tools` using the Agent Skills spec format, for example `allowed-tools: execute_code`.
- If a selected skill requires tools that are not bound on the node, that skill is skipped at runtime.
- If no compatible skills remain, the agent is explicitly instructed not to claim skill usage.

## When to Use

- **Text generation**: Writing, translation, summarization, Q&A, etc.
- **Intelligent conversation**: Multi-turn dialogue, customer service bots
- **Tool calling**: Enable the model to call external APIs or execute functions
- **Complex reasoning**: Use with thinking configuration for deep thought
- **Knowledge retrieval**: Use with memories to implement RAG patterns

## Examples

### Basic Configuration

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
        You are a professional technical documentation writer. Please answer questions in clear and concise language.
      params:
        temperature: 0.7
        max_tokens: 2000
```

### Configuring Tool Calling

```yaml
nodes:
  - id: Assistant
    type: agent
    config:
      provider: openai
      name: gpt-4o
      api_key: ${API_KEY}
      tooling:
        type: function  # Tool type: function, mcp_remote, mcp_local
        config:
          tools:  # List of function tools from workspace/functions/function_calling/ directory
            - name: describe_available_files
            - name: load_file
          timeout: 20  # Optional: execution timeout (seconds)
```

### Configuring MCP Tools (Remote HTTP)

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
          server: http://localhost:8080/mcp  # MCP server endpoint
          headers:  # Optional: custom request headers
            Authorization: Bearer ${MCP_TOKEN}
          timeout: 30  # Optional: request timeout (seconds)
```

### Configuring MCP Tools (Local stdio)

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
          command: uvx  # Launch command
          args: ["mcp-server-sqlite", "--db-path", "data.db"]
          cwd: ${WORKSPACE}  # Optional, usually not needed
          env:  # Optional, usually not needed
            DEBUG: "true"
          startup_timeout: 10  # Optional: startup timeout (seconds)
```

### Gemini Multimodal Configuration

```yaml
nodes:
  - id: Vision Agent
    type: agent
    config:
      provider: gemini
      base_url: https://generativelanguage.googleapis.com
      api_key: ${GEMINI_API_KEY}
      name: gemini-2.5-flash-image
      role: You need to generate corresponding image content based on user input.
```

### Using Claude (Anthropic)

The `anthropic` provider calls Claude models through the official `anthropic` Python SDK (Messages API, streamed internally so long outputs do not time out).

```yaml
nodes:
  - id: Claude Agent
    type: agent
    config:
      provider: anthropic
      name: claude-opus-5-5          # also: claude-sonnet-5-5, claude-haiku-5-5, claude-fable-5-1
      api_key: ${ANTHROPIC_API_KEY}  # do NOT reuse ${API_KEY}/${BASE_URL} (those hold OpenAI values)
      # base_url: ${ANTHROPIC_BASE_URL}  # optional; omit to use the official endpoint
      role: You are a helpful assistant.
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

- `api_key`: node value if set, otherwise the `ANTHROPIC_API_KEY` environment variable. `base_url`: node value if set, otherwise `ANTHROPIC_BASE_URL` or the official endpoint.
- Supported: text, system prompts, tool use (function tools, MCP tools, skills), parallel tool calls, image input (png/jpeg/gif/webp), PDF input, text-file attachments (inlined as text), adaptive thinking, prompt caching (on by default), token usage including cache read/write tokens.
- See `workspace/workflows/demo_claude.yaml` for a runnable example.

| Param | Description |
|-------|-------------|
| `max_tokens` | Maximum output tokens (default `64000`) |
| `effort` | `low` / `medium` / `high` / `xhigh` / `max` (sent as `output_config.effort`) |
| `thinking` | Thinking config dict passed through as-is; `false` or `"off"` omits it |
| `thinking_display` | `summarized` or `omitted` |
| `prompt_caching` | Enable prompt caching (bool, default `true`) |
| `tool_choice` | `auto` / `none` / `required`, or a native Anthropic `tool_choice` dict |
| `stop_sequences` | List of custom stop sequences |
| `timeout` | Request timeout (seconds) |
| `fallbacks` | Server-side refusal fallback. Defaults to `"default"` on `claude-opus-5-5`, `claude-fable-5-1`, `claude-opus-5`, `claude-sonnet-5-5` with the official endpoint; `false` disables |
| `metadata` | Request metadata dict |
| `inference_geo` | Inference geography |
| `extra_headers` | Extra HTTP headers |
| `temperature` / `top_p` / `top_k` | Dropped with a warning (current Claude models reject them) unless `allow_sampling_params: true` |

**Limitations**

- Output is text only: no image/audio/video generation.
- Audio/video inputs are not sent natively; they are described to the model as text.
- Anthropic has no embedding model: memory `embedding` must keep using `openai` or `local`.

### Configuring Retry Strategy

```yaml
nodes:
  - id: Robust Agent
    type: agent
    config:
      provider: openai
      name: gpt-4o
      api_key: ${API_KEY}
      retry:  # Retry is enabled by default, you can customize it
        enabled: true
        max_attempts: 3
        min_wait_seconds: 2.0
        max_wait_seconds: 10.0
```

### Configuring Agent Skills

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

## Related Documentation

- [Tooling Module Configuration](../modules/tooling/README.md)
- [Memory Module Configuration](../modules/memory.md)
- [Workflow Authoring Guide](../workflow_authoring.md)
