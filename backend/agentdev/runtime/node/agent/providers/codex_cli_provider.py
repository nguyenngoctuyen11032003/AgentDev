"""OpenAI provider backed by the user's logged-in ``codex`` CLI (``codex exec``)."""

from __future__ import annotations

import json
import re
import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from agentdev.connections.cli_auth import find_cli
from agentdev.entity.messages import Message, MessageRole
from agentdev.entity.tool_spec import ToolSpec
from agentdev.runtime.node.agent import ModelProvider, ModelResponse
from agentdev.runtime.node.agent.providers._cli_common import (
    CliClient,
    CliProviderError,
    CliRunState,
    attachments_section,
    effort_level,
    build_tool_preamble,
    flatten_conversation,
    make_tempdir,
    parse_tool_reply,
    record_token_usage,
    run_cli,
    stage_attachments,
    trim,
    validate_model_name,
)
from agentdev.runtime.node.agent.providers._native import (
    DEFAULT_NATIVE_TIMEOUT,
    CodexActivityReader,
    LiveEvents,
    NativeRunContext,
    absolutize_attachments,
    changed_files_note,
    native_preamble,
    read_codex_activity,
    with_preamble,
)
from agentdev.runtime.node.agent.account_fallback import QuotaExceededError, looks_like_quota
from agentdev.utils.token_tracker import TokenUsage

logger = logging.getLogger(__name__)

# Keep the user's own Codex setup out of AgentDev runs (verified on codex-cli 0.166): no skill catalog from
# ~/.agents/skills / ~/.codex/skills (it alone cost ~8k input tokens and invited Codex to read those files),
# no MCP servers, apps, plugins, hooks or memories, and no session files. Auth still comes from CODEX_HOME,
# and config.toml stays loaded (it carries e.g. the Windows sandbox mode). Plain unquoted values: .cmd shims
# go through cmd.exe, which mangles quotes.
CODEX_ISOLATION_ARGS = (
    "--ephemeral",
    "-c", "skills.include_instructions=false", "-c", "mcp_servers={}",
    "--disable", "apps", "--disable", "plugins", "--disable", "hooks", "--disable", "memories",
)

# Codex enforces --output-schema in OpenAI's strict mode: every object closed and fully
# required, so tool arguments travel as a JSON-encoded string (parse_tool_reply decodes it).
_ARGS_NOTE = (
    '- In this reply format "arguments" is a STRING holding the JSON-encoded arguments object, '
    'e.g. "{\\"query\\": \\"weather\\"}". Use an empty "tool_calls" list when answering.'
)


def tool_reply_schema(tool_specs: List[ToolSpec]) -> Dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "text": {"type": "string"},
            "tool_calls": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string", "enum": [spec.name for spec in tool_specs]},
                        "arguments": {"type": "string"},
                    },
                    "required": ["name", "arguments"],
                },
            },
        },
        "required": ["text", "tool_calls"],
    }


def _ignore_line(_line: str) -> None:
    """on_line target that only switches the idle watchdog on."""


def _error_events_text(stdout: str) -> str:
    """Messages of error events only (normal events carry rate-limit telemetry that is not an error)."""
    parts = []
    for line in stdout.splitlines():
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
        if "error" in kind or "failed" in kind:
            # Readable text (``error`` and ``turn.failed`` repeat the same message), not the raw event JSON.
            err = event.get("error")
            msg = (err.get("message") if isinstance(err, dict) else err) or event.get("message")
            text = str(msg) if isinstance(msg, str) and msg.strip() else json.dumps(event, ensure_ascii=False)
            if text not in parts:
                parts.append(text)
    return chr(10).join(parts)


def _read_events(stdout: str) -> tuple[Dict[str, Any], str]:
    """(token usage, last agent message) from the ``--json`` event stream."""
    usage: Dict[str, Any] = {}
    message = ""
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
        if isinstance(event.get("usage"), dict):
            usage = event["usage"]
        item = event.get("item")
        if isinstance(item, dict) and item.get("type") == "agent_message" and isinstance(item.get("text"), str):
            message = item["text"]
    return usage, message


