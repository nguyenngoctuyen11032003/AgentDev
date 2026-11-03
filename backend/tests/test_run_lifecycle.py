"""Run lifecycle: one run per session, cancel, non-fatal socket errors, input timeout, replay order."""

import asyncio
import json
from types import SimpleNamespace

import pytest
import yaml

from agentdev.api.services import workflow_run_service as run_service_module
from agentdev.api.services.attachment_service import AttachmentService
from agentdev.api.services.session_execution import NO_REPLY_TEXT, SessionExecutionController
from agentdev.api.services.session_history import SessionHistoryStore
from agentdev.api.services.session_store import (
    SessionBusyError,
    SessionStatus,
    WorkflowSession,
    WorkflowSessionStore,
)
from agentdev.api.services.websocket_manager import WebSocketManager
from agentdev.api.services.workflow_run_service import WorkflowRunService
from agentdev.runtime.node.executor import agent_executor as agent_executor_module


class FakeSocketManager:
    def __init__(self):
        self.sent = []

    async def send_message(self, session_id, message):
        self.sent.append(message)

    def send_message_sync(self, session_id, message):
        self.sent.append(message)

    def record_user_message(self, session_id, text, attachment_ids=None):
        pass


class FakeWebSocket:
    """Yields on every send, like a real socket, so other tasks can interleave."""

    def __init__(self):
        self.sent = []

    async def accept(self):
        pass

    async def close(self, code=1000, reason=""):
        pass

    async def send_text(self, text):
        await asyncio.sleep(0)
        self.sent.append(json.loads(text))


@pytest.fixture()
def run_service(tmp_path, monkeypatch):
    yaml_dir = tmp_path / "yaml"
    yaml_dir.mkdir()
    agent = {"connection": "fake", "provider": "fake", "name": "fake-model", "role": "Lead"}
    definition = {
        "version": "0.4.0",
        "graph": {
            "id": "solo",
            "start": ["Lead"],
            "end": ["Lead"],
            "nodes": [{"id": "Lead", "type": "agent", "description": "Lead", "config": agent}],
            "edges": [],
        },
    }
    (yaml_dir / "solo.yaml").write_text(yaml.safe_dump(definition), encoding="utf-8")
    monkeypatch.setattr(run_service_module, "YAML_DIR", yaml_dir)
    creds = SimpleNamespace(provider="fake", vendor="fake", token="", base_url="")
    monkeypatch.setattr(agent_executor_module, "resolve_connection", lambda _id: creds)

    executor_cls = run_service_module.WebSocketGraphExecutor
    monkeypatch.setattr(executor_cls, "get_final_output", lambda self: "done")
    monkeypatch.setattr(executor_cls, "get_results", lambda self: {})

    store = WorkflowSessionStore(history=SessionHistoryStore(root=tmp_path / "sessions"))
    controller = SessionExecutionController(store)
    service = WorkflowRunService(store, controller, AttachmentService())

    def patch_run(run):
        monkeypatch.setattr(executor_cls, "execute_graph_async", run)

    return service, store, patch_run


def _types(sent):
    return [m["type"] for m in sent]


# ------------------------------------------------------------- 1. double launch


def test_two_quick_launches_run_only_one_graph(run_service):
    service, store, patch_run = run_service
    calls = []

    async def slow_run(self, task_input):
        calls.append(task_input)
        await asyncio.sleep(0.05)

    patch_run(slow_run)
    socket = FakeSocketManager()

    async def both():
        await asyncio.gather(
            service.start_workflow("s1", "solo.yaml", "first", socket),
            service.start_workflow("s1", "solo.yaml", "second", socket),
        )

    asyncio.run(both())
    assert len(calls) == 1
    errors = [m for m in socket.sent if m["type"] == "error"]
    assert [e["data"]["code"] for e in errors] == ["run_in_progress"]
    assert errors[0]["data"]["fatal"] is False
    assert _types(socket.sent).count("workflow_completed") == 1
    session = store.get_session("s1")
    assert session.task_prompt == "first"
    assert session.executor is None and session.starting is False


def test_create_session_never_replaces_a_live_session(run_service):
    _, store, _ = run_service
    live = store.create_session(session_id="s2", yaml_file="solo.yaml", task_prompt="x")
    live.starting = True
    with pytest.raises(SessionBusyError):
        store.create_session(session_id="s2", yaml_file="solo.yaml", task_prompt="y")
    assert store.get_session("s2") is live


def test_cancel_reports_cancelled_only_when_the_run_ends(run_service):
    service, store, patch_run = run_service
    seen = {}

    async def run_until_cancelled(self, task_input):
        service.request_cancel("s3", reason="User requested cancellation")
        session = store.get_session("s3")
        seen["status"] = session.status
        seen["types"] = _types(socket.sent)
        seen["busy"] = run_service_module.run_in_progress(session)

    patch_run(run_until_cancelled)
    socket = FakeSocketManager()
    asyncio.run(service.start_workflow("s3", "solo.yaml", "go", socket))
    assert seen["status"] == SessionStatus.CANCELLING and seen["busy"]
    assert "workflow_cancelled" not in seen["types"]
    session = store.get_session("s3")
    assert socket.sent[-1]["type"] == "workflow_cancelled"
    assert session.status == SessionStatus.CANCELLED and session.executor is None
    assert not run_service_module.run_in_progress(session)


