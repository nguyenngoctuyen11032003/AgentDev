"""Native agent mode for the CLI providers: the vendor CLI's own agent loop works in the project folder.

In this mode the node gets no AgentDev tools. ``claude -p`` / ``codex exec`` run with the session's
project workspace as their working directory and use their built-in file tools; the final text of the
run is the node's answer. The executor builds a :class:`NativeRunContext` (workspace root, effective
shell permission, turn cap, tool-activity callback) and passes it to ``call_model(native=...)``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from agentdev.runtime.node.agent.providers._cli_common import StagedAttachment, trim

DEFAULT_NATIVE_TIMEOUT = 1800

# Claude Code built-in tools offered in native mode. Web, MCP, sub-agents and skills are never offered.
CLAUDE_NATIVE_FILE_TOOLS = ("Read", "Glob", "Grep", "Edit", "Write")
CLAUDE_SHELL_TOOL = "Bash"
_CLAUDE_EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

# (stage "before"/"after", tool name, success, result, details) -> None
ToolActivity = Callable[[str, str, Optional[bool], Any, Dict[str, Any]], None]


@dataclass
class NativeRunContext:
    workspace: str
    allow_commands: bool = False
    max_turns: int = 60
    on_tool: Optional[ToolActivity] = None

    def emit(self, stage: str, name: str, success: Optional[bool], result: Any, details: Dict[str, Any]) -> None:
        if self.on_tool is None:
            return
        try:
            self.on_tool(stage, name, success, result, details)
        except Exception:  # logging is best effort and must never fail the run
            pass


def absolutize_attachments(staged: List[StagedAttachment], staging_dir: str) -> bool:
    """Point staged files at absolute paths (they live outside the workspace). True when any file was staged."""
    any_file = False
    for item in staged:
        if item.rel_path:
            item.rel_path = os.path.join(staging_dir, item.rel_path).replace(os.sep, "/")
            any_file = True
    return any_file


def native_preamble(workspace: str, *, can_edit: bool, can_run_commands: bool, vendor: str) -> str:
    lines = [
        "[Native agent mode]",
        f"You are working directly in the project folder `{workspace}` (your current working directory). "
        "Use your own built-in tools to explore, read, search and edit the project files there.",
        "- Stay inside this folder: never read or change files outside it (attached files listed below are the "
        "only exception, and are read-only input).",
    ]
    if not can_edit:
        lines.append("- Your sandbox is read-only: you cannot change files. Investigate, then describe the exact "
                     "changes needed (file, location, new code).")
    if can_run_commands:
        lines.append("- You may run shell commands (tests, builds, linters) inside the project. Never run destructive "
                     "commands (deleting the repository, rewriting git history, pushing) and do not install global "
                     "software.")
    else:
        lines.append("- Shell commands are disabled in this run. Do not try to run tests or programs; verify by "
                     "reading the code and say which commands the user should run.")
    lines.append("- There is no user to ask during the run: make reasonable decisions and note assumptions.")
    lines.append("- When done, reply with a concise report: what you changed (files), how you verified it, and anything "
                 "left open. That report is your whole answer.")
    return "\n".join(lines)


def with_preamble(prompt: str, preamble: str) -> str:
    return preamble + "\n\n" + prompt if prompt else preamble


def _jsonl(stdout: str):
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            yield event


def _tool_result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts)
    return "" if content is None else str(content)


def read_claude_stream(stdout: str, native: Optional[NativeRunContext]) -> tuple[Optional[Dict[str, Any]], List[str]]:
    """Parse ``--output-format stream-json`` output.

    Returns (final ``result`` event or None, files written by edit tools). Tool use / tool result pairs
    are reported to ``native.on_tool`` as ``claude:<Tool>`` calls (after the run; best effort).
    """
    result: Optional[Dict[str, Any]] = None
    pending: Dict[str, Dict[str, Any]] = {}
    changed: List[str] = []
    for event in _jsonl(stdout):
        kind = event.get("type")
        if kind == "result":
            result = event
            continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if kind == "assistant" and block.get("type") == "tool_use":
                name = str(block.get("name") or "tool")
                args = block.get("input") if isinstance(block.get("input"), dict) else {}
                pending[str(block.get("id") or "")] = {"name": name, "args": args}
                if name in _CLAUDE_EDIT_TOOLS:
                    path = args.get("file_path") or args.get("notebook_path")
                    if isinstance(path, str) and path and path not in changed:
                        changed.append(path)
                if native is not None:
                    native.emit("before", f"claude:{name}", None, None, {"arguments": _compact(args)})
            elif kind == "user" and block.get("type") == "tool_result":
                call = pending.pop(str(block.get("tool_use_id") or ""), None)
                if call is None or native is None:
                    continue
                ok = not bool(block.get("is_error"))
                native.emit(
                    "after", f"claude:{call['name']}", ok, trim(_tool_result_text(block.get("content")), 2000),
                    {"arguments": _compact(call["args"])},
                )
    return result, changed


def read_codex_activity(stdout: str, native: Optional[NativeRunContext]) -> List[str]:
    """Report completed Codex items (commands, file changes, MCP/web calls) and return changed file paths."""
    changed: List[str] = []
    for event in _jsonl(stdout):
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "file_change":
            paths = [c.get("path") for c in item.get("changes") or [] if isinstance(c, dict) and c.get("path")]
            for path in paths:
                if path not in changed:
                    changed.append(path)
            name, args = "codex:apply_patch", {"changes": item.get("changes")}
            ok = item.get("status") in (None, "completed")
            output: Any = ", ".join(paths)
        elif kind == "command_execution":
            name, args = "codex:shell", {"command": item.get("command")}
            ok = item.get("exit_code") in (None, 0) and item.get("status") != "failed"
            output = trim(str(item.get("aggregated_output") or ""), 2000)
        elif kind in ("mcp_tool_call", "web_search"):
            name, args, ok, output = f"codex:{kind}", {k: v for k, v in item.items() if k not in ("id", "type")}, True, None
        else:
            continue
        if native is not None:
            native.emit("before", name, None, None, {"arguments": _compact(args)})
            native.emit("after", name, ok, output, {"arguments": _compact(args)})
    return changed


def changed_files_note(workspace: str, changed: List[str]) -> str:
    if not changed:
        return ""
    shown = []
    for path in changed[:50]:
        try:
            rel = os.path.relpath(path, workspace) if os.path.isabs(path) else path
        except ValueError:  # other drive on Windows
            rel = path
        shown.append(rel.replace(os.sep, "/"))
    more = f" (+{len(changed) - 50} more)" if len(changed) > 50 else ""
    return "[Files changed by the agent] " + ", ".join(shown) + more


def _compact(args: Any, limit: int = 2000) -> Any:
    text = json.dumps(args, ensure_ascii=False, default=str)
    return args if len(text) <= limit else text[:limit] + "..."
