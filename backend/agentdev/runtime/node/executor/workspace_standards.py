"""Project standards for agents that build things in the run's project workspace.

Added to the system prompt only for agents that can write there (native CLI mode, or file/shell tools),
so pure chat agents do not pay the tokens. Static text: it sits in the cached prefix of the prompt.
"""

from collections.abc import Iterable

from agentdev.utils.reserved_ports import RESERVED_PORTS

# Tools that create, change or run things in the project workspace (workspace/functions/function_calling).
WORKSPACE_WRITE_TOOLS = frozenset(
    {
        "save_file",
        "apply_text_edits",
        "edit_file",
        "multi_edit",
        "create_folder",
        "delete_path",
        "rename_path",
        "copy_path",
        "move_path",
        "run_shell_command",
        "execute_code",
        "uv_run",
        "init_python_env",
        "install_python_packages",
    }
)

_PORTS = ", ".join(str(port) for port in RESERVED_PORTS)

WORKSPACE_STANDARDS = f"""# Project workspace standards
Everything you build must look like a professional, conventional project for its stack.
- Structure: pick the idiomatic layout for the stack and match it to the request size. A small script stays small (one file plus README); do not over-engineer. An app gets real layering: e.g. separate `client/` and `server/`, or `src/` with feature/module folders, plus `config/` and `tests/`. Follow the conventions already in an existing project instead of imposing new ones.
- Clear names (kebab-case or the stack's convention); no stray files in the root, no `final2.js`, no leftover scratch or debug files.
- README.md: purpose, a short structure tree, exact install / run / test commands, required env vars.
- Add a stack-appropriate `.gitignore` (dependencies, build output, `.env`, caches).
- Config through environment variables; commit `.env.example` with placeholders, never real secrets.
- Ports: read the port from the `PORT` env var with a default in 3000-3999 or 8000-8999. NEVER use {_PORTS}: AgentDev itself runs on them (also listed in the `AGENTDEV_RESERVED_PORTS` env var). For Vite never set `server.port` to 5173; set e.g. `server: {{ port: Number(process.env.PORT) || 3000, strictPort: false }}`.
- Do not leave long-running processes (dev servers, watchers) running. If you start one to test, use a free non-reserved port and stop it before you finish.
- Write only inside the project workspace. Never touch the AgentDev installation, its files or its processes.
- Non-code deliverables (scripts / kịch bản, docs, reports, plans) go in clearly named folders with ordered, descriptive file names (e.g. `scripts/01-<slug>.md`, `docs/architecture.md`) and an index README listing them.
- Tests live in the stack's standard place (`tests/`, `__tests__/`, `*.test.ts`) and run with one documented command."""


def writes_workspace(native: bool, tool_names: Iterable[str]) -> bool:
    """True when the agent can write to the project workspace: native CLI mode or a write/run tool."""
    return native or any(name in WORKSPACE_WRITE_TOOLS for name in tool_names)