def test_follow_up_is_accepted_as_soon_as_the_end_is_announced(run_service):
    service, store, patch_run = run_service

    async def quick(self, task_input):
        return None

    patch_run(quick)
    busy_at_end = []

    class Probe(FakeSocketManager):
        async def send_message(self, session_id, message):
            if message["type"] == "workflow_completed":
                busy_at_end.append(run_service_module.run_in_progress(store.get_session(session_id)))
            await super().send_message(session_id, message)

    asyncio.run(service.start_workflow("s4", "solo.yaml", "go", Probe()))
    assert busy_at_end == [False]


# ------------------------------------------------------------- 3. error contract


def test_failed_run_error_is_fatal(run_service):
    service, _, patch_run = run_service

    async def boom(self, task_input):
        raise RuntimeError("provider crashed")

    patch_run(boom)
    socket = FakeSocketManager()
    asyncio.run(service.start_workflow("s5", "solo.yaml", "go", socket))
    error = socket.sent[-1]
    assert error["type"] == "error" and error["data"]["fatal"] is True and error["data"]["code"] == "run_failed"


def test_client_errors_are_non_fatal_and_not_replayed(tmp_path):
    store = WorkflowSessionStore()
    store.create_session(session_id="s6", yaml_file="solo.yaml", task_prompt="x")
    manager = WebSocketManager(session_store=store)
    ws = FakeWebSocket()
    manager.active_connections["s6"] = ws

    async def scenario():
        await manager.handle_message("s6", "{not json")
        await manager.handle_message("s6", json.dumps({"type": "human_input", "data": {"input": ""}}))
        await manager.handle_message("s6", json.dumps({"type": "human_input", "data": {"input": "hi"}}))

    asyncio.run(scenario())
    assert [(m["data"]["code"], m["data"]["fatal"]) for m in ws.sent] == [
        ("invalid_json", False),
        ("empty_input", False),
        ("not_waiting", False),
    ]
    assert store.get_session("s6").message_buffer == []


# ------------------------------------------------------------- 4. input timeout


def test_input_timeout_returns_a_proceed_with_default_reply():
    store = WorkflowSessionStore()
    store.create_session(session_id="s7", yaml_file="solo.yaml", task_prompt="x")
    controller = SessionExecutionController(store)
    controller.set_waiting_for_input("s7", "Lead", {"input": "Approve?"})
    reply = controller.wait_for_human_input("s7", timeout=0.05)
    assert reply["text"] == NO_REPLY_TEXT and reply["timed_out"] is True
    session = store.get_session("s7")
    assert session.waiting_for_input is False and session.status == SessionStatus.RUNNING


def test_cancel_while_waiting_still_raises():
    from agentdev.utils.exceptions import WorkflowCancelledError

    store = WorkflowSessionStore()
    store.create_session(session_id="s8", yaml_file="solo.yaml", task_prompt="x")
    controller = SessionExecutionController(store)
    controller.set_waiting_for_input("s8", "Lead", {})
    store.get_session("s8").cancel_event.set()
    with pytest.raises(WorkflowCancelledError):
        controller.wait_for_human_input("s8", timeout=5)


# ------------------------------------------------------------- 5. replay order


def test_live_messages_wait_for_the_replay_to_finish():
    store = WorkflowSessionStore()
    session = store.create_session(session_id="s9", yaml_file="solo.yaml", task_prompt="x")
    for i in range(5):
        session.append_message({"type": "old", "data": {"i": i}})
    manager = WebSocketManager(session_store=store)
    ws = FakeWebSocket()

    async def scenario():
        async def live():
            for i in range(3):
                await asyncio.sleep(0)
                await manager.send_message("s9", {"type": "live", "data": {"i": i}})

        await asyncio.gather(manager.connect(ws, "s9"), live())
        if manager._gc_task:
            manager._gc_task.cancel()

    asyncio.run(scenario())
    order = [(m["type"], m["data"].get("i")) for m in ws.sent if m["type"] in ("old", "live", "session_resumed")]
    assert order == [("old", i) for i in range(5)] + [("session_resumed", None)] + [("live", i) for i in range(3)]
    assert manager._replay_queues == {}


# ------------------------------------------------------------- 6. long sessions


def test_buffer_eviction_keeps_turn_start_user_messages():
    session = WorkflowSession(session_id="s10", yaml_file="", task_prompt="", MAX_BUFFER_SIZE=5)
    session.append_message({"type": "user_message", "data": {"text": "first"}})
    for i in range(20):
        session.append_message({"type": "chunk", "data": {"i": i}})
    session.append_message({"type": "user_message", "data": {"text": "second"}})
    session.append_message({"type": "chunk", "data": {"i": 99}})
    texts = [m["data"].get("text") for m in session.message_buffer if m["type"] == "user_message"]
    assert texts == ["first", "second"] and len(session.message_buffer) == 5