def _raise_codex_failure(proc) -> None:
    err = proc.stderr or ""
    # stdout is the JSON event stream (model text, thread ids, rate-limit telemetry): only its
    # error events count. Quota is checked first so an exhausted account triggers fallback.
    errors_text = err + chr(10) + _error_events_text(proc.stdout or "")
    if looks_like_quota(errors_text):
        raise QuotaExceededError(f"Codex account limit reached: {trim(errors_text)}")
    low = errors_text.lower()
    if "not logged in" in low or "login" in low or "unauthorized" in low or re.search(r"\b401\b", low):
        raise CliProviderError(f"`codex` CLI is not logged in: {trim(errors_text)}")
    raise CliProviderError(f"`codex` CLI exited with code {proc.returncode}: {trim(err or proc.stdout)}")


class CodexCliProvider(ModelProvider):
    """Runs ``codex exec ... -`` with the prompt on stdin; reply read from the ``-o`` file."""

    # call_model(native=NativeRunContext) runs Codex's own agent loop in the project folder.
    supports_native_mode = True

    def create_client(self) -> CliClient:
        path = find_cli("codex")
        if not path:
            raise CliProviderError("`codex` CLI is not installed or not on PATH")
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
        if tool_specs:
            # AgentDev tools are offered through the prompt; Codex answers with {text, tool_calls}.
            preamble = build_tool_preamble(tool_specs, schema_enforced=True) + "\n" + _ARGS_NOTE
            prompt = flatten_conversation(conversation, preamble)
        else:
            prompt = flatten_conversation(conversation)
        # Streamed (on_line) so the idle watchdog catches a stuck CLI; the wall-clock limit is only a backstop
        # (a flat 300 s killed long outputs and the retry redid the work).
        timeout = self.params.get("timeout", DEFAULT_NATIVE_TIMEOUT)
        # One working folder for every call of this agent run: Codex puts the cwd in its prompt, so a
        # per-call temp folder changes the prompt prefix and no step reuses the previous one's cache.
        cwd = self._run_state().workdir()
        tag = uuid.uuid4().hex[:8]
        out_file = os.path.join(cwd, f"last_message_{tag}.txt")
        schema_file = os.path.join(cwd, f"reply_schema_{tag}.json")
        cmd = [
            client.path, "exec", "--skip-git-repo-check", "--sandbox", "read-only",
            "--color", "never", "--json", "-o", out_file, *CODEX_ISOLATION_ARGS,
            # The temp working dir has no AGENTS.md of interest; never pick up one from a parent folder.
            "-c", "project_doc_max_bytes=0",
        ]
        if tool_specs:
            with open(schema_file, "w", encoding="utf-8") as fh:
                json.dump(tool_reply_schema(tool_specs), fh)
            cmd += ["--output-schema", schema_file]
        # Attachments: images go to Codex natively (-i); other files sit in the working directory,
        # which the read-only sandbox can read; small text files are inlined in the prompt.
        staged = stage_attachments(conversation, cwd)
        for item in staged:
            if item.kind == "image" and item.rel_path:
                # --image takes several values; the = form keeps the trailing "-" (stdin prompt) separate.
                cmd.append(f"--image={os.path.join(cwd, item.rel_path)}")
        section = attachments_section(staged, can_read_files=False)
        if section:
            prompt = prompt + chr(10) * 2 + section
        if self.model_name:
            cmd += ["--model", validate_model_name(self.model_name)]
        effort = effort_level(self.params)
        if effort:
            cmd += ["-c", f"model_reasoning_effort={effort}"]
        cmd.append("-")  # read prompt from stdin
        try:
            proc = run_cli(cmd, prompt, timeout, "codex", cwd, on_line=_ignore_line)
            text = ""
            if os.path.exists(out_file):
                with open(out_file, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read().strip()
        finally:
            for path in (out_file, schema_file):
                try:
                    os.remove(path)
                except OSError:
                    pass
        if proc.returncode != 0:
            _raise_codex_failure(proc)
        usage, event_text = _read_events(proc.stdout or "")
        text = text or event_text.strip()
        raw = {"result": text, "usage": usage}
        record_token_usage(self, raw, "codex_cli")
        if tool_specs:
            structured = None
            try:
                structured = json.loads(text)
            except ValueError:
                pass
            answer, tool_calls = parse_tool_reply(structured, text, tool_specs)
            return ModelResponse(
                message=Message(role=MessageRole.ASSISTANT, content=answer, tool_calls=tool_calls),
                raw_response=raw,
            )
        return ModelResponse(
            message=Message(role=MessageRole.ASSISTANT, content=text),
            raw_response=raw,
        )

    def _run_state(self) -> CliRunState:
        state = self.__dict__.get("_cli_state")
        if state is None:
            state = self.__dict__["_cli_state"] = CliRunState(self)
        return state

    def close(self) -> None:
        """End of the agent run: delete the working folder."""
        state = self.__dict__.get("_cli_state")
        if state is not None:
            state.close()

    def _call_native(self, client, conversation: List[Message], native: NativeRunContext) -> ModelResponse:
        """Codex's own agent with ``-C`` = project workspace.

        Shell commands are how Codex works, so the sandbox is the gate: ``workspace-write`` (edits and
        commands confined to the workspace, no network) only when commands are allowed (node setting AND
        server opt-in), otherwise ``read-only`` (Codex can inspect but not change the project). MCP servers,
        web search, apps, plugins, hooks, memories and the user's skill catalog are switched off
        for the run. Never ``--dangerously-bypass-approvals-and-sandbox``.
        """
        timeout = self.params.get("timeout", DEFAULT_NATIVE_TIMEOUT)
        sandbox = "workspace-write" if native.allow_commands else "read-only"
        with make_tempdir() as staging:
            out_file = os.path.join(staging, "last_message.txt")
            cmd = [
                client.path, "exec", "--skip-git-repo-check", "-C", native.workspace, "--sandbox", sandbox,
                "--color", "never", "--json", "-o", out_file, *CODEX_ISOLATION_ARGS,
                # The project's own AGENTS.md still applies; user-level skills/plugins/MCP do not.
                "-c", "web_search=disabled", "-c", "sandbox_workspace_write.network_access=false",
            ]
            staged = stage_attachments(conversation, staging)
            absolutize_attachments(staged, staging)
            for item in staged:
                if item.kind == "image" and item.rel_path:
                    cmd.append(f"--image={item.rel_path}")
            preamble = native_preamble(native.workspace, can_edit=native.allow_commands,
                                       can_run_commands=native.allow_commands, vendor="codex")
            prompt = with_preamble(flatten_conversation(conversation), preamble)
            section = attachments_section(staged, can_read_files=False)
            if section:
                prompt = prompt + chr(10) * 2 + section
            if self.model_name:
                cmd += ["--model", validate_model_name(self.model_name)]
            effort = effort_level(self.params)
            if effort:
                cmd += ["-c", f"model_reasoning_effort={effort}"]
            cmd.append("-")
            # Commands / file changes are reported to the UI as their item.started/completed events arrive.
            live = LiveEvents(CodexActivityReader(native))
            try:
                proc = run_cli(cmd, prompt, timeout, "codex", native.workspace, on_line=live.push)
            except BaseException:
                live.abort()
                raise
            text = ""
            if os.path.exists(out_file):
                with open(out_file, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read().strip()
        if proc.returncode != 0:
            live.abort()
            _raise_codex_failure(proc)
        live.finish(proc.stdout or "")  # reports what was not seen live; changed files from the whole output
        changed = read_codex_activity(proc.stdout or "", None)
        usage, event_text = _read_events(proc.stdout or "")
        text = text or event_text.strip()
        raw = {"result": text, "usage": usage, "changed_files": changed}
        record_token_usage(self, raw, "codex_cli")
        note = changed_files_note(native.workspace, changed)
        if note:
            text = (text.rstrip() + chr(10) * 2 + note) if text.strip() else note
        return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=text), raw_response=raw)

    def extract_token_usage(self, response: Any) -> TokenUsage:
        usage = response.get("usage") if isinstance(response, dict) else None
        if not isinstance(usage, dict) or not usage:
            return TokenUsage()
        inp = int(usage.get("input_tokens") or 0)
        out = int(usage.get("output_tokens") or 0)
        return TokenUsage(
            input_tokens=inp,
            output_tokens=out,
            total_tokens=inp + out,
            metadata={"cached_input_tokens": usage.get("cached_input_tokens")},
        )
