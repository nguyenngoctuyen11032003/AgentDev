"""Reviewing delivered work: the digest of a run and the user's verdict on it."""

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api import state
from agentdev.api.routes import sessions
from agentdev.api.services.session_review import build_digest
from agentdev.api.services.session_store import SessionStatus
from agentdev.api.services.websocket_manager import WebSocketManager


def _log(node, event, at, output=None):
    data = {"node_id": node, "event_type": event, "timestamp": f"2026-11-03T10:00:{at:02d}"}
    if output is not None:
        data["details"] = {"output": output}
    return {"type": "log", "data": data}


RUN = [
    {"type": "user_message", "data": {"text": "Build a todo app", "attachments": ["spec.md"]}},
    _log("CTO", "NODE_START", 0),
    _log("CTO", "NODE_END", 5, "Plan: API + UI"),
    _log("Dev", "NODE_START", 6),
    {"type": "artifact_created", "data": {"events": [
        {"relative_path": "src/app.py", "file_name": "app.py", "change_type": "created", "node_id": "Dev"},
        {"relative_path": "src/app.py", "file_name": "app.py", "change_type": "updated", "node_id": "Dev"},
    ]}},
    {"type": "user_message", "data": {"text": "use sqlite"}},
    _log("Dev", "NODE_END", 20, "Implemented"),
    _log("Dev", "NODE_START", 21),
    _log("Dev", "NODE_END", 30, "Implemented with sqlite"),
    {"type": "workflow_completed", "data": {"summary": "Todo app ready", "token_usage": {"total_tokens": 1200}}},
]


def test_digest_condenses_a_run():
    digest = build_digest(RUN)
    assert digest["task"] == {"text": "Build a todo app", "attachments": ["spec.md"]}
    assert digest["replies"] == ["use sqlite"]
    assert [s["node_id"] for s in digest["steps"]] == ["CTO", "Dev"]
    dev = digest["steps"][1]
    assert dev["runs"] == 2 and dev["output"] == "Implemented with sqlite"
    assert digest["files"] == [
        {"path": "src/app.py", "name": "app.py", "change": "created", "node_id": "Dev", "size": None, "attachment_id": None}
    ]
    assert digest["outcome"] == "completed" and digest["summary"] == "Todo app ready"
    assert digest["ended_at"] - digest["started_at"] == 30_000


def test_last_hand_over_is_the_result_without_a_summary():
    digest = build_digest(RUN[:-1])
    assert digest["outcome"] == "" and digest["summary"] == "Implemented with sqlite"


@pytest.fixture
def api(monkeypatch, tmp_path):
    from agentdev.api.services import session_history

    monkeypatch.setattr(session_history, "SESSIONS_DIR", tmp_path / "sessions")
    manager = WebSocketManager()
    monkeypatch.setattr(manager, "_start_gc", lambda: None)
    monkeypatch.setattr(state, "websocket_manager", manager)
    app = FastAPI()
    app.include_router(sessions.router)
    with TestClient(app) as client:
        yield client, manager


def _finished_run(manager, session_id="run-1"):
    store = manager.session_store
    store.create_session(session_id=session_id, yaml_file="dev.yaml", task_prompt="Build a todo app")
    for message in RUN:
        store.record_message(session_id, message, json.dumps(message))
    store.update_session_status(session_id, SessionStatus.COMPLETED)


def test_review_is_saved_listed_and_keeps_history(api):
    client, manager = api
    if manager.session_store.history is None:
        pytest.skip("session history is disabled in this build")
    _finished_run(manager)

    digest = client.get("/api/sessions/run-1/digest").json()
    assert digest["digest"]["summary"] == "Todo app ready" and digest["review"] is None

    first = client.put("/api/sessions/run-1/review", json={
        "verdict": "rework", "rating": 2, "tags": ["Missing tests"], "feedback": "Add tests", "rework_session_id": "run-2",
    })
    assert first.status_code == 200 and first.json()["review"]["rework_session_id"] == "run-2"

    second = client.put("/api/sessions/run-1/review", json={"verdict": "approved", "rating": 5})
    review = second.json()["review"]
    assert review["verdict"] == "approved" and review["rework_session_id"] == "run-2"
    assert [h["verdict"] for h in review["history"]] == ["rework"]

    listed = {item["session_id"]: item for item in client.get("/api/sessions").json()["sessions"]}
    assert listed["run-1"]["review"]["verdict"] == "approved"


def test_review_rejects_bad_input_and_running_sessions(api):
    client, manager = api
    if manager.session_store.history is None:
        pytest.skip("session history is disabled in this build")
    _finished_run(manager)
    assert client.put("/api/sessions/run-1/review", json={"verdict": "great"}).status_code == 400
    assert client.put("/api/sessions/run-1/review", json={"verdict": "approved", "rating": 9}).status_code == 422
    assert client.get("/api/sessions/missing/digest").status_code == 404
    manager.session_store.update_session_status("run-1", SessionStatus.RUNNING)
    assert client.put("/api/sessions/run-1/review", json={"verdict": "approved"}).status_code == 409
