"""OpenAI provider backed by the user's logged-in ``codex`` CLI (``codex exec``)."""

from __future__ import annotations

import json
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
    build_tool_preamble,
    flatten_conversation,
    make_tempdir,
    parse_tool_reply,
    record_token_usage,
    run_cli,
    trim,
    validate_model_name,
)
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


class CodexCliProvider(ModelProvider):
    """Runs ``codex exec ... -`` with the prompt on stdin; reply read from the ``-o`` file."""

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
            if self.model_name:
                cmd += ["--model", validate_model_name(self.model_name)]
            cmd.append("-")  # read prompt from stdin
            proc = run_cli(cmd, prompt, timeout, "codex", cwd)
            text = ""
            if os.path.exists(out_file):
                with open(out_file, "r", encoding="utf-8", errors="replace") as fh:
                    text = fh.read().strip()
        err = proc.stderr or ""
        if proc.returncode != 0:
            low = (err + (proc.stdout or "")).lower()
            if "login" in low or "unauthorized" in low or "401" in low:
                raise CliProviderError(f"`codex` CLI is not logged in: {trim(err)}")
            raise CliProviderError(f"`codex` CLI exited with code {proc.returncode}: {trim(err or proc.stdout)}")
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
