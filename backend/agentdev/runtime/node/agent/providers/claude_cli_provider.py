"""Claude provider backed by the user's logged-in ``claude`` CLI (print mode)."""

from __future__ import annotations

import hashlib
import json
import os
import logging
import re
import shutil
import uuid
from pathlib import Path
from typing import Any, List, Optional

from agentdev.paths import SKILLS_DIR
from agentdev.connections.cli_auth import find_cli
from agentdev.entity.messages import Message, MessageRole
from agentdev.entity.tool_spec import ToolSpec
from agentdev.runtime.node.agent import ModelProvider, ModelResponse
from agentdev.runtime.node.agent.providers._cli_common import (
    CliCancelled,
    CliClient,
    CliProviderError,
    CliRunState,
    CliSession,
    CliTimeoutError,
    TOOL_REPLY_SCHEMA,
    render_followup,
    session_reuse_enabled,
    split_conversation,
    attachments_section,
    stage_attachments,
    build_tool_preamble,
    flatten_conversation,
    parse_tool_reply,
    make_tempdir,
    record_token_usage,
    run_cli,
    trim,
    validate_model_name,
)
from agentdev.runtime.node.agent.providers._native import (
    CLAUDE_NATIVE_FILE_TOOLS,
    CLAUDE_SHELL_TOOL,
    DEFAULT_NATIVE_TIMEOUT,
    NativeRunContext,
    absolutize_attachments,
    changed_files_note,
    native_preamble,
    read_claude_stream,
    with_preamble,
)
from agentdev.runtime.node.agent.account_fallback import QuotaExceededError, looks_like_quota
from agentdev.utils.token_tracker import TokenUsage

logger = logging.getLogger(__name__)

# Head of the system prompt for normal (non-native) calls; the agent's role, rules, skills and tool protocol
# (the static part of split_conversation) follow it, and the conversation is the prompt text.
SYSTEM_PROMPT = (
    "You are an AI agent running inside AgentDev, a multi-agent workspace. Follow the system instructions "
    "and the protocol given in the prompt exactly. Reply in the language the user's latest message uses "
    "unless the instructions say otherwise."
)


# Hardening flags of newer Claude Code releases; dropped (once) when an older CLI rejects them.
_NATIVE_OPTIONAL_FLAGS = (("--restricted",), ("--permission-prompts", "none"))

# Settings layered on native runs so they hold even when an older CLI drops --restricted: no auto-memory
# section in the system prompt and no hooks (verified on Claude Code 2.1.317). A file, not inline JSON:
# .cmd shims go through cmd.exe, which mangles the quotes of a JSON argv value.
_NATIVE_SETTINGS = {"autoMemoryEnabled": False, "disableAllHooks": True}


def _session_scope(model: Optional[str], tool_specs: List[ToolSpec], schema_enforced: bool) -> str:
    """A session is resumed only by calls offering the same model, tools and reply mode."""
    specs = [[spec.name, spec.description, spec.parameters] for spec in tool_specs]
    blob = json.dumps([model, schema_enforced, specs], sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _claude_projects_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or (Path.home() / ".claude")) / "projects"


def delete_claude_session_files(session: Optional[CliSession], workdir: str) -> None:
    """Remove what Claude Code stored for an AgentDev call under ``~/.claude/projects``: the session
    transcript (``<id>.jsonl`` + ``<id>/``) or, with ``session`` None, the project folder of our own temp
    working directory (Claude Code names it after the cwd; only ``agentdev-cli`` folders are touched)."""
    root = _claude_projects_dir()
    if not root.is_dir():
        return
    own = root / re.sub(r"[^A-Za-z0-9]", "-", workdir) if workdir else None
    if session is None:
        if own is not None and "agentdev-cli" in own.name and own.is_dir():
            shutil.rmtree(own, ignore_errors=True)
        return
    name = f"{session.session_id}.jsonl"
    files = [own / name] if own is not None and (own / name).is_file() else list(root.glob(f"*/{name}"))
    for path in files:
        try:
            path.unlink()
        except OSError:
            pass
        shutil.rmtree(path.with_suffix(""), ignore_errors=True)


