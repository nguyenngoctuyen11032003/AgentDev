import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import workflow_assistant as route
from agentdev.api.services import assistant_sessions as store
from agentdev.api.services import workflow_assistant as service


@pytest.fixture(autouse=True)
def sessions_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "SESSIONS_DIR", tmp_path / "assistant_sessions")
    return tmp_path


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(route.router)
    return TestClient(app)


MSGS = [{"id": "m1", "role": "user", "content": "Giải thích bugfix_team"},
        {"id": "m2", "role": "assistant", "content": "Quy trình có 3 bước", "model": "sonnet"}]


def test_save_list_get_delete(client):
    res = client.put("/api/workflow-assistant/sessions/s1234567890", json={
        "workflow": "bugfix_team.yaml", "title": "Giải thích", "messages": MSGS, "pending_message_id": None})
    assert res.status_code == 200
    assert res.json()["workflow"] == "bugfix_team" and res.json()["message_count"] == 2

    listed = client.get("/api/workflow-assistant/sessions", params={"workflow": "bugfix_team"}).json()["sessions"]
    assert [s["id"] for s in listed] == ["s1234567890"]
    # Sessions of "new workflow" are listed separately.
    assert client.get("/api/workflow-assistant/sessions").json()["sessions"] == []

    full = client.get("/api/workflow-assistant/sessions/s1234567890").json()
    assert full["messages"] == MSGS and full["title"] == "Giải thích"

    assert client.delete("/api/workflow-assistant/sessions/s1234567890").json() == {"deleted": True}
    assert client.get("/api/workflow-assistant/sessions/s1234567890").status_code == 404


def test_resave_keeps_created_at_and_moves_workflow():
    first = store.save_session("s1234567890", workflow=None, title="tạo mới", messages=MSGS)
    second = store.save_session("s1234567890", workflow="new_flow", title="", messages=MSGS)
    assert second["created_at"] == first["created_at"]
    assert second["title"] == "tạo mới"  # an empty title keeps the old one
    assert store.list_sessions(None) == []
    assert [s["id"] for s in store.list_sessions("new_flow")] == ["s1234567890"]


def test_list_newest_first(monkeypatch):
    clock = iter([100.0, 200.0])
    monkeypatch.setattr(store.time, "time", lambda: next(clock))
    store.save_session("aaaaaaaa1", workflow="w", title="old", messages=MSGS)
    store.save_session("bbbbbbbb2", workflow="w", title="new", messages=MSGS)
    assert [s["title"] for s in store.list_sessions("w")] == ["new", "old"]


@pytest.mark.parametrize("bad", ["../etc", "short", "a/b/c/d/e/f", "x" * 80])
def test_bad_ids_rejected(client, bad):
    res = client.get(f"/api/workflow-assistant/sessions/{bad}")
    assert res.status_code in (400, 404)
    assert not list((store.SESSIONS_DIR.parent).glob("**/etc*"))


def test_bad_workflow_rejected(client):
    res = client.put("/api/workflow-assistant/sessions/s1234567890",
                     json={"workflow": "../x", "messages": MSGS})
    assert res.status_code == 400


def test_chat_passes_model(client, monkeypatch):
    seen = {}
    monkeypatch.setattr(route.service, "run_turn", lambda **kw: seen.update(kw) or {"reply": "ok"})
    body = {"vendor": "anthropic", "model": "claude-haiku-4-5", "request_id": "r1",
            "messages": [{"role": "user", "content": "hi"}]}
    assert client.post("/api/workflow-assistant/chat", json=body).status_code == 200
    assert seen["model"] == "claude-haiku-4-5"


def test_chat_rejects_odd_model_name(client):
    body = {"vendor": "anthropic", "model": "--dangerous flag", "request_id": "r1",
            "messages": [{"role": "user", "content": "hi"}]}
    assert client.post("/api/workflow-assistant/chat", json=body).status_code == 422


def test_history_digest_covers_dropped_messages():
    messages = []
    for i in range(30):
        messages.append({"role": "user", "content": f"câu hỏi {i}"})
        messages.append({"role": "assistant", "content": f"trả lời {i}"})
    messages.append({"role": "user", "content": "câu cuối"})
    kept = service._trim_history(messages)
    digest = service.history_digest(messages, kept)
    assert "câu hỏi 1" in digest and "trả lời 1" in digest
    assert "câu hỏi 0" not in digest  # the first request is still sent in full
    assert service.history_digest(messages[:5], service._trim_history(messages[:5])) == ""


def test_run_turn_sends_digest_and_uses_model(monkeypatch):
    sent = {}

    def fake_call(system, history):
        sent["last"] = history[-1]["content"]
        return '{"reply": "ok", "quick_replies": [], "proposal": null, "intent": "explain"}'

    messages = []
    for i in range(25):
        messages += [{"role": "user", "content": f"hỏi {i}"}, {"role": "assistant", "content": f"đáp {i}"}]
    messages.append({"role": "user", "content": "tiếp tục"})
    result = service.run_turn(vendor="anthropic", workflow=None, messages=messages, pending_yaml=None,
                              request_id="digest-1", call=fake_call)
    assert result["reply"] == "ok"
    assert "Earlier in this chat" in sent["last"] and "hỏi 3" in sent["last"]
