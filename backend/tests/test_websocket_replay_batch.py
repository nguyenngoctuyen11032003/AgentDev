"""Replay of a saved session: one frame per message for old clients, array frames on request."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from agentdev.api.services.websocket_manager import REPLAY_BATCH_SIZE, WebSocketManager


class _Socket:
    def __init__(self, batch: bool) -> None:
        self.query_params = {"batch": "1"} if batch else {}
        self.sent = []

    async def accept(self) -> None:
        pass

    async def send_text(self, data: str) -> None:
        self.sent.append(json.loads(data))


def _replay(batch: bool, count: int):
    store = MagicMock()
    store.restore_session.return_value = True
    store.get_session.return_value = SimpleNamespace(
        message_buffer=[{"type": "stage", "data": {"i": i}} for i in range(count)]
    )
    store.get_session_snapshot.return_value = {"session_id": "s1", "status": "idle"}
    manager = WebSocketManager(
        session_store=store,
        session_controller=MagicMock(),
        attachment_service=MagicMock(),
        workflow_run_service=MagicMock(),
    )
    manager._start_gc = lambda: None
    socket = _Socket(batch)
    asyncio.run(manager.connect(socket, session_id="s1"))
    return socket.sent


def test_old_clients_get_one_frame_per_message():
    sent = _replay(False, 5)
    assert [m["type"] for m in sent] == ["connection"] + ["stage"] * 5 + ["session_resumed"]


def test_batch_clients_get_array_frames_in_order():
    count = REPLAY_BATCH_SIZE * 2 + 7
    sent = _replay(True, count)
    assert sent[0]["type"] == "connection"
    assert sent[-1]["type"] == "session_resumed"
    frames = sent[1:-1]
    assert [f["type"] for f in frames] == ["batch"] * 3
    assert [len(f["data"]) for f in frames] == [REPLAY_BATCH_SIZE, REPLAY_BATCH_SIZE, 7]
    assert [m["data"]["i"] for f in frames for m in f["data"]] == list(range(count))
