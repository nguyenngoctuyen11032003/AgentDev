"""WebSocket connection manager used by FastAPI app."""

import asyncio
import json
import logging
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import WebSocket, WebSocketException

from agentdev.api.services.message_handler import MessageHandler, client_error
from agentdev.api.services.attachment_service import AttachmentService
from agentdev.api.services.session_execution import SessionExecutionController
from agentdev.api.services.session_history import SessionHistoryStore
from agentdev.api.services.session_store import WorkflowSessionStore, SessionStatus
from agentdev.api.services.workflow_run_service import WorkflowRunService
from agentdev.api.services.websocket_logger import client_entry
from agentdev.utils.exceptions import ValidationError
from agentdev.utils.workspace_paths import validate_path_component


def _json_default(value):
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception:
            pass
    if hasattr(value, "__dict__"):
        try:
            return vars(value)
        except Exception:
            pass
    return str(value)


def _encode_ws_message(message: Any) -> str:
    if isinstance(message, str):
        return message
    return json.dumps(message, default=_json_default)


# A client that asks for it (`?batch=1`) gets the saved events as array frames of this many
# messages (type "batch") instead of one frame each; older clients keep the one-by-one replay.
REPLAY_BATCH_SIZE = 100


def _client_accepts_batches(websocket: Any) -> bool:
    try:
        return str(websocket.query_params.get("batch", "")) == "1"
    except Exception:
        return False


def _with_timestamp(message: Dict[str, Any]) -> Dict[str, Any]:
    """Return ``message`` with a top-level ``ts`` (ISO 8601 UTC) unless it already has one."""
    if not isinstance(message, dict) or message.get("ts"):
        return message
    return {**message, "ts": datetime.now(timezone.utc).isoformat()}


def _is_non_fatal_error(message: Dict[str, Any]) -> bool:
    data = message.get("data") if message.get("type") == "error" else None
    return isinstance(data, dict) and data.get("fatal") is False


