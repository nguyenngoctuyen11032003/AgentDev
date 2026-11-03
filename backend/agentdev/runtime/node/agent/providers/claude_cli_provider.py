"""Claude provider backed by the user's logged-in ``claude`` CLI (print mode)."""

from __future__ import annotations

import json
import os
import logging
from typing import Any, List, Optional

from agentdev.connections.cli_auth import find_cli
from agentdev.entity.messages import Message, MessageRole
from agentdev.entity.tool_spec import ToolSpec
from agentdev.runtime.node.agent import ModelProvider, ModelResponse
from agentdev.runtime.node.agent.providers._cli_common import (
    CliClient,
    CliProviderError,
    TOOL_REPLY_SCHEMA,
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

# Minimal system prompt for normal (non-native) calls; the agent's role, rules, skills and tool protocol
# are in the prompt text built by flatten_conversation.
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


def _raise_claude_error(detail: str) -> None:
    detail = trim(detail)
    if "login" in detail.lower() or "authenticat" in detail.lower():
        raise CliProviderError(f"`claude` CLI is not logged in: {detail}")
    if looks_like_quota(detail):
        raise QuotaExceededError(f"Claude account limit reached: {detail}")
    raise CliProviderError(f"`claude` CLI error: {detail}")


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
        timeout = self.params.get("timeout", 300)
        with make_tempdir() as cwd:
            # Images / PDFs the user attached are copied next to the call; Claude Code's Read tool (and
            # only that one) is enabled so the model can look at them. Small text files are inlined.
            staged = stage_attachments(conversation, cwd)
            needs_read = any(item.rel_path and item.kind in ("image", "pdf", "file", "text") for item in staged)
            cmd = [client.path, "-p", "--output-format", "json", "--no-session-persistence"]
            # Only the Read tool, and no blanket allow rule: print mode then auto-allows reads inside the
            # temp working directory (the staged attachments) and refuses paths outside it.
            cmd += ["--tools", "Read"] if needs_read else ["--tools", ""]
            # Replace Claude Code's own ~18k-token coding-assistant system prompt (and skip the user's
            # global settings / CLAUDE.md): AgentDev's instructions travel in the prompt itself. This cuts
            # each call's input ~15x and stops the CLI's coding persona from overriding the agent's role.
            system_file = os.path.join(cwd, "agentdev_system.txt")
            with open(system_file, "w", encoding="utf-8") as fh:
                fh.write(SYSTEM_PROMPT)
            cmd += ["--system-prompt-file", system_file, "--setting-sources", "project", "--disable-slash-commands"]
            if tool_specs:
                # Claude Code's own tools stay disabled; AgentDev tools are offered through the prompt and the
                # model answers with {text, tool_calls} JSON. --json-schema makes that reply machine-parseable.
                # .cmd/.bat shims go through cmd.exe, which mangles the quotes in a JSON argv value, so there
                # the schema is skipped and the prompt alone asks for JSON (parsed leniently below).
                schema_enforced = not client.path.lower().endswith((".cmd", ".bat"))
                if schema_enforced:
                    cmd += ["--json-schema", json.dumps(TOOL_REPLY_SCHEMA, separators=(",", ":"))]
                prompt = flatten_conversation(conversation, build_tool_preamble(tool_specs, schema_enforced))
            else:
                prompt = flatten_conversation(conversation)
            section = attachments_section(staged, can_read_files=needs_read)
            if section:
                prompt = prompt + chr(10) * 2 + section
            if self.model_name:
                cmd += ["--model", validate_model_name(self.model_name)]
            proc = run_cli(cmd, prompt, timeout, "claude", cwd)
        out, err = proc.stdout or "", proc.stderr or ""
        data: Any = None
        try:
            data = json.loads(out)
        except (ValueError, TypeError):
            pass
        if isinstance(data, dict) and data.get("is_error"):
            detail = trim(str(data.get("result") or err))
            if "login" in detail.lower() or "authenticat" in detail.lower():
                raise CliProviderError(f"`claude` CLI is not logged in: {detail}")
            if looks_like_quota(detail):
                raise QuotaExceededError(f"Claude account limit reached: {detail}")
            raise CliProviderError(f"`claude` CLI error: {detail}")
        if proc.returncode != 0:
            if looks_like_quota(err):
                raise QuotaExceededError(f"Claude account limit reached: {trim(err)}")
            raise CliProviderError(f"`claude` CLI exited with code {proc.returncode}: {trim(err or out)}")
        if isinstance(data, dict):
            text = str(data.get("result") or "")
        else:
            text = out.strip()
            data = {"result": text}
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
            settings_file = os.path.join(staging, "agentdev_settings.json")
            with open(settings_file, "w", encoding="utf-8") as fh:
                json.dump(_NATIVE_SETTINGS, fh)
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
                if looks_like_quota(err) or looks_like_quota(out[-2000:]):
                    raise QuotaExceededError(f"Claude account limit reached: {trim(err or out[-500:])}")
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
            metadata={"total_cost_usd": response.get("total_cost_usd")},
        )
