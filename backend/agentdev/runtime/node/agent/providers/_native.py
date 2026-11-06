"""Native agent mode for the CLI providers: the vendor CLI's own agent loop works in the project folder.

In this mode the node gets no AgentDev tools. ``claude -p`` / ``codex exec`` run with the session's
project workspace as their working directory and use their built-in file tools; the final text of the
run is the node's answer. The executor builds a :class:`NativeRunContext` (workspace root, effective
shell permission, turn cap, tool-activity callback) and passes it to ``call_model(native=...)``.
"""

from __future__ import annotations

import json
import os
import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

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
        "- Stay inside this folder: never read or change files outside it (attached files listed below and the "
        "SKILL.md files of your listed skills are the only exceptions, and are read-only input).",
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


def _event(line: str) -> Optional[Dict[str, Any]]:
    line = (line or "").strip()
    if not line.startswith("{"):
        return None
    try:
        event = json.loads(line)
    except ValueError:
        return None
    return event if isinstance(event, dict) else None


def _jsonl(stdout: str):
    for line in (stdout or "").splitlines():
        event = _event(line)
        if event is not None:
            yield event


def native_calls_of_listed_tools(stdout: str, names: Any) -> List[Tuple[str, Dict[str, Any]]]:
    """Tool calls the model made natively (stream ``tool_use`` blocks) for tools that only exist in the host protocol.

    The CLI answers those with "No such tool available" and a small model then often ends with a plain text
    reply, so the host never sees the call. Only names in ``names`` count (never a built-in tool); repeats of the
    same call (the model retrying) are merged. Order is kept.
    """
    known = set(names)
    found: List[Tuple[str, Dict[str, Any]]] = []
    seen: set = set()
    for event in _jsonl(stdout):
        if event.get("type") != "assistant":
            continue
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_use" or block.get("name") not in known:
                continue
            args = block.get("input") if isinstance(block.get("input"), dict) else {}
            name, args = _reshape_rescued_call(block["name"], args, known)
            key = (name, json.dumps(args, sort_keys=True, default=str))
            if key not in seen:
                seen.add(key)
                found.append((name, args))
    return found


def _reshape_rescued_call(name: str, args: Dict[str, Any], known: Set[str]) -> Tuple[str, Dict[str, Any]]:
    """Map a native ``delegate_parallel`` call onto the host tool that matches its shape.

    The model often sends ``tasks`` as a JSON string, or as a single task. One task is ``delegate_task``
    (``delegate_parallel`` itself still requires two or more); several tasks stay parallel with a real list.
    """
    if name != "delegate_parallel":
        return name, args
    tasks = args.get("tasks")
    if isinstance(tasks, str):
        try:
            tasks = json.loads(tasks)
        except ValueError:
            return name, args
    if isinstance(tasks, dict):
        tasks = [tasks]
    if not isinstance(tasks, list):
        return name, args
    if len(tasks) == 1 and isinstance(tasks[0], dict) and "delegate_task" in known:
        only = tasks[0]
        return "delegate_task", {"member": only.get("member", ""), "task": only.get("task", "")}
    return name, {**args, "tasks": tasks}



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


def describe_tool_failure(name: str, result: Any, arguments: Any, limit: int = 300) -> str:
    """Why a built-in tool call failed: the command (or file) and the first lines of its error output."""
    args = arguments if isinstance(arguments, dict) else {}
    target = args.get("command") or args.get("file_path") or args.get("path") or args.get("pattern") or ""
    target = trim(" ".join(str(target).split()), 120)
    text = " | ".join(line.strip() for line in str(result or "").splitlines() if line.strip())
    reason = trim(text, limit) or "no error output (non-zero exit or tool error)"
    return f"`{target}` -> {reason}" if target else reason


class ClaudeStreamReader:
    """Incremental parser of ``--output-format stream-json`` events.

    ``feed(event)`` reports tool use / tool result pairs to ``native.on_tool`` as ``claude:<Tool>`` calls the
    moment they are seen; ``result`` (final ``result`` event) and ``changed`` (files written by edit tools)
    accumulate. Each event is fed once, so each call is reported once.
    """

    def __init__(self, native: Optional[NativeRunContext]):
        self.native = native
        self.result: Optional[Dict[str, Any]] = None
        self.changed: List[str] = []
        self._pending: Dict[str, Dict[str, Any]] = {}
        self._message_usage: Dict[str, Dict[str, Any]] = {}

    def partial_usage(self) -> Dict[str, int]:
        """Token usage seen so far, from the assistant events: what a call that never reached its final
        ``result`` event (timeout, kill, cancel) still spent. One entry per message id (the CLI repeats it)."""
        total = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        for usage in self._message_usage.values():
            for key in total:
                try:
                    total[key] += int(usage.get(key) or 0)
                except (TypeError, ValueError):
                    pass
        return total

    def feed(self, event: Dict[str, Any]) -> None:
        native = self.native
        kind = event.get("type")
        if kind == "result":
            self.result = event
            return
        message = event.get("message")
        if kind == "assistant" and isinstance(message, dict) and isinstance(message.get("usage"), dict):
            self._message_usage[str(message.get("id") or len(self._message_usage))] = message["usage"]
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict):
                continue
            if kind == "assistant" and block.get("type") == "tool_use":
                name = str(block.get("name") or "tool")
                args = block.get("input") if isinstance(block.get("input"), dict) else {}
                self._pending[str(block.get("id") or "")] = {"name": name, "args": args}
                if name in _CLAUDE_EDIT_TOOLS:
                    path = args.get("file_path") or args.get("notebook_path")
                    if isinstance(path, str) and path and path not in self.changed:
                        self.changed.append(path)
                if native is not None:
                    native.emit("before", f"claude:{name}", None, None, {"arguments": _compact(args)})
            elif kind == "user" and block.get("type") == "tool_result":
                call = self._pending.pop(str(block.get("tool_use_id") or ""), None)
                if call is None or native is None:
                    continue
                ok = not bool(block.get("is_error"))
                native.emit(
                    "after", f"claude:{call['name']}", ok, trim(_tool_result_text(block.get("content")), 2000),
                    {"arguments": _compact(call["args"])},
                )


