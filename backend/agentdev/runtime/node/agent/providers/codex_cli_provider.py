"""OpenAI provider backed by the user's logged-in ``codex`` CLI (``codex exec``)."""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional

from agentdev.connections.cli_auth import find_cli
from agentdev.entity.messages import Message, MessageRole
from agentdev.entity.tool_spec import ToolSpec
from agentdev.runtime.node.agent import ModelProvider, ModelResponse
from agentdev.runtime.node.agent.providers._cli_common import (
    CliClient,
    CliProviderError,
    flatten_conversation,
    make_tempdir,
    run_cli,
    trim,
    validate_model_name,
)
from agentdev.utils.token_tracker import TokenUsage

logger = logging.getLogger(__name__)


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
        if tool_specs:
            logger.warning("Tools are not supported in codex CLI mode; ignoring %d tool(s)", len(tool_specs))
        prompt = flatten_conversation(conversation)
        timeout = self.params.get("timeout", 300)
        with make_tempdir() as cwd:
            out_file = os.path.join(cwd, "last_message.txt")
            cmd = [
                client.path, "exec", "--skip-git-repo-check", "--sandbox", "read-only",
                "--color", "never", "-o", out_file,
            ]
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
            low = err.lower()
            if "login" in low or "unauthorized" in low:
                raise CliProviderError(f"`codex` CLI is not logged in: {trim(err)}")
            raise CliProviderError(f"`codex` CLI exited with code {proc.returncode}: {trim(err or proc.stdout)}")
        if not text:
            text = (proc.stdout or "").strip()
        return ModelResponse(
            message=Message(role=MessageRole.ASSISTANT, content=text),
            raw_response={"result": text},
        )

    def extract_token_usage(self, response: Any) -> TokenUsage:
        return TokenUsage()
