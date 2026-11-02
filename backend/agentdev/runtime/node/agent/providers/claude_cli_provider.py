"""Claude provider backed by the user's logged-in ``claude`` CLI (print mode)."""

from __future__ import annotations

import json
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
    build_tool_preamble,
    flatten_conversation,
    parse_tool_reply,
    make_tempdir,
    run_cli,
    trim,
    validate_model_name,
)
from agentdev.utils.token_tracker import TokenUsage

logger = logging.getLogger(__name__)


class ClaudeCliProvider(ModelProvider):
    """Runs ``claude -p --output-format json`` with the prompt on stdin."""

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
        tool_specs = list(tool_specs or [])
        cmd = [client.path, "-p", "--output-format", "json", "--tools", "", "--no-session-persistence"]
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
        if self.model_name:
            cmd += ["--model", validate_model_name(self.model_name)]
        timeout = self.params.get("timeout", 300)
        with make_tempdir() as cwd:
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
            raise CliProviderError(f"`claude` CLI error: {detail}")
        if proc.returncode != 0:
            raise CliProviderError(f"`claude` CLI exited with code {proc.returncode}: {trim(err or out)}")
        if isinstance(data, dict):
            text = str(data.get("result") or "")
        else:
            text = out.strip()
            data = {"result": text}
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