def read_claude_stream(stdout: str, native: Optional[NativeRunContext]) -> tuple[Optional[Dict[str, Any]], List[str]]:
    """Parse a whole ``--output-format stream-json`` output.

    Returns (final ``result`` event or None, files written by edit tools). With ``native`` the tool calls
    are reported to ``native.on_tool`` too; pass None when :class:`LiveEvents` already reported them.
    """
    reader = ClaudeStreamReader(native)
    for event in _jsonl(stdout):
        reader.feed(event)
    return reader.result, reader.changed


def _codex_call(item: Dict[str, Any]) -> Optional[Tuple[str, Dict[str, Any]]]:
    kind = item.get("type")
    if kind == "file_change":
        return "codex:apply_patch", {"changes": item.get("changes")}
    if kind == "command_execution":
        return "codex:shell", {"command": item.get("command")}
    if kind in ("mcp_tool_call", "web_search"):
        return f"codex:{kind}", {k: v for k, v in item.items() if k not in ("id", "type")}
    return None


class CodexActivityReader:
    """Incremental reader of ``codex exec --json`` events.

    ``item.started`` reports a call as begun; ``item.completed`` reports it finished (and begun first, when
    its start was not seen). ``changed`` collects the paths of completed file changes.
    """

    def __init__(self, native: Optional[NativeRunContext]):
        self.native = native
        self.changed: List[str] = []
        self._started: Set[str] = set()

    def feed(self, event: Dict[str, Any]) -> None:
        kind = event.get("type")
        if kind not in ("item.started", "item.completed"):
            return
        item = event.get("item")
        if not isinstance(item, dict):
            return
        call = _codex_call(item)
        if call is None:
            return
        name, args = call
        item_id = str(item.get("id") or "")
        native = self.native
        if kind == "item.started":
            if item_id and item_id not in self._started:
                self._started.add(item_id)
                if native is not None:
                    native.emit("before", name, None, None, {"arguments": _compact(args)})
            return
        item_type = item.get("type")
        if item_type == "file_change":
            paths = [c.get("path") for c in item.get("changes") or [] if isinstance(c, dict) and c.get("path")]
            for path in paths:
                if path not in self.changed:
                    self.changed.append(path)
            ok = item.get("status") in (None, "completed")
            output: Any = ", ".join(paths)
        elif item_type == "command_execution":
            ok = item.get("exit_code") in (None, 0) and item.get("status") != "failed"
            output = trim(str(item.get("aggregated_output") or ""), 2000)
        else:
            ok, output = True, None
        started = bool(item_id) and item_id in self._started
        self._started.discard(item_id)
        if native is None:
            return
        if not started:
            native.emit("before", name, None, None, {"arguments": _compact(args)})
        native.emit("after", name, ok, output, {"arguments": _compact(args)})


def read_codex_activity(stdout: str, native: Optional[NativeRunContext]) -> List[str]:
    """Report the Codex items (commands, file changes, MCP/web calls) of a whole output; return changed paths."""
    reader = CodexActivityReader(native)
    for event in _jsonl(stdout):
        reader.feed(event)
    return reader.changed


class LiveEvents:
    """Feeds a CLI's JSON-lines stdout to a reader (:class:`ClaudeStreamReader` / :class:`CodexActivityReader`)
    while the CLI runs, so tool calls reach the UI as they happen instead of all at once at the end.

    ``push`` is the ``on_line`` hook of ``run_cli``. It runs on the stdout reader thread and only queues the
    line, so a slow listener (a WebSocket send) never stalls the pipe; one pump thread feeds the reader in
    order (``native.emit`` -> log manager is lock-protected and the WebSocket send is thread-safe).
    ``finish(stdout)`` waits for the pump, then feeds whatever it did not see (all of it when the output was
    not streamed), so every line is fed exactly once. ``abort()`` (cancel / timeout / error) stops at once.
    """

    FINISH_WAIT = 30.0

    def __init__(self, reader: Any):
        self.reader = reader
        self._queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._consumed = 0  # characters of stdout fed by the pump (read only after it has stopped)
        self._stopped = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def push(self, line: str) -> None:
        with self._lock:
            if self._stopped:
                return
            if self._thread is None:
                self._thread = threading.Thread(target=self._pump, name="agentdev-cli-events", daemon=True)
                self._thread.start()
            self._queue.put(line)

    def _pump(self) -> None:
        while True:
            line = self._queue.get()
            if line is None or self._stopped:
                return
            self._consumed += len(line)
            self._feed(line)

    def _feed(self, line: str) -> None:
        event = _event(line)
        if event is None:
            return
        try:
            self.reader.feed(event)
        except Exception:  # reporting is best effort and must never fail the run
            pass

    def finish(self, stdout: str) -> None:
        # run_cli has returned: the stdout reader thread is done, so no push races this.
        with self._lock:
            thread, closed = self._thread, self._stopped
        if closed:
            return
        if thread is not None:
            self._queue.put(None)
            thread.join(self.FINISH_WAIT)
            if thread.is_alive():  # listener stuck: stop reporting rather than race the pump
                self._stopped = True
                return
        self._stopped = True
        for line in (stdout or "")[self._consumed:].splitlines():
            self._feed(line)

    def abort(self) -> None:
        with self._lock:
            self._stopped = True
            if self._thread is not None:
                self._queue.put(None)


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
