"""OpenAI provider backed by the user's logged-in ``codex`` CLI (``codex exec``)."""

from __future__ import annotations

import json
import re
import logging
import os
from typing import Any, Dict, List, Optional

from agentdev.connections.cli_auth import find_cli
from agentdev.entity.messages import Message, MessageRole
from agentdev.entity.tool_spec import ToolSpec
from agentdev.runtime.node.agent import ModelProvider, ModelResponse
from agentdev.runtime.node.agent.providers._cli_common import (
    CliClient,
    CliProviderError,
    attachments_section,
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
            parts.append(json.dumps(event, ensure_ascii=False))
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
        timeout = self.params.get("timeout", 300)
        with make_tempdir() as cwd:
            out_file = os.path.join(cwd, "last_message.txt")
            cmd = [
                client.path, "exec", "--skip-git-repo-check", "--sandbox", "read-only",
                "--color", "never", "--json", "-o", out_file,
            ]
            if tool_specs:
                schema_file = os.path.join(cwd, "reply_schema.json")
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
            cmd.append("-")  # read prompt from stdin
            proc = run_cli(cmd, prompt, timeout, "codex", cwd)
            text = ""
            if os.path.exists(out_file):
                with open(out_file, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read().strip()
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

    def _call_native(self, client, conversation: List[Message], native: NativeRunContext) -> ModelResponse:
        """Codex's own agent with ``-C`` = project workspace.

        Shell commands are how Codex works, so the sandbox is the gate: ``workspace-write`` (edits and
        commands confined to the workspace, no network) only when commands are allowed (node setting AND
        server opt-in), otherwise ``read-only`` (Codex can inspect but not change the project). MCP servers,
        web search and apps are switched off for the run. Never ``--dangerously-bypass-approvals-and-sandbox``.
        """
        timeout = self.params.get("timeout", DEFAULT_NATIVE_TIMEOUT)
        sandbox = "workspace-write" if native.allow_commands else "read-only"
        with make_tempdir() as staging:
            out_file = os.path.join(staging, "last_message.txt")
            cmd = [
                client.path, "exec", "--skip-git-repo-check", "-C", native.workspace, "--sandbox", sandbox,
                "--color", "never", "--json", "-o", out_file,
                # Plain (unquoted) TOML-ish values: .cmd shims go through cmd.exe, which mangles quotes.
                "-c", "mcp_servers={}", "-c", "web_search=disabled",
                "-c", "sandbox_workspace_write.network_access=false",
                "--disable", "apps", "--disable", "plugins",
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
            cmd.append("-")
            proc = run_cli(cmd, prompt, timeout, "codex", native.workspace)
            text = ""
            if os.path.exists(out_file):
                with open(out_file, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read().strip()
        if proc.returncode != 0:
            _raise_codex_failure(proc)
        changed = read_codex_activity(proc.stdout or "", native)
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
