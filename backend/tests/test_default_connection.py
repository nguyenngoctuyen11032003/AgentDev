import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.connections import ConnectionStore
from agentdev.connections import autobind
from agentdev.connections import store as store_module
from agentdev.connections.autobind import bind_default_connections
from agentdev.entity.configs.node.agent import AgentConfig


@pytest.fixture()
def store(tmp_path, monkeypatch):
    s = ConnectionStore(tmp_path / "c.json")
    monkeypatch.setattr(store_module, "_store", s)
    # Never ask a real CLI for its models in tests.
    monkeypatch.setattr(autobind, "_default_model", lambda conn: None)
    return s


def _doc(provider, name):
    cfg = {"name": name, "provider": provider, "role": "x"}
    return {"vars": {}, "graph": {"nodes": [{"id": "a", "type": "agent", "config": cfg}]}}


def _cfg(doc):
    return doc["graph"]["nodes"][0]["config"]


def test_claude_is_the_default_until_another_is_chosen(store):
    codex = store.create(vendor="openai", label="Codex", secret="", auth_type="cli")
    assert store.default_connection() is None
    claude = store.create(vendor="anthropic", label="Claude", secret="", auth_type="cli")
    assert store.default_connection().id == claude.id
    store.set_default(codex.id)
    assert store.default_connection().id == codex.id
    # A later write keeps the choice; deleting the chosen one falls back to Claude.
    store.create(vendor="gemini", label="G", secret="", auth_type="oauth")
    assert store.default_connection().id == codex.id
    store.delete(codex.id)
    assert store.default_connection().id == claude.id


def test_every_node_runs_on_the_default_connection(store):
    claude = store.create(vendor="anthropic", label="Claude", secret="", auth_type="cli")
    store.create(vendor="openai", label="Codex", secret="", auth_type="cli")
    doc = _doc("openai", "gpt-4o")
    bind_default_connections(doc, {})
    assert _cfg(doc)["connection"] == claude.id
    assert _cfg(doc)["name"].startswith("claude-")


def test_explicit_node_connection_is_kept(store):
    store.create(vendor="anthropic", label="Claude", secret="", auth_type="cli")
    codex = store.create(vendor="openai", label="Codex", secret="", auth_type="cli")
    doc = _doc("openai", "gpt-4o")
    _cfg(doc)["connection"] = codex.id
    bind_default_connections(doc, {})
    assert _cfg(doc)["connection"] == codex.id and _cfg(doc)["name"] == "gpt-4o"


def test_new_nodes_preselect_the_default_connection(store):
    claude = store.create(vendor="anthropic", label="Claude", secret="", auth_type="cli")
    store.create(vendor="openai", label="Codex", secret="", auth_type="cli")
    assert AgentConfig.field_specs()["connection"].default == claude.id


def test_api_reports_and_changes_the_default(store):
    from agentdev.api.routes import connections as connections_route

    app = FastAPI()
    app.include_router(connections_route.router)
    client = TestClient(app)
    claude = store.create(vendor="anthropic", label="Claude", secret="", auth_type="cli")
    codex = store.create(vendor="openai", label="Codex", secret="", auth_type="cli")
    assert client.get("/api/connections").json()["defaultConnection"] == claude.id
    res = client.put("/api/connections/default", json={"connection_id": codex.id})
    assert res.status_code == 200 and res.json()["defaultConnection"] == codex.id
    assert client.get("/api/connections").json()["defaultConnection"] == codex.id
    assert client.put("/api/connections/default", json={"connection_id": "nope"}).status_code == 404
