# Agent Node

The Agent node is the most fundamental node type in the AgentDev platform, used to invoke Large Language Models (LLMs) for text generation, conversation, reasoning, and other tasks. It runs on signed-in accounts (Claude, ChatGPT, Gemini) created on the web console's Connections page, and can be configured with advanced features like tool calling, chain-of-thought, and memory.

## Configuration

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `connection` | string | No | Default connection | Account connection id from the Connections page (form field "Account connection"; the default connection is preselected). Omit it to bind automatically at run time (see below) |
| `provider` | string | No | - | Vendor hint kept by older workflows (`anthropic`, `openai`, `gemini`); only used to pick an account when `connection` is missing |
| `name` | string | Yes | - | Model name, e.g., `claude-opus-5-5`, `gpt-6.1-sol`, `gemini-2.5-flash`. An unset `${MODEL_NAME}`-style placeholder falls back to the account's default model |
| `role` | text | No | - | System prompt |
| `params` | dict | No | `{}` | Model call parameters (temperature, top_p, etc.) |
| `tooling` | object | No | - | Tool calling configuration, see [Tooling Module](../modules/tooling/README.md) |
| `thinking` | object | No | - | Chain-of-thought configuration, e.g., chain-of-thought, reflection |
| `memories` | list | No | `[]` | Memory binding configuration, see [Memory Module](../modules/memory.md) |
| `skills` | object | No | - | Agent Skills discovery and built-in skill activation/file-read tools |
| `retry` | object | No | - | Automatic retry strategy configuration |

There are no API keys: `api_key` and `base_url` no longer exist and are ignored if present in old YAML.

### Account Connections

Sign in to accounts on the Connections page of the web console:

| Account | Provider | Sign-in |
|---------|----------|---------|
| Claude | `claude_cli` | Local `claude` CLI (Claude Code login) |
| ChatGPT | `codex_cli` | Local `codex` CLI (`codex login` with ChatGPT sign-in; a Codex logged in with an API key is rejected) |
| Gemini | `gemini` | Google sign-in (the server needs `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `PUBLIC_BASE_URL`) |

At run time a node without `connection` is bound automatically to the default connection (Claude unless changed on the Connections page), otherwise to a signed-in account of the same vendor as its `provider` hint (`anthropic` → Claude, `openai` → Codex, `gemini` → Google), otherwise to any signed-in account (the model is then switched to that account's default). If no account is signed in, the run fails with a message pointing to the Connections page.

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
      connection: <your-connection-id>
      name: claude-opus-5-5
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
      connection: <your-connection-id>
      name: claude-opus-5-5
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
      connection: <your-connection-id>
      name: claude-opus-5-5
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
      connection: <your-connection-id>
      name: claude-opus-5-5
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

Requires a Gemini account signed in with Google on the Connections page.

```yaml
nodes:
  - id: Vision Agent
    type: agent
    config:
      connection: <your-gemini-connection-id>
      name: gemini-2.5-flash-image
      role: You need to generate corresponding image content based on user input.
```

### Using Claude and ChatGPT (CLI accounts)

Claude accounts run through the local `claude` CLI (`claude_cli` provider) and ChatGPT accounts through the local `codex` CLI (`codex_cli` provider). Both support tool use (function tools, MCP tools, skills); Codex enforces a JSON reply schema for tool calls.

```yaml
nodes:
  - id: Claude Agent
    type: agent
    config:
      connection: <your-claude-connection-id>
      name: claude-opus-5-5          # also: claude-sonnet-5-5, claude-haiku-5-5, claude-fable-5-1
      role: You are a helpful assistant.
      tooling:
        - type: function
          config:
            auto_load: true
            tools:
              - name: get_weather
      params:
        timeout: 300
```

- Credentials come from the signed-in CLI account; there is no key to configure in YAML or `.env`.
- `params.timeout`: CLI call timeout in seconds (default `300`).
- See `workspace/workflows/software_company.yaml` for a runnable example (it uses the `provider: anthropic` vendor hint, so it binds to a signed-in Claude account automatically).

### Configuring Retry Strategy

```yaml
nodes:
  - id: Robust Agent
    type: agent
    config:
      connection: <your-connection-id>
      name: claude-opus-5-5
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
      connection: <your-connection-id>
      name: claude-opus-5-5
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
