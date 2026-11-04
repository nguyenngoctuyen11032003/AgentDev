"""Chat -> run pipeline: cheaper persistence, listing and sending (no behaviour change)."""

import asyncio
import json
import time

from agentdev.api.services.session_history import MESSAGES_FILE, SessionHistoryStore
from agentdev.api.services.session_store import (
    COMPACT_LOG_FACTOR,
    SessionStatus,
    WorkflowSession,
    WorkflowSessionStore,
)
from agentdev.api.services.websocket_manager import WebSocketManager


def _lines(root, session_id):
    return (root / session_id / MESSAGES_FILE).read_text(encoding="utf-8").splitlines()


def test_append_keeps_one_handle_and_is_readable_at_once(tmp_path):
    history = SessionHistoryStore(tmp_path)
    for i in range(50):
        history.append_message("s1", json.dumps({"type": "log", "i": i}))
        # Another reader (a second store, a restart) sees every line right away
        assert len(_lines(tmp_path, "s1")) == i + 1
    assert len(history._streams) == 1
    assert [m["i"] for m in history.load_messages("s1", 0)] == list(range(50))


def test_close_stream_then_append_reopens(tmp_path):
    history = SessionHistoryStore(tmp_path)
    history.append_message("s1", '{"a": 1}')
    history.close_stream("s1")
    assert history._streams == {}
    history.append_message("s1", '{"a": 2}')
    assert _lines(tmp_path, "s1") == ['{"a": 1}', '{"a": 2}']


def test_delete_closes_the_handle_and_removes_the_folder(tmp_path):
    history = SessionHistoryStore(tmp_path)
    history.append_message("s1", '{"a": 1}')
    assert history.delete("s1") is True
    assert not (tmp_path / "s1").exists()
    assert history._streams == {}


def test_open_handles_are_bounded(tmp_path):
    history = SessionHistoryStore(tmp_path)
    for i in range(40):
        history.append_message(f"s{i}", '{"a": 1}')
    assert len(history._streams) <= 16
    assert all((tmp_path / f"s{i}" / MESSAGES_FILE).is_file() for i in range(40))


def test_invalid_session_id_is_ignored(tmp_path):
    history = SessionHistoryStore(tmp_path)
    history.append_message("../evil", '{"a": 1}')
    assert list(tmp_path.iterdir()) == []


def test_rewrite_messages_replaces_the_log(tmp_path):
    history = SessionHistoryStore(tmp_path)
    for i in range(5):
        history.append_message("s1", json.dumps({"i": i}))
    history.rewrite_messages("s1", [{"i": 3}, {"i": 4}])
    history.append_message("s1", json.dumps({"i": 5}))
    assert [m["i"] for m in history.load_messages("s1", 0)] == [3, 4, 5]


def test_list_meta_reuses_unchanged_files_and_sees_changes(tmp_path):
    history = SessionHistoryStore(tmp_path)
    history.save_meta({"session_id": "a", "title": "first", "updated_at": 1})
    history.save_meta({"session_id": "b", "title": "second", "updated_at": 2})

    first = history.list_meta()
    assert [m["session_id"] for m in first] == ["b", "a"]
    first[0]["extra"] = "caller change"  # must not leak into the cache
    assert "extra" not in history.list_meta()[0]

    reads = []
    original = history._read_json
    history._read_json = lambda path: (reads.append(path.name), original(path))[1]
    history.list_meta()
    assert reads == []  # nothing re-parsed

    history.rename("a", "renamed")
    assert {m["session_id"]: m["title"] for m in history.list_meta()}["a"] == "renamed"
    history.save_review("a", {"verdict": "good"})
    assert next(m for m in history.list_meta() if m["session_id"] == "a")["review"] == {"verdict": "good"}
    history.delete("b")
    assert [m["session_id"] for m in history.list_meta()] == ["a"]


def test_restore_compacts_an_oversized_log_and_keeps_files_changed(tmp_path):
    store = WorkflowSessionStore(SessionHistoryStore(tmp_path))
    store.create_session(session_id="s1", yaml_file="w.yaml", task_prompt="Build it")
    total = COMPACT_LOG_FACTOR * WorkflowSession.MAX_BUFFER_SIZE + 50
    store.record_message("s1", {"type": "user_message", "data": {"text": "Build it"}}, '{"type": "user_message", "data": {"text": "Build it"}}')
    changed = {"type": "artifact_created", "data": {"events": [{"file_name": "a.txt"}]}}
    store.record_message("s1", changed, json.dumps(changed))
    for i in range(total):
        store.record_message("s1", {"type": "log", "data": i}, json.dumps({"type": "log", "data": i}))
    assert len(_lines(tmp_path, "s1")) == total + 2

    store.history.close_stream("s1")  # the old process is gone: its handle is closed with it
    restored = WorkflowSessionStore(SessionHistoryStore(tmp_path)).restore_session("s1")

    assert restored.files_changed is True
    assert len(restored.message_buffer) == WorkflowSession.MAX_BUFFER_SIZE
    assert restored.message_buffer[0]["type"] == "user_message"
    assert len(_lines(tmp_path, "s1")) == WorkflowSession.MAX_BUFFER_SIZE
    # The artifact message was evicted from the log, yet a second restart still knows files changed
    again = WorkflowSessionStore(SessionHistoryStore(tmp_path)).restore_session("s1")
    assert again.files_changed is True


def test_run_end_messages_release_the_log_handle(tmp_path):
    store = WorkflowSessionStore(SessionHistoryStore(tmp_path))
    store.create_session(session_id="s1", yaml_file="w.yaml", task_prompt="x")
    store.update_session_status("s1", SessionStatus.RUNNING)
    store.record_message("s1", {"type": "log"}, '{"type": "log"}')
    assert "s1" in store.history._streams
    store.record_message("s1", {"type": "workflow_completed"}, '{"type": "workflow_completed"}')
    assert "s1" not in store.history._streams
    store.record_message("s1", {"type": "log"}, '{"type": "log"}')
    store.update_session_status("s1", SessionStatus.COMPLETED)
    assert "s1" not in store.history._streams


class _FakeSocket:
    def __init__(self):
        self.sent = []

    async def accept(self):
        pass

    async def send_text(self, data):
        self.sent.append(data)


def test_send_message_sync_on_the_loop_thread_does_not_block(tmp_path):
    manager = WebSocketManager(session_store=WorkflowSessionStore(SessionHistoryStore(tmp_path)))
    socket = _FakeSocket()

    async def run():
        sid = await manager.connect(socket, session_id="s1")
        socket.sent.clear()
        started = time.monotonic()
        manager.send_message_sync(sid, {"type": "test", "data": "hello"})
        elapsed = time.monotonic() - started
        await asyncio.sleep(0.05)
        return elapsed

    elapsed = asyncio.run(run())
    assert elapsed < 1.0  # used to wait for its own loop for the whole 10 s timeout
    assert len(socket.sent) == 1 and '"test"' in socket.sent[0]
