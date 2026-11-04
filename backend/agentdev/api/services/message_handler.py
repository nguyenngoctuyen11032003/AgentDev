import logging
from typing import Any, Dict

from agentdev.runtime.node.agent.interject import get_run_inbox, route_note
from agentdev.utils.exceptions import ValidationError

from agentdev.api.services.session_execution import SessionExecutionController
from agentdev.api.services.session_store import WorkflowSessionStore

# Error contract for {"type": "error", "data": {...}} WebSocket messages:
#   fatal: true  -> the run itself failed/ended (sent by WorkflowRunService); buffered for replay.
#   fatal: false -> a rejected client message; the run (if any) keeps going; never buffered.
# Non-fatal ``code`` values:
#   invalid_json      - the socket message was not JSON
#   unknown_type      - unknown socket message ``type``
#   empty_input       - human_input with no text and no attachments
#   not_waiting       - human_input while no node is waiting for it
#   session_not_found - human_input for an unknown session
#   invalid_input     - other rejected human_input
#   message_failed    - unexpected error while handling a socket message
#   run_in_progress   - a launch while a run is already live in this session
#   not_running       - interject while no run is live (carries ``note_id``): send it as a normal message
# Fatal ``code`` values: start_failed, validation_error, run_failed.


def client_error(message: str, code: str) -> Dict[str, Any]:
    """A non-fatal error about a client message; the run keeps going."""
    return {"type": "error", "data": {"message": message, "code": code, "fatal": False}}


def _validation_code(exc: Exception) -> str:
    text = str(exc).lower()
    if "not waiting" in text:
        return "not_waiting"
    if "session not found" in text:
        return "session_not_found"
    return "invalid_input"


class MessageHandler:
    """Routes WebSocket messages to the appropriate handlers."""

    def __init__(
        self,
        session_store: WorkflowSessionStore,
        session_controller: SessionExecutionController,
        workflow_run_service=None,
    ) -> None:
        self.session_store = session_store
        self.session_controller = session_controller
        self.workflow_run_service = workflow_run_service
        self.logger = logging.getLogger(__name__)

    async def handle_message(self, session_id: str, data: Dict[str, Any], websocket_manager):
        message_type = data.get("type")
        if message_type == "human_input":
            await self._handle_human_input(session_id, data, websocket_manager)
        elif message_type == "interject":
            await self._handle_interject(session_id, data, websocket_manager)
        elif message_type == "ping":
            await self._handle_ping(session_id, websocket_manager)
        elif message_type == "get_status":
            await self._handle_get_status(session_id, websocket_manager)
        elif message_type == "cancel":
            await self._handle_cancel(session_id, websocket_manager)
        else:
            await websocket_manager.send_message(
                session_id,
                client_error(f"Unknown message type: {message_type}", "unknown_type"),
            )

    async def _handle_cancel(self, session_id: str, websocket_manager):
        if self.workflow_run_service:
            self.workflow_run_service.request_cancel(session_id, reason="User requested cancellation")
        await websocket_manager.send_message(
            session_id,
            {"type": "input_received", "data": {"message": "Cancellation requested"}},
        )

    async def _handle_human_input(self, session_id: str, data: Dict[str, Any], websocket_manager):
        try:
            payload = data.get("data", {}) or {}
            user_input = payload.get("input", "")
            attachments = payload.get("attachments") or []

            if not user_input and not attachments:
                await websocket_manager.send_message(session_id, client_error("Empty input", "empty_input"))
                return

            self.session_controller.provide_human_input(
                session_id,
                {"text": user_input, "attachments": attachments},
            )
            websocket_manager.record_user_message(session_id, user_input, attachments)

            await websocket_manager.send_message(
                session_id,
                {"type": "input_received", "data": {"message": "Input received"}},
            )

        except ValidationError as exc:
            await websocket_manager.send_message(session_id, client_error(str(exc), _validation_code(exc)))
        except Exception as exc:
            self.logger.error("Error handling human input for session %s: %s", session_id, exc)
            await websocket_manager.send_message(session_id, client_error(str(exc), "message_failed"))

    async def _handle_interject(self, session_id: str, data: Dict[str, Any], websocket_manager):
        """A message the user sent while the team works: answered at once (status) or handed to the lead."""
        payload = data.get("data", {}) or {}
        text = str(payload.get("text") or "").strip()
        note_id = str(payload.get("id") or "")[:64]
        if not text:
            await websocket_manager.send_message(session_id, client_error("Empty input", "empty_input"))
            return
        session = self.session_store.get_session(session_id)
        executor = getattr(session, "executor", None) if session else None
        global_state = getattr(getattr(executor, "runtime_context", None), "global_state", None)
        if global_state is None or getattr(session, "cancel_event", None) is not None and session.cancel_event.is_set():
            error = client_error("No run is going on in this session", "not_running")
            error["data"]["note_id"] = note_id
            await websocket_manager.send_message(session_id, error)
            return

        lead = self._lead_id(session)
        kind, reply, note = route_note(
            text,
            global_state,
            note_id=note_id,
            lead=lead,
            locale=str(payload.get("locale") or ""),
            waiting=bool(session.waiting_for_input),
        )
        if note is not None:
            # Tell the user when the lead really picks the note up (it runs in a worker thread)
            get_run_inbox(global_state).on_event = lambda message: websocket_manager.send_message_sync(session_id, message)
        websocket_manager.record_user_note(session_id, text)
        await websocket_manager.send_message(
            session_id,
            {"type": "lead_note_reply", "data": {"note_id": note_id, "lead": lead, "kind": kind, "text": reply}},
        )

    @staticmethod
    def _lead_id(session) -> str:
        """The entry agent that answers the user: the first start node of the graph."""
        graph = getattr(session, "graph", None)
        starts = list(getattr(graph, "start_nodes", None) or [])
        return str(starts[0]) if starts else ""

    async def _handle_ping(self, session_id: str, websocket_manager):
        await websocket_manager.handle_heartbeat(session_id)

    async def _handle_get_status(self, session_id: str, websocket_manager):
        session_info = self.session_store.get_session_info(session_id)
        await websocket_manager.send_message(
            session_id,
            {"type": "status", "data": session_info or {"message": "Session not found"}},
        )