def _raise_claude_error(detail: str) -> None:
    detail = trim(detail)
    # Quota first (like Codex): a limit message may mention the login/account and must still trigger fallback.
    if looks_like_quota(detail):
        raise QuotaExceededError(f"Claude account limit reached: {detail}")
    if "login" in detail.lower() or "authenticat" in detail.lower():
        raise CliProviderError(f"`claude` CLI is not logged in: {detail}")
    raise CliProviderError(f"`claude` CLI error: {detail}")


def _stream_error_text(stdout: str) -> str:
    """Error text of a ``stream-json`` run: only ``result`` / error events, never the model's own text or
    the file contents carried by tool results (those may mention "usage limit" and are not errors)."""
    parts: List[str] = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        kind = str(event.get("type") or "")
        if kind == "result":
            if event.get("is_error") or str(event.get("subtype") or "").startswith("error"):
                parts.append(str(event.get("result") or event.get("subtype") or ""))
        elif "error" in kind:
            err = event.get("error")
            parts.append(json.dumps(err, ensure_ascii=False) if isinstance(err, (dict, list)) else str(err or event.get("message") or ""))
        elif kind == "assistant" and event.get("error"):
            # API-level failure surfaced on a synthetic assistant message (e.g. rate_limit / billing_error).
            parts.append(str(event.get("error")))
            message = event.get("message")
            for block in (message.get("content") if isinstance(message, dict) else None) or []:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
    return chr(10).join(p for p in parts if p)


