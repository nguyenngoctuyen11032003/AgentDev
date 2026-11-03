import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import workflow_assistant as route
from agentdev.api.services.workflow_assistant import AssistantError


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(route.router)
    return TestClient(app)


BODY = {"vendor": "anthropic", "messages": [{"role": "user", "content": "hi"}], "request_id": "r1"}


def test_providers_route(client, monkeypatch):
    monkeypatch.setattr(route.service, "list_providers", lambda: [{"vendor": "anthropic", "available": True}])
    res = client.get("/api/workflow-assistant/providers")
    assert res.status_code == 200
    assert res.json() == {"providers": [{"vendor": "anthropic", "available": True}]}


def test_chat_route_ok(client, monkeypatch):
    seen = {}

    def fake(**kw):
        seen.update(kw)
        return {"reply": "ok", "quick_replies": [], "proposal": None, "model_used": "m", "validation_errors": []}

    monkeypatch.setattr(route.service, "run_turn", fake)
    res = client.post("/api/workflow-assistant/chat", json=BODY)
    assert res.status_code == 200 and res.json()["reply"] == "ok"
    assert seen["vendor"] == "anthropic" and seen["request_id"] == "r1"
    assert seen["messages"] == [{"role": "user", "content": "hi"}]


def test_chat_route_quota_returns_error_payload(client, monkeypatch):
    def fake(**kw):
        raise AssistantError("quota_exhausted", "out of quota")

    monkeypatch.setattr(route.service, "run_turn", fake)
    res = client.post("/api/workflow-assistant/chat", json=BODY)
    assert res.status_code == 200
    assert res.json() == {"error": "quota_exhausted", "message": "out of quota"}


def test_chat_route_bad_request_is_400(client, monkeypatch):
    def fake(**kw):
        raise AssistantError("bad_request", "dup")

    monkeypatch.setattr(route.service, "run_turn", fake)
    res = client.post("/api/workflow-assistant/chat", json=BODY)
    assert res.status_code == 400 and res.json()["error"] == "bad_request"


def test_chat_route_validates_roles(client):
    bad = {**BODY, "messages": [{"role": "system", "content": "x"}]}
    assert client.post("/api/workflow-assistant/chat", json=bad).status_code == 422


def test_cancel_route(client, monkeypatch):
    monkeypatch.setattr(route.service, "cancel", lambda rid: rid == "r1")
    assert client.post("/api/workflow-assistant/cancel", json={"request_id": "r1"}).json() == {"cancelled": True}
    assert client.post("/api/workflow-assistant/cancel", json={"request_id": "zz"}).json() == {"cancelled": False}


def test_rejects_non_local_origin(client):
    evil = {"Origin": "http://evil.example"}
    assert client.get("/api/workflow-assistant/providers", headers=evil).status_code == 403
    assert client.post("/api/workflow-assistant/chat", json=BODY, headers=evil).status_code == 403
    assert client.post("/api/workflow-assistant/cancel", json={"request_id": "r1"}, headers=evil).status_code == 403


def test_chat_route_unexpected_error_is_sanitised_json(client, monkeypatch):
    def fake(**kw):
        raise KeyError("C:\\Users\\someone\\secret path")

    monkeypatch.setattr(route.service, "run_turn", fake)
    res = TestClient(client.app, raise_server_exceptions=False).post("/api/workflow-assistant/chat", json=BODY)
    assert res.status_code == 500
    data = res.json()
    assert data["error"] == "internal"
    assert "someone" not in data["message"] and data["message"]


def test_chat_route_busy_returns_error_payload(client, monkeypatch):
    def fake(**kw):
        raise AssistantError("busy", "too many concurrent requests")

    monkeypatch.setattr(route.service, "run_turn", fake)
    res = client.post("/api/workflow-assistant/chat", json=BODY)
    assert res.status_code == 200 and res.json()["error"] == "busy"


def test_chat_route_rejects_blank_last_user_message(client, monkeypatch):
    monkeypatch.setattr(route.service, "run_turn", lambda **kw: {"reply": "ok"})
    for content in ("", "   \n "):
        bad = {**BODY, "messages": [{"role": "user", "content": content}]}
        assert client.post("/api/workflow-assistant/chat", json=bad).status_code == 422
    # An empty assistant message earlier in the history (a give-up turn) is fine.
    ok = {**BODY, "messages": [{"role": "user", "content": "a"}, {"role": "assistant", "content": ""},
                               {"role": "user", "content": "b"}]}
    assert client.post("/api/workflow-assistant/chat", json=ok).status_code == 200


def test_chat_route_rejects_oversized_request(client, monkeypatch):
    monkeypatch.setattr(route.service, "run_turn", lambda **kw: {"reply": "ok"})
    big = {**BODY, "messages": [{"role": "user", "content": "x" * 50_000}] * 8, "pending_yaml": "y" * 10}
    assert client.post("/api/workflow-assistant/chat", json=big).status_code == 422