class WebSocketManager:
    SESSION_TTL_SECONDS = 24 * 60 * 60  # 24 hours

    def __init__(
        self,
        *,
        session_store: WorkflowSessionStore | None = None,
        session_controller: SessionExecutionController | None = None,
        attachment_service: AttachmentService | None = None,
        workflow_run_service: WorkflowRunService | None = None,
    ):
        self.active_connections: Dict[str, WebSocket] = {}
        self.connection_timestamps: Dict[str, float] = {}
        self._owner_loop: Optional[asyncio.AbstractEventLoop] = None
        self._gc_task: Optional[asyncio.Task] = None
        self._sync_tasks: set = set()  # send tasks started from the loop thread (kept referenced until done)
        # Live messages for a socket that is still replaying the buffer, keyed by id(socket);
        # flushed in order once the replay is done so nothing overtakes older history.
        self._replay_queues: Dict[int, list] = {}
        self.session_store = session_store or WorkflowSessionStore(history=SessionHistoryStore())
        self.session_controller = session_controller or SessionExecutionController(self.session_store)
        self.attachment_service = attachment_service or AttachmentService()
        self.workflow_run_service = workflow_run_service or WorkflowRunService(
            self.session_store,
            self.session_controller,
            self.attachment_service,
        )
        self.message_handler = MessageHandler(
            self.session_store,
            self.session_controller,
            self.workflow_run_service,
        )

    async def connect(self, websocket: WebSocket, session_id: Optional[str] = None) -> str:
        if session_id:
            try:
                validate_path_component(session_id, field="session_id")
            except ValidationError as exc:
                raise WebSocketException(code=1008, reason=str(exc)) from exc
        await websocket.accept()
        # Capture the event loop that owns the WebSocket connections so that
        # worker threads can safely schedule sends via run_coroutine_threadsafe.
        if self._owner_loop is None:
            self._owner_loop = asyncio.get_running_loop()

        # --- Reconnect to existing session (live, or saved on disk before a restart) ---
        if session_id and self.session_store.restore_session(session_id):
            # If an old WebSocket is still tied to this session, close it first
            if session_id in self.active_connections:
                old_ws = self.active_connections[session_id]
                try:
                    # Say it in a message too: proxies (e.g. the Vite dev proxy) can drop the close
                    # reason, and a tab that sees a plain drop would reconnect and take it back.
                    await old_ws.send_text(json.dumps({"type": "session_replaced", "data": {"session_id": session_id}}))
                except Exception:
                    pass
                try:
                    await old_ws.close(code=1000, reason="Replaced by new connection")
                except Exception:
                    pass

            # Register the socket, start queueing live messages and snapshot the buffer in
            # one synchronous step: every message is then either replayed or queued, once.
            self.active_connections[session_id] = websocket
            self.connection_timestamps[session_id] = time.time()
            queue: list = []
            self._replay_queues[id(websocket)] = queue
            session = self.session_store.get_session(session_id)
            messages_to_replay = list(session.message_buffer) if session else []
            logging.info("WebSocket reconnected to existing session: %s", session_id)

            # Always start the GC loop (idempotent)
            self._start_gc()

            # Replay goes to *this* socket only, and stops as soon as a newer socket
            # replaces it (that one gets its own full replay) to avoid duplicated rows.
            def still_current() -> bool:
                return self.active_connections.get(session_id) is websocket

            try:
                await self._send_to(
                    websocket,
                    session_id,
                    {"type": "connection", "data": {"session_id": session_id, "status": "connected", "resumed": True}},
                )
                batched = _client_accepts_batches(websocket)
                chunk: list = []
                for msg in messages_to_replay:
                    if not still_current():
                        return session_id
                    # Sessions saved before log entries were trimmed for the client carry whole
                    # model prompts; trim them on the way out too.
                    if isinstance(msg, dict) and msg.get("type") == "log" and isinstance(msg.get("data"), dict):
                        msg = {**msg, "data": client_entry(msg["data"])}
                    if not batched:
                        await self._send_to(websocket, session_id, msg)
                        continue
                    chunk.append(msg)
                    if len(chunk) >= REPLAY_BATCH_SIZE:
                        await self._send_to(websocket, session_id, {"type": "batch", "data": chunk})
                        chunk = []
                if chunk and still_current():
                    await self._send_to(websocket, session_id, {"type": "batch", "data": chunk})

                snapshot = self.session_store.get_session_snapshot(session_id)
                if snapshot and still_current():
                    await self._send_to(websocket, session_id, {"type": "session_resumed", "data": snapshot})

                # Live messages that arrived meanwhile, in order (more may arrive while flushing)
                while queue and still_current():
                    await self._send_to(websocket, session_id, queue.pop(0))
            finally:
                # No await between the last empty check and this: nothing can be lost.
                self._replay_queues.pop(id(websocket), None)

            return session_id

        # --- New connection ---
        if not session_id:
            session_id = str(uuid.uuid4())
        self.active_connections[session_id] = websocket
        self.connection_timestamps[session_id] = time.time()
        logging.info("WebSocket connected: %s", session_id)

        # Always start the GC loop (idempotent)
        self._start_gc()

        await self.send_message(
            session_id,
            {
                "type": "connection",
                "data": {"session_id": session_id, "status": "connected"},
            },
        )
        return session_id

    def disconnect(self, session_id: str, websocket: Optional[WebSocket] = None) -> None:
        """Forget the socket of ``session_id``.

        With ``websocket``, only when it is still the current one: a socket that was
        replaced by a newer connection must not unregister its successor.
        """
        if websocket is not None and self.active_connections.get(session_id) is not websocket:
            logging.info("Stale WebSocket disconnected (newer connection kept): %s", session_id)
            return
        self.active_connections.pop(session_id, None)
        self.connection_timestamps.pop(session_id, None)
        logging.info("WebSocket disconnected (session preserved): %s", session_id)

    async def send_message(self, session_id: str, message: Dict[str, Any]) -> None:
        message = _with_timestamp(message)
        encoded = _encode_ws_message(message)
        # Buffer business messages for reconnection replay (exclude transport messages and
        # non-fatal errors: a rejected click must not reappear as a failure on replay)
        if message.get("type") not in ("connection", "pong") and not _is_non_fatal_error(message):
            self.session_store.record_message(session_id, message, encoded)

        if session_id in self.active_connections:
            websocket = self.active_connections[session_id]
            queue = self._replay_queues.get(id(websocket))
            if queue is not None:
                queue.append(message)
                return
            try:
                await websocket.send_text(encoded)
            except Exception as exc:
                traceback.print_exc()
                logging.error("Failed to send message to %s: %s", session_id, exc)

    def record_user_message(self, session_id: str, text: str, attachment_ids: Optional[list] = None) -> None:
        """Buffer what the user typed so a replay shows both sides of the conversation.

        The browser renders its own message immediately, so this is stored but not sent.
        """
        names = []
        if attachment_ids:
            try:
                manifest = self.attachment_service.list_attachment_manifests(session_id)
            except Exception:
                manifest = {}
            for attachment_id in attachment_ids:
                ref = (manifest.get(attachment_id) or {}).get("ref") or {}
                names.append(ref.get("name") or attachment_id)
        message = _with_timestamp({"type": "user_message", "data": {"text": text or "", "attachments": names}})
        self.session_store.record_message(session_id, message, _encode_ws_message(message))

    def record_user_note(self, session_id: str, text: str) -> None:
        """Buffer a note the user wrote mid-run (stored, not sent: the browser shows it itself)."""
        message = _with_timestamp({"type": "user_note", "data": {"text": text or ""}})
        self.session_store.record_message(session_id, message, _encode_ws_message(message))

    async def _send_raw(self, session_id: str, message: Dict[str, Any]) -> None:
        """Send a message without buffering. Used for replay and connection management."""
        if session_id in self.active_connections:
            websocket = self.active_connections[session_id]
            try:
                await websocket.send_text(_encode_ws_message(message))
            except Exception as exc:
                traceback.print_exc()
                logging.error("Failed to send raw message to %s: %s", session_id, exc)

    async def _send_to(self, websocket: WebSocket, session_id: str, message: Dict[str, Any]) -> None:
        """Send a message to one specific socket without buffering (used for replay)."""
        try:
            await websocket.send_text(_encode_ws_message(message))
        except Exception as exc:
            traceback.print_exc()
            logging.error("Failed to send replay message to %s: %s", session_id, exc)

    def send_message_sync(self, session_id: str, message: Dict[str, Any]) -> None:
        """Send a WebSocket message from any thread (including worker threads).

        WebSocket objects are bound to the event loop that created them (the main
        uvicorn loop).  Previous code called ``asyncio.run()`` from worker threads
        which spins up a *new* event loop, causing ``RuntimeError: … attached to a
        different loop`` or silent delivery failures.

        The fix: always schedule the coroutine on the loop that owns the sockets
        via ``asyncio.run_coroutine_threadsafe`` and wait for the result with a
        short timeout so the caller knows if delivery failed.
        """
        loop = self._owner_loop
        if loop is None or loop.is_closed():
            logging.warning(
                "Cannot send sync message to %s: owner event loop unavailable",
                session_id,
            )
            return

        try:
            on_owner_loop = asyncio.get_running_loop() is loop
        except RuntimeError:
            on_owner_loop = False
        if on_owner_loop:
            # Called from the loop's own thread (e.g. while a run is being built): waiting on a
            # future the blocked loop must complete would stall it for the whole timeout.
            task = loop.create_task(self.send_message(session_id, message))
            self._sync_tasks.add(task)
            task.add_done_callback(self._sync_tasks.discard)
            return

        future = asyncio.run_coroutine_threadsafe(
            self.send_message(session_id, message), loop
        )
        try:
            future.result(timeout=10)
        except TimeoutError:
            logging.warning(
                "Timed out sending sync WS message to %s", session_id
            )
        except Exception as exc:
            logging.error(
                "Error sending sync WS message to %s: %s", session_id, exc
            )

    async def broadcast(self, message: Dict[str, Any]) -> None:
        for session_id in list(self.active_connections.keys()):
            await self.send_message(session_id, message)

    async def handle_heartbeat(self, session_id: str) -> None:
        if session_id in self.active_connections:
            await self.send_message(
                session_id,
                {"type": "pong", "data": {"timestamp": time.time()}},
            )
        else:
            logging.warning("Heartbeat request from disconnected session: %s", session_id)

    async def handle_message(self, session_id: str, message: str) -> None:
        try:
            data = json.loads(message)
            await self.message_handler.handle_message(session_id, data, self)
        except json.JSONDecodeError:
            await self.send_message(session_id, client_error("Invalid JSON format", "invalid_json"))
        except Exception as exc:
            logging.error("Error handling message from %s: %s", session_id, exc)
            await self.send_message(session_id, client_error(str(exc), "message_failed"))

    def _start_gc(self) -> None:
        """Start the background GC task if not already running."""
        if self._gc_task is not None and not self._gc_task.done():
            return
        loop = asyncio.get_running_loop()
        self._gc_task = loop.create_task(self._gc_loop())

    async def _gc_loop(self) -> None:
        """Periodically clean up terminal sessions older than TTL."""
        TERMINAL = {SessionStatus.COMPLETED, SessionStatus.ERROR, SessionStatus.CANCELLED}
        while True:
            await asyncio.sleep(3600)  # run every hour
            now = time.time()
            to_remove = []
            for sid, session in self.session_store._sessions.items():
                if session.status in TERMINAL:
                    if now - session.updated_at > self.SESSION_TTL_SECONDS:
                        to_remove.append(sid)
            for sid in to_remove:
                self.session_store.pop_session(sid)
                self.attachment_service.cleanup_session(sid)
                logging.info("GC: removed expired session %s", sid)
