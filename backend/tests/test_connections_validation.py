import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import connections_check
from agentdev.connections import ConnectionStore, validation
from agentdev.connections import store as store_module
from agentdev.connections.validation import check_workflow_connections


@pytest.fixture()
def store(tmp_path, monkeypatch):
    s = ConnectionStore(tmp_path / "c.json")
    monkeypatch.setattr(store_module, "_store", s)
    return s


def agent(nid, conn=None):
    cfg = {"connection": conn} if conn else {"provider": "anthropic"}
    return {"id": nid, "type": "agent", "config": cfg}


def doc(*nodes):
    return {"graph": {"nodes": list(nodes), "edges": []}}


def test_missing(store):
    r = check_workflow_connections(doc(agent("a", "nope")))
    assert [(p["nodeId"], p["problem"]) for p in r] == [("a", "missing")]


def test_api_key_connection_is_flagged_and_accounts_pass(store, tmp_path):
    import json

    (tmp_path / "c.json").write_text(
        json.dumps({"connections": [{"id": "old", "vendor": "openai", "label": "old", "auth_type": "api_key", "secret": "sk-realsecret-123456"}]}),
        encoding="utf-8",
    )
    good = store.create(vendor="openai", label="good", auth_type="cli")
    r = check_workflow_connections(doc(agent("a", "old"), agent("b", good.id)))
    assert len(r) == 1 and r[0]["problem"] == "unsupported_auth" and r[0]["nodeId"] == "a"
    assert "realsecret" not in str(r)


def test_legacy_ignored(store):
    assert check_workflow_connections(doc(agent("a"))) == []


def test_nested_inline(store):
    inner = doc(agent("x", "nope"))["graph"]
    d = doc({"id": "sg", "type": "subgraph", "config": {"type": "config", "config": inner}})
    r = check_workflow_connections(d)
    assert r[0]["nodeId"] == "sg/x"


def test_subgraph_file_cycle(store, tmp_path, monkeypatch):
    (tmp_path / "a.yaml").write_text(
        "graph:\n  nodes:\n    - id: s\n      type: subgraph\n      config:\n        type: file\n"
        "        config: {path: b.yaml}\n    - id: n\n      type: agent\n      config: {connection: nope}\n"
    )
    (tmp_path / "b.yaml").write_text(
        "graph:\n  nodes:\n    - id: s\n      type: subgraph\n      config:\n        type: file\n"
        "        config: {path: a.yaml}\n"
    )
    monkeypatch.setattr(validation, "WORKFLOWS_DIR", tmp_path)
    d = doc({"id": "top", "type": "subgraph", "config": {"type": "file", "config": {"path": "a.yaml"}}})
    r = check_workflow_connections(d)
    assert len(r) == 1 and r[0]["nodeId"] == "top/n"
    d2 = doc({"id": "t", "type": "subgraph", "config": {"type": "file", "config": {"path": "../x.yaml"}}})
    assert check_workflow_connections(d2) == []


def test_route(store):
    app = FastAPI()
    app.include_router(connections_check.router)
    c = TestClient(app)
    y = "graph:\n  nodes:\n    - id: a\n      type: agent\n      config: {connection: nope}\n"
    r = c.post("/api/connections/check", json={"yaml_content": y})
    assert r.status_code == 200 and r.json()["ok"] is False
    assert r.json()["problems"][0]["problem"] == "missing"
    assert c.post("/api/connections/check", json={"yaml_content": "a: [\n"}).status_code == 422
