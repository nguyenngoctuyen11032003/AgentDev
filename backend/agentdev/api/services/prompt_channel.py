"""PromptChannel implementation backed by WebSocket sessions."""

import asyncio
from typing import Any, Dict, List, Optional

from agentdev.entity.messages import MessageBlock
from agentdev.api.services.attachment_service import AttachmentService
from agentdev.api.services.session_execution import SessionExecutionController
from agentdev.utils.attachments import AttachmentStore
from agentdev.utils.exceptions import TimeoutError
from agentdev.utils.human_prompt import AUTO_SKIP_PAID, PromptChannel, PromptResult
from agentdev.utils.run_mode import DEFAULT_RUN_MODE, RUN_MODE_AUTO_ANSWER, answers_automatically, normalize_run_mode
from agentdev.utils.structured_logger import get_server_logger


class WebPromptChannel(PromptChannel):
    """Prompt channel that mediates through the WebSocket session controller."""

    def __init__(
        self,
        *,
        session_id: str,
        session_controller: SessionExecutionController,
        websocket_manager: Any,
        attachment_service: AttachmentService,
        attachment_store: AttachmentStore,
        run_mode: str = DEFAULT_RUN_MODE,
    ) -> None:
        self.session_id = session_id
        self.run_mode = normalize_run_mode(run_mode)
        self.session_controller = session_controller
        self.websocket_manager = websocket_manager
        self.attachment_service = attachment_service
        self.attachment_store = attachment_store
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    def request(
        self,
        *,
        node_id: str,
        task: str,
        inputs: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> PromptResult:
        preview = inputs or ""
        if answers_automatically(self.run_mode, metadata):
            # The user chose not to be asked in this turn: answer for them, and say so in the chat
            self._send({
                "type": "auto_answered",
                "data": {
                    "node_id": node_id,
                    "task_description": task,
                    "answer": RUN_MODE_AUTO_ANSWER,
                    "mode": self.run_mode,
                },
            })
            return PromptResult(
                text=RUN_MODE_AUTO_ANSWER,
                blocks=[MessageBlock.text_block(RUN_MODE_AUTO_ANSWER)],
                metadata={"auto_answered": True, "run_mode": self.run_mode},
            )
        payload = {
            "input": preview,
            "task_description": task,
            **(metadata or {}),
        }

        self.session_controller.set_waiting_for_input(
            self.session_id,
            node_id,
            payload,
        )

        self._notify_human_prompt(node_id, preview, task, metadata)

        try:
            human_response = self.session_controller.wait_for_human_input(self.session_id)
        except TimeoutError:
            raise
        except Exception as exc:  # pragma: no cover - propagated upstream
            logger = get_server_logger()
            logger.log_exception(exc, "Error waiting for human input", node_id=node_id, session_id=self.session_id)
            raise

        if isinstance(human_response, dict) and human_response.get("timed_out"):
            # The run moves on without an answer: close the question in the UI instead of leaving it open
            self._send({"type": "human_input_timeout", "data": {"node_id": node_id}})
            meta = metadata or {}
            if str(meta.get("node_type") or "") == "human" and meta.get("paid"):
                # Silence is never approval, least of all at a paid gate: answer with the paid refusal, which
                # every edge out of a paid gate treats as "do not start the paid step" (see function_manager).
                human_response = {**human_response, "text": AUTO_SKIP_PAID}
        response_text, attachment_ids = self._extract_response(human_response)
        blocks = self._build_blocks(response_text, attachment_ids)
        metadata_out = {
            "attachment_count": len(attachment_ids),
            "input_size": len(preview),
        }
        return PromptResult(text=response_text, blocks=blocks, metadata=metadata_out)

    def _extract_response(self, payload: Any) -> tuple[str, List[str]]:
        if isinstance(payload, dict):
            response_text = payload.get("text") or ""
            attachments = payload.get("attachments") or []
            return response_text, attachments
        if payload is None:
            return "", []
        return str(payload), []

    def _build_blocks(self, text: str, attachment_ids: List[str]) -> List[MessageBlock]:
        blocks: List[MessageBlock] = []
        if text:
            blocks.append(MessageBlock.text_block(text))
        if attachment_ids:
            blocks.extend(
                self.attachment_service.build_attachment_blocks(
                    self.session_id,
                    attachment_ids,
                    target_store=self.attachment_store,
                )
            )
        if not blocks:
            blocks.append(MessageBlock.text_block(""))
        return blocks

    def _notify_human_prompt(
        self, node_id: str, preview: str, task: str, metadata: Optional[Dict[str, Any]] = None
    ) -> None:
        meta = metadata or {}
        node_type = str(meta.get("node_type") or "")
        self._send({
            "type": "human_input_required",
            "data": {
                "node_id": node_id,
                "input": preview,
                "task_description": task,
                # The chat marks an approval gate, and a paid one (costs money / cannot be undone) clearly
                "node_type": node_type,
                "paid": node_type == "human" and bool(meta.get("paid")),
            },
        })

    def _send(self, message: Dict[str, Any]) -> None:
        if self._loop and self._loop.is_running():
            future = asyncio.run_coroutine_threadsafe(
                self.websocket_manager.send_message(self.session_id, message),
                self._loop,
            )
            try:
                future.result()
            except Exception:
                # fallback to sync send to surface errors/logging
                self.websocket_manager.send_message_sync(self.session_id, message)
        else:
            self.websocket_manager.send_message_sync(self.session_id, message)
