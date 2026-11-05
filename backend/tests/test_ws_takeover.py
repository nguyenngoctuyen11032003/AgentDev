"""Reload while a run waits at a human gate: the reloaded tab must keep the session."""

import asyncio
import json

from agentdev.api.services.session_store import WorkflowSessionStore
from agentdev.api.services.websocket_manager import WebSocketManager


class _Socket:
    def __init__(self, slow_close=False):
        self.sent = []
        self.closed = None
        self._release = asyncio.Event() if slow_close else None

    async def accept(self):
        pass

    async def send_text(self, text):
        await asyncio.sleep(0)
        self.sent.append(json.loads(text))

    async def close(self, code=1000, reason=""):
        if self._release is not None:
            await self._release.wait()  # a gone page: the close handshake never answers quickly
        self.closed = reason

    def types(self):
        return [m.get("type") for m in self.sent]


def _manager():
    store = WorkflowSessionStore()
    store.create_session(session_id="gate", yaml_file="w.yaml", task_prompt="x")
    store.get_session("gate").append_message({"type": "human_input_required", "data": {"node_id": "Gate"}})
    return WebSocketManager(session_store=store)


def test_reloaded_tab_is_registered_without_waiting_for_the_old_socket_to_close():
    async def scenario():
        manager = _manager()
        old = _Socket(slow_close=True)
        await manager.connect(old, session_id="gate", client_id="page-1", seq=1)
        new = _Socket()
        task = asyncio.create_task(manager.connect(new, session_id="gate", client_id="page-2", seq=1))
        for _ in range(20):
            await asyncio.sleep(0)
        registered = manager.active_connections.get("gate") is new
        replayed = "connection" in new.types()
        old._release.set()
        await task
        await asyncio.sleep(0.01)
        return registered, replayed, new, old

    registered, replayed, new, old = asyncio.run(scenario())
    assert registered and replayed
    assert "session_replaced" not in new.types() and new.closed is None
    assert "session_replaced" in old.types() and old.closed == "Replaced by new connection"


def test_older_connect_in_flight_never_closes_a_newer_page():
    async def scenario():
        manager = _manager()
        old = _Socket(slow_close=True)
        await manager.connect(old, session_id="gate", client_id="page-1", seq=1)
        first = _Socket()
        second = _Socket()
        t1 = asyncio.create_task(manager.connect(first, session_id="gate", client_id="page-2", seq=1))
        await asyncio.sleep(0)
        t2 = asyncio.create_task(manager.connect(second, session_id="gate", client_id="page-3", seq=1))
        for _ in range(20):
            await asyncio.sleep(0)
        old._release.set()
        await asyncio.gather(t1, t2)
        await asyncio.sleep(0.01)
        return manager, first, second

    manager, first, second = asyncio.run(scenario())
    assert manager.active_connections["gate"] is second  # the newest arrival wins
    assert second.closed is None and "session_replaced" not in second.types()
    assert "session_replaced" in first.types()
