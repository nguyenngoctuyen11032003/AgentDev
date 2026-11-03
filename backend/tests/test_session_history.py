"""Session history: runs are saved to disk and can be listed and replayed after a restart."""

from urllib.parse import urlencode

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api import state
from agentdev.api.routes import sessions, websocket
from agentdev.api.services.session_history import SessionHistoryStore, make_title
from agentdev.api.services.session_store import SessionStatus
from agentdev.api.services.websocket_manager import WebSocketManager


def _client_for(manager, monkeypatch):
    monkeypatch.setattr(manager, "_start_gc", lambda: None)
    monkeypatch.setattr(state, "websocket_manager", manager)
    app = FastAPI()
    app.include_router(sessions.router)
    app.include_router(websocket.router)
    return TestClient(app)


@pytest.fixture
def api(monkeypatch):
    manager = WebSocketManager()
    with _client_for(manager, monkeypatch) as client:
        yield client, manager


def _start_run(manager, session_id="run-1", prompt="Review the login flow\nsecond line"):
    store = manager.session_store
    store.create_session(session_id=session_id, yaml_file="demo.yaml", task_prompt=prompt)
    store.update_session_status(session_id, SessionStatus.RUNNING)
    manager.record_user_message(session_id, prompt)
    store.record_message(session_id, {"type": "log", "data": "hello"}, '{"type": "log", "data": "hello"}')
    return store


def test_make_title_uses_first_line_and_truncates():
    assert make_title("\n  First line  \nmore") == "First line"
    assert make_title("", fallback="demo.yaml") == "demo.yaml"
    assert len(make_title("x" * 200)) == 80


def test_sessions_are_listed_newest_first(api):
    client, manager = api
    _start_run(manager, "run-1")
    _start_run(manager, "run-2", prompt="Second task")

    items = client.get("/api/sessions").json()["sessions"]
    assert [item["session_id"] for item in items] == ["run-2", "run-1"]
    assert items[1]["title"] == "Review the login flow"
    assert items[1]["status"] == "running"


def test_run_is_restored_after_restart_and_marked_interrupted(api, monkeypatch):
    client, manager = api
    _start_run(manager)

    # A new manager simulates a server restart: nothing in memory, only the disk copy.
    restarted = WebSocketManager()
    with _client_for(restarted, monkeypatch) as fresh:
        with fresh.websocket_connect("/ws?" + urlencode({"session_id": "run-1"})) as ws:
            connection = ws.receive_json()
            assert connection["data"] == {"session_id": "run-1", "status": "connected", "resumed": True}
            assert ws.receive_json() == {
                "type": "user_message",
                "data": {"text": "Review the login flow\nsecond line", "attachments": []},
            }
            assert ws.receive_json() == {"type": "log", "data": "hello"}
            resumed = ws.receive_json()
            assert resumed["type"] == "session_resumed"
            assert resumed["data"]["status"] == "cancelled"
            assert resumed["data"]["title"] == "Review the login flow"

        listed = fresh.get("/api/sessions").json()["sessions"]
        assert listed[0]["status"] == "cancelled"


def test_unknown_session_id_is_a_new_connection(api):
    client, _ = api
    with client.websocket_connect("/ws?" + urlencode({"session_id": "never-seen"})) as ws:
        data = ws.receive_json()["data"]
        assert data["session_id"] == "never-seen"
        assert "resumed" not in data


def test_rename_survives_later_status_updates(api):
    client, manager = api
    store = _start_run(manager)

    response = client.patch("/api/sessions/run-1", json={"title": "Auth review"})
    assert response.status_code == 200
    store.update_session_status("run-1", SessionStatus.COMPLETED)

    assert SessionHistoryStore().get_meta("run-1")["title"] == "Auth review"
    assert client.get("/api/sessions").json()["sessions"][0]["title"] == "Auth review"


def test_delete_refuses_running_and_removes_finished(api):
    client, manager = api
    store = _start_run(manager)

    assert client.delete("/api/sessions/run-1").status_code == 409
    store.update_session_status("run-1", SessionStatus.COMPLETED)
    assert client.delete("/api/sessions/run-1").status_code == 200
    assert client.get("/api/sessions").json()["sessions"] == []
    assert not SessionHistoryStore().has("run-1")
    assert client.delete("/api/sessions/run-1").status_code == 404


@pytest.mark.parametrize("bad", ["../etc", "a b", "x.y"])
def test_invalid_session_ids_are_rejected(api, bad):
    client, _ = api
    assert client.delete(f"/api/sessions/{bad}").status_code in (400, 404)
    assert client.patch(f"/api/sessions/{bad}", json={"title": "t"}).status_code in (400, 404)