class ClaudeCliProvider(ModelProvider):
    """Runs ``claude -p --output-format json`` with the prompt on stdin."""

    # call_model(native=NativeRunContext) runs Claude Code's own agent loop in the project folder.
    supports_native_mode = True

    def create_client(self) -> CliClient:
        path = find_cli("claude")
        if not path:
            raise CliProviderError("`claude` CLI is not installed or not on PATH")
        return CliClient(path)

    def call_model(
        self,
        client,
        conversation: List[Message],
        timeline: List[Any],
        tool_specs: Optional[List[ToolSpec]] = None,
        **kwargs,
    ) -> ModelResponse:
        native = kwargs.get("native")
        if isinstance(native, NativeRunContext):
            return self._call_native(client, conversation, native)
        tool_specs = list(tool_specs or [])
        schema_enforced = not client.path.lower().endswith((".cmd", ".bat"))
        state = self._run_state()
        if not tool_specs or not session_reuse_enabled(self.params):
            return self._call_once(client, conversation, tool_specs, schema_enforced, state)
        # Tool loop: one Claude Code session per agent run. The first step starts it (--session-id), later
        # steps --resume it and send only the new tool results, so earlier turns are prompt-cache reads
        # instead of being re-sent (and re-written to the cache) on every step.
        scope = _session_scope(self.model_name, tool_specs, schema_enforced)
        hit = state.match(conversation, scope)
        if hit is not None:
            session, start = hit
            try:
                response = self._call_once(client, conversation, tool_specs, schema_enforced, state,
                                           session=session, resume_from=start)
            except (CliCancelled, QuotaExceededError, CliTimeoutError):
                state.discard(session)
                raise
            except CliProviderError as exc:
                # Any resume problem: forget the session and answer statelessly (full prompt) from now on.
                logger.warning("claude CLI session resume failed; continuing without session reuse: %s", exc)
                state.discard(session, broken=True)
                return self._call_once(client, conversation, tool_specs, schema_enforced, state)
            state.remember(session, conversation, response.message)
            return response
        if state.resume_broken:
            return self._call_once(client, conversation, tool_specs, schema_enforced, state)
        session = state.start(scope)
        try:
            response = self._call_once(client, conversation, tool_specs, schema_enforced, state, session=session)
        except BaseException:
            state.discard(session)
            raise
        state.remember(session, conversation, response.message)
        return response

    def _run_state(self) -> CliRunState:
        state = self.__dict__.get("_cli_state")
        if state is None:
            state = self.__dict__["_cli_state"] = CliRunState(self, cleanup=delete_claude_session_files)
        return state

    def close(self) -> None:
        """End of the agent run: delete the working folder and the CLI session files."""
        state = self.__dict__.get("_cli_state")
        if state is not None:
            state.close()

    def _call_once(
        self,
        client,
        conversation: List[Message],
        tool_specs: List[ToolSpec],
        schema_enforced: bool,
        state: CliRunState,
        session: Optional[CliSession] = None,
        resume_from: Optional[int] = None,
    ) -> ModelResponse:
        """One ``claude -p`` call: stateless (no session), first step of ``session`` (persisted under its
        id), or ``resume_from`` = index of the first message the resumed ``session`` has not seen."""
        timeout = self.params.get("timeout", 300)
        cwd = state.workdir()
        resuming = session is not None and resume_from is not None
        # Images / PDFs the user attached are copied next to the call; Claude Code's Read tool (and
        # only that one) is enabled so the model can look at them. Small text files are inlined.
        staged = [] if resuming else stage_attachments(conversation, cwd)
        if resuming:
            needs_read = bool(session.options.get("read_tool"))
        else:
            needs_read = any(item.rel_path and item.kind in ("image", "pdf", "file", "text") for item in staged)
            if session is not None:
                session.options["read_tool"] = needs_read
        cmd = [client.path, "-p", "--output-format", "json"]
        if session is None:
            cmd.append("--no-session-persistence")
        elif resuming:
            cmd += ["--resume", session.session_id]
        else:
            cmd += ["--session-id", session.session_id]
        # Only the Read tool, and no blanket allow rule: print mode then auto-allows reads inside the
        # working directory (the staged attachments) and refuses paths outside it.
        cmd += ["--tools", "Read"] if needs_read else ["--tools", ""]
        preamble = build_tool_preamble(tool_specs, schema_enforced) if tool_specs else ""
        static, transcript = split_conversation(conversation, preamble)
        # Replace Claude Code's own ~18k-token coding-assistant system prompt (and skip the user's global
        # settings / CLAUDE.md / MCP servers, claude.ai connectors included): AgentDev's instructions are
        # the system prompt. The static part (role, skills catalog, tool protocol + schemas) goes there,
        # byte-identical on every step, so it is a prompt-cache read after the first call.
        system_text = SYSTEM_PROMPT
        if static and transcript:
            system_text = SYSTEM_PROMPT + "\n\n" + static
        else:
            transcript = static or transcript
        system_file = os.path.join(cwd, f"agentdev_system_{uuid.uuid4().hex[:8]}.txt")
        with open(system_file, "w", encoding="utf-8") as fh:
            fh.write(system_text)
        cmd += ["--system-prompt-file", system_file, "--setting-sources", "project", "--disable-slash-commands",
                "--strict-mcp-config"]
        if tool_specs and schema_enforced:
            # Claude Code's own tools stay disabled; AgentDev tools are offered through the prompt and the
            # model answers with {text, tool_calls} JSON. --json-schema makes that reply machine-parseable.
            # .cmd/.bat shims go through cmd.exe, which mangles the quotes in a JSON argv value, so there
            # the schema is skipped and the prompt alone asks for JSON (parsed leniently below).
            cmd += ["--json-schema", json.dumps(TOOL_REPLY_SCHEMA, separators=(",", ":"))]
        prompt = render_followup(conversation, resume_from, bool(tool_specs)) if resuming else transcript
        section = attachments_section(staged, can_read_files=needs_read)
        if section:
            prompt = prompt + chr(10) * 2 + section
        if self.model_name:
            cmd += ["--model", validate_model_name(self.model_name)]
        try:
            proc = run_cli(cmd, prompt, timeout, "claude", cwd)
        finally:
            try:
                os.remove(system_file)
            except OSError:
                pass
        out, err = proc.stdout or "", proc.stderr or ""
        data: Any = None
        try:
            data = json.loads(out)
        except (ValueError, TypeError):
            pass
        if isinstance(data, dict) and data.get("is_error"):
            _raise_claude_error(str(data.get("result") or err))
        if proc.returncode != 0:
            if looks_like_quota(err):
                raise QuotaExceededError(f"Claude account limit reached: {trim(err)}")
            raise CliProviderError(f"`claude` CLI exited with code {proc.returncode}: {trim(err or out)}")
        if isinstance(data, dict):
            text = str(data.get("result") or "")
        else:
            if resuming:
                raise CliProviderError("`claude` CLI returned no JSON result on resume")
            text = out.strip()
            data = {"result": text}
        if session is not None:
            data["agentdev_session"] = "resumed" if resuming else "started"
            # A resumed session reports its running total cost; keep this call's share (usage is per call).
            total = data.get("total_cost_usd")
            if isinstance(total, (int, float)):
                before = float(session.options.get("cost_usd") or 0.0) if resuming else 0.0
                session.options["cost_usd"] = float(total)
                data["session_cost_usd"] = float(total)
                data["total_cost_usd"] = max(0.0, float(total) - before)
        record_token_usage(self, data, "claude_cli")
        if tool_specs:
            text, tool_calls = parse_tool_reply(data.get("structured_output"), text, tool_specs)
            return ModelResponse(
                message=Message(role=MessageRole.ASSISTANT, content=text, tool_calls=tool_calls),
                raw_response=data,
            )
        return ModelResponse(
            message=Message(role=MessageRole.ASSISTANT, content=text),
            raw_response=data,
        )

    def _call_native(self, client, conversation: List[Message], native: NativeRunContext) -> ModelResponse:
        """Full Claude Code agent with cwd = project workspace and only the file tools (+ Bash on opt-in).

        ``--restricted`` drops code-running tools not named in ``--tools`` and ignores user/project settings
        (hooks, extra permissions); ``--setting-sources project`` + ``--disable-slash-commands`` + the
        settings file keep that true (no user CLAUDE.md, skills, plugins, auto-memory, hooks) even when an
        older CLI rejects ``--restricted``; ``--strict-mcp-config`` without ``--mcp-config`` loads no MCP server;
        ``acceptEdits`` auto-approves file edits inside the working directories and ``--permission-prompts
        none`` denies anything else that would need a person. Never ``--dangerously-skip-permissions``.
        """
        timeout = self.params.get("timeout", DEFAULT_NATIVE_TIMEOUT)
        tools = list(CLAUDE_NATIVE_FILE_TOOLS) + ([CLAUDE_SHELL_TOOL] if native.allow_commands else [])
        with make_tempdir() as staging:
            # Attachments stay outside the user's project: staged in a temp folder exposed read-only via --add-dir.
            staged = stage_attachments(conversation, staging)
            has_files = absolutize_attachments(staged, staging)
            settings = dict(_NATIVE_SETTINGS)
            skills_readable = "SKILL.md" in flatten_conversation(conversation) and SKILLS_DIR.is_dir()
            if skills_readable:
                # Skills are read-only reference: --add-dir plus acceptEdits would otherwise let the agent edit
                # the shared skill library. Edit(path) rules cover every file-editing tool (verified, 2.1.317).
                settings["permissions"] = {"deny": [f"Edit({SKILLS_DIR.as_posix()}/**)"]}
            settings_file = os.path.join(staging, "agentdev_settings.json")
            with open(settings_file, "w", encoding="utf-8") as fh:
                json.dump(settings, fh)
            base = [
                client.path, "-p", "--output-format", "stream-json", "--verbose", "--no-session-persistence",
                "--tools", ",".join(tools), "--strict-mcp-config",
                # The user's own setup stays out: no ~/.claude settings, CLAUDE.md, plugins or skills.
                "--setting-sources", "project", "--disable-slash-commands", "--settings", settings_file,
                "--permission-mode", "acceptEdits", "--max-turns", str(int(native.max_turns)),
            ]
            if native.allow_commands:
                base += ["--allowedTools", CLAUDE_SHELL_TOOL]
            if has_files:
                base += ["--add-dir", staging]
            if skills_readable:
                # Ticked skills are listed by path in the system prompt; let the agent read them (read-only use).
                base += ["--add-dir", str(SKILLS_DIR)]
            if self.model_name:
                base += ["--model", validate_model_name(self.model_name)]
            preamble = native_preamble(native.workspace, can_edit=True, can_run_commands=native.allow_commands,
                                       vendor="claude")
            prompt = with_preamble(flatten_conversation(conversation), preamble)
            section = attachments_section(staged, can_read_files=True)
            if section:
                prompt = prompt + chr(10) * 2 + section
            optional = [flag for group in _NATIVE_OPTIONAL_FLAGS for flag in group]
            proc = run_cli(base + optional, prompt, timeout, "claude", native.workspace)
            if proc.returncode != 0 and "unknown option" in (proc.stderr or "").lower():
                logger.warning("claude CLI rejected native-mode hardening flags; retrying without them: %s",
                               trim(proc.stderr or "", 200))
                proc = run_cli(base, prompt, timeout, "claude", native.workspace)
        out, err = proc.stdout or "", proc.stderr or ""
        result, changed = read_claude_stream(out, native)
        if result is None:
            if proc.returncode != 0:
                errors_text = err + chr(10) + _stream_error_text(out)
                if looks_like_quota(errors_text):
                    raise QuotaExceededError(f"Claude account limit reached: {trim(errors_text)}")
                raise CliProviderError(f"`claude` CLI exited with code {proc.returncode}: {trim(err or out[-500:])}")
            raise CliProviderError("`claude` CLI returned no result")
        text = str(result.get("result") or "")
        subtype = str(result.get("subtype") or "")
        record_token_usage(self, result, "claude_cli")
        if result.get("is_error") or subtype.startswith("error"):
            if subtype == "error_max_turns":
                # Work done so far is on disk; report it instead of failing the node.
                text = (text + chr(10) * 2 if text else "") + (
                    f"[Stopped: reached the limit of {native.max_turns} agent turns. The work may be incomplete.]"
                )
            else:
                _raise_claude_error(text or err or subtype)
        note = changed_files_note(native.workspace, changed)
        if note:
            text = (text.rstrip() + chr(10) * 2 + note) if text.strip() else note
        raw = dict(result)
        raw["changed_files"] = changed
        return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=text), raw_response=raw)

    def extract_token_usage(self, response: Any) -> TokenUsage:
        usage = response.get("usage") if isinstance(response, dict) else None
        if not isinstance(usage, dict):
            return TokenUsage()
        uncached = int(usage.get("input_tokens") or 0)
        cache_w = int(usage.get("cache_creation_input_tokens") or 0)
        cache_r = int(usage.get("cache_read_input_tokens") or 0)
        out = int(usage.get("output_tokens") or 0)
        inp = uncached + cache_w + cache_r
        return TokenUsage(
            input_tokens=inp,
            output_tokens=out,
            total_tokens=inp + out,
            # input_tokens counts cache reads (billed ~10%) and writes: the cost and the split show savings.
            metadata={
                "total_cost_usd": response.get("total_cost_usd"),
                "uncached_input_tokens": uncached,
                "cache_creation_input_tokens": cache_w,
                "cache_read_input_tokens": cache_r,
                "session": response.get("agentdev_session"),
            },
        )
