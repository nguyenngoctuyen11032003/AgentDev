"""Human-in-the-loop prompt service with pluggable channels."""

import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Protocol

from agentdev.entity.messages import MessageBlock, MessageBlockType, MessageContent
from agentdev.utils.log_manager import LogManager


@dataclass
class PromptResult:
    """Typed result returned from prompt channels."""

    text: str
    blocks: Optional[List[MessageBlock]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_message_content(self) -> MessageContent:
        return self.blocks if self.blocks is not None else self.text


class PromptChannel(Protocol):
    """Channel interface that performs the actual user interaction."""

    def request(
        self,
        *,
        node_id: str,
        task: str,
        inputs: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PromptResult:
        """Collect user feedback and return the structured response."""


@dataclass
class CliPromptChannel:
    """Default channel that prompts the operator via CLI input()."""

    input_func: Callable[[str], str] = input

    def request(
        self,
        *,
        node_id: str,
        task: str,
        inputs: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PromptResult:
        header = ["===== HUMAN INPUT REQUIRED ====="]
        if inputs:
            header.append("=== Node inputs ===")
            header.append(inputs)
        header.append(f"=== Task for human ({node_id}) ===")
        header.append(task)
        header.append("=== Your response: ===")
        prompt = "\n".join(header) + "\n"
        response = self.input_func(prompt)
        return PromptResult(
            text=response,
            blocks=[MessageBlock.text_block(response or "")],
        )


AUTO_ANSWER = (
    "[Automatic answer: no person is available in this run] Approved. Proceed with your recommended "
    "option, state the assumption you made, and finish the task."
)


# Answer given instead of AUTO_ANSWER at a gate marked ``paid: true`` (the step after it costs money or cannot
# be undone). It deliberately does NOT start with "[Automatic answer" (gates accept that as approval) nor with
# an approval word or the explicit "tạo video" phrase, so every gate routes it to its skip/refusal branch.
AUTO_SKIP_PAID = (
    "[Skipped automatically: no person is available in this run] Not approved. This step costs money or "
    "cannot be undone, so it was skipped: do not start it; list it for the user to confirm."
)


class AutoAnswerChannel:
    """Non-interactive channel: approves and records each question (server runs without a chat, Lab).

    A Human gate marked ``paid`` is never approved: it gets ``AUTO_SKIP_PAID`` and its id is recorded in
    ``skipped_gates``.
    """

    def __init__(self, answer: str = AUTO_ANSWER, *, allow_human_nodes: bool = True) -> None:
        self.answer = answer
        # False for ordinary server runs: a Human node is a deliberate approval step, so it must not
        # be approved silently when nobody is watching; the run fails with a clear message instead.
        self.allow_human_nodes = allow_human_nodes
        self.questions: List[Dict[str, str]] = []
        self.skipped_gates: List[str] = []

    def request(
        self,
        *,
        node_id: str,
        task: str,
        inputs: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PromptResult:
        if not self.allow_human_nodes and (metadata or {}).get("node_type") == "human":
            raise RuntimeError(
                f"Node '{node_id}' needs a person to answer, but this run has no chat attached. "
                "Run the workflow from the Run page to answer it."
            )
        meta = metadata or {}
        if meta.get("node_type") == "human" and meta.get("paid"):
            if node_id not in self.skipped_gates:
                self.skipped_gates.append(node_id)
            self.questions.append({"node": node_id, "question": task, "answer": "skipped"})
            return PromptResult(text=AUTO_SKIP_PAID, blocks=[MessageBlock.text_block(AUTO_SKIP_PAID)])
        self.questions.append({"node": node_id, "question": task})
        return PromptResult(text=self.answer, blocks=[MessageBlock.text_block(self.answer)])


class HumanPromptService:
    """Coordinates human feedback collection across nodes and tools."""

    def __init__(
        self,
        *,
        log_manager: LogManager,
        channel: PromptChannel,
        session_id: Optional[str] = None,
    ) -> None:
        self._log_manager = log_manager
        self._channel = channel
        self._session_id = session_id
        self._lock = threading.Lock()

    def request(
        self,
        node_id: str,
        task_description: str,
        *,
        inputs: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PromptResult:
        """Request human input through the configured channel."""

        meta = dict(metadata or {})
        if self._session_id and "session_id" not in meta:
            meta["session_id"] = self._session_id

        with self._lock:
            with self._log_manager.human_timer(node_id):
                raw_result = self._channel.request(
                    node_id=node_id,
                    task=task_description,
                    inputs=inputs,
                    metadata=meta,
                )

        prompt_result = self._normalize_result(raw_result)
        sanitized_text = self._sanitize_response(prompt_result.text)
        normalized_blocks = self._normalize_blocks(prompt_result.blocks, sanitized_text)
        combined_metadata = {**prompt_result.metadata, **meta}

        self._log_manager.record_human_interaction(
            node_id,
            inputs,
            sanitized_text,
            details={"task_description": task_description, **combined_metadata},
        )
        return PromptResult(
            text=sanitized_text,
            blocks=normalized_blocks,
            metadata=combined_metadata,
        )

    @staticmethod
    def _sanitize_response(response: Any) -> str:
        text = response if isinstance(response, str) else str(response)
        return text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")

    def _normalize_result(self, raw_result: PromptResult | str | Any) -> PromptResult:
        if isinstance(raw_result, PromptResult):
            return raw_result
        text = self._sanitize_response(raw_result)
        return PromptResult(text=text, blocks=[MessageBlock.text_block(text)])

    def _normalize_blocks(
        self,
        blocks: Optional[List[MessageBlock]],
        fallback_text: str,
    ) -> List[MessageBlock]:
        if not blocks:
            return [MessageBlock.text_block(fallback_text)]
        normalized: List[MessageBlock] = []
        for block in blocks:
            dup = block.copy()
            if dup.type is MessageBlockType.TEXT and dup.text is not None:
                dup.text = self._sanitize_response(dup.text)
            normalized.append(dup)
        return normalized


def resolve_prompt_channel(workspace_hook: Any) -> PromptChannel | None:
    """Helper to fetch a PromptChannel from a workspace hook if available."""

    if workspace_hook is None:
        return None

    getter = getattr(workspace_hook, "get_prompt_channel", None)
    if callable(getter):
        channel = getter()
        if channel is not None:
            return channel

    channel = getattr(workspace_hook, "prompt_channel", None)
    if channel is not None:
        return channel

    return None