PROJECT = {"name": "OrderFlow", "attachment_id": "att-1", "project_id": "OrderFlow", "workspace_path": "projects/OrderFlow", "file_count": 876}


def test_adding_a_project_lists_a_draft_session(api):
    client, manager = api
    store = manager.session_store
    store.register_project("draft-1", "demo.yaml", PROJECT)
    store.register_project("draft-1", "demo.yaml", PROJECT)  # same upload twice is one entry

    item = client.get("/api/sessions").json()["sessions"][0]
    assert item["session_id"] == "draft-1"
    assert item["status"] == "idle"
    assert item["title"] == "OrderFlow"
    assert item["projects"] == [PROJECT]


def test_draft_survives_restart_as_draft(api, monkeypatch):
    _, manager = api
    manager.session_store.register_project("draft-1", "demo.yaml", PROJECT)

    restarted = WebSocketManager()
    with _client_for(restarted, monkeypatch) as fresh:
        with fresh.websocket_connect("/ws?" + urlencode({"session_id": "draft-1"})) as ws:
            assert ws.receive_json()["data"]["resumed"] is True
            resumed = ws.receive_json()
            assert resumed["type"] == "session_resumed"
            assert resumed["data"]["status"] == "idle"
            assert resumed["data"]["projects"] == [PROJECT]


def test_launching_a_draft_keeps_its_projects(api):
    client, manager = api
    store = manager.session_store
    store.register_project("draft-1", "demo.yaml", PROJECT)
    store.create_session(session_id="draft-1", yaml_file="demo.yaml", task_prompt="Fix the cart total")

    item = client.get("/api/sessions").json()["sessions"][0]
    assert item["title"] == "Fix the cart total"
    assert item["projects"] == [PROJECT]


def test_draft_can_switch_workflow_but_launched_session_cannot(api):
    client, manager = api
    store = manager.session_store
    store.register_project("draft-1", "demo.yaml", PROJECT)

    response = client.patch("/api/sessions/draft-1", json={"yaml_file": "review.yaml"})
    assert response.status_code == 200
    assert client.get("/api/sessions").json()["sessions"][0]["yaml_file"] == "review.yaml"
    assert SessionHistoryStore().get_meta("draft-1")["yaml_file"] == "review.yaml"

    _start_run(manager, "run-1")
    assert client.patch("/api/sessions/run-1", json={"yaml_file": "review.yaml"}).status_code == 409
    assert client.patch("/api/sessions/draft-1", json={"yaml_file": "../x.yaml"}).status_code == 400
    assert client.patch("/api/sessions/missing", json={"yaml_file": "a.yaml"}).status_code == 404
    assert client.patch("/api/sessions/draft-1", json={}).status_code == 400


def test_new_session_in_a_project_continues_from_its_latest_copy(monkeypatch):
    import asyncio
    import io

    from starlette.datastructures import UploadFile

    from agentdev.api.routes import uploads

    manager = WebSocketManager()
    monkeypatch.setattr(manager, "_start_gc", lambda: None)
    monkeypatch.setattr(state, "websocket_manager", manager)
    app = FastAPI()
    for module in (sessions, websocket, uploads):
        app.include_router(module.router)

    service = manager.attachment_service
    service.create_project("sess-a", "shop")
    asyncio.run(service.save_project_files("sess-a", "shop", [UploadFile(file=io.BytesIO(b"v1"), filename="a.py")], ["src/a.py"]))
    manager.session_store.register_project("sess-a", "build.yaml", {"name": "shop", "project_id": "shop", "attachment_id": "x"})

    with TestClient(app) as client:
        with client.websocket_connect("/ws?" + urlencode({"session_id": "sess-b"})) as ws:
            assert ws.receive_json()["data"]["session_id"] == "sess-b"
            response = client.post(
                "/api/uploads/sess-b/projects/clone",
                json={"source_session_id": "sess-a", "project_id": "shop", "yaml_file": "review.yaml"},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["kind"] == "project" and body["file_count"] == 1

            listed = {item["session_id"]: item for item in client.get("/api/sessions").json()["sessions"]}
            assert listed["sess-b"]["status"] == "idle"
            assert listed["sess-b"]["yaml_file"] == "review.yaml"
            assert listed["sess-b"]["projects"][0]["name"] == "shop"

            bad = client.post("/api/uploads/sess-b/projects/clone", json={"source_session_id": "sess-a", "project_id": "nope"})
            assert bad.status_code == 400
