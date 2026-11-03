import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import connections as connections_route
from agentdev.connections import ConnectionResolutionError, ConnectionStore, resolve_connection
from agentdev.connections import store as store_module
from agentdev.entity.configs.node.agent import AgentConfig


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    store = ConnectionStore(tmp_path / "connections.json")
    monkeypatch.setattr(store_module, "_store", store)
    return store


def test_store_roundtrip_and_unique_ids(isolated_store):
    a = isolated_store.create(vendor="anthropic", label="Work", auth_type="cli")
    b = isolated_store.create(vendor="anthropic", label="Work", auth_type="cli")
    assert a.id == "work" and b.id != a.id
    assert {c.id for c in isolated_store.list()} == {a.id, b.id}
    assert isolated_store.delete(a.id) is True
    assert isolated_store.delete(a.id) is False


def test_agent_config_connection_makes_provider_optional():
    cfg = AgentConfig.from_dict({"connection": "work", "name": "claude-sonnet-5-5"}, path="t")
    assert cfg.connection == "work" and cfg.provider == ""
    legacy = AgentConfig.from_dict(
        {"provider": "openai", "name": "gpt-4o", "api_key": "${API_KEY}", "base_url": "${BASE_URL}"}, path="t"
    )
    assert legacy.connection is None and legacy.provider == "openai"
    assert legacy.api_key is None and legacy.base_url == ""  # credentials are never read from YAML
    specs = AgentConfig.field_specs()
    assert "api_key" not in specs and "base_url" not in specs and specs["provider"].hidden
    with pytest.raises(Exception):
        AgentConfig.from_dict({"name": "gpt-4o"}, path="t")


def test_connection_field_becomes_enum_when_connections_exist(isolated_store):
    assert AgentConfig.field_specs()["connection"].enum is None
    isolated_store.create(vendor="gemini", label="G", auth_type="oauth", secret='{"email": "g@x.io"}')
    assert AgentConfig.field_specs()["connection"].enum == ["g"]


def test_api_create_list_delete(isolated_store, monkeypatch):
    monkeypatch.setattr(connections_route, "logout_cli", lambda vendor: True)
    app = FastAPI()
    app.include_router(connections_route.router)
    client = TestClient(app)

    monkeypatch.setattr(connections_route, "detect_cli", lambda vendor: {"installed": True, "logged_in": True})
    assert client.post("/api/connections", json={"vendor": "nope", "label": "a"}).status_code == 422
    assert client.post("/api/connections", json={"vendor": "gemini", "label": "a", "auth_type": "oauth"}).status_code == 422
    created = client.post("/api/connections", json={"vendor": "anthropic", "label": "Main", "auth_type": "cli"})
    assert created.status_code == 201
    body = created.json()
    assert "api_key" not in body and "secret" not in body
    listed = client.get("/api/connections").json()["connections"]
    assert [c["id"] for c in listed] == [body["id"]]
    assert len(client.get("/api/connections/vendors").json()["vendors"]) == 3
    assert client.delete(f"/api/connections/{body['id']}").status_code == 200
    assert client.delete(f"/api/connections/{body['id']}").status_code == 404


def test_cli_connection_needs_no_secret_and_resolves_to_cli_provider(isolated_store):
    claude = isolated_store.create(vendor="anthropic", label="Claude CLI", secret="", auth_type="cli")
    creds = resolve_connection(claude.id)
    assert creds.provider == "claude_cli" and creds.token == ""
    gemini = isolated_store.create(vendor="gemini", label="G CLI", secret="", auth_type="cli")
    with pytest.raises(ConnectionResolutionError):
        resolve_connection(gemini.id)


def test_api_rejects_cli_for_gemini_and_accepts_for_claude(isolated_store, monkeypatch):
    monkeypatch.setattr(connections_route, "detect_cli", lambda vendor: {"installed": True, "logged_in": True})
    app = FastAPI()
    app.include_router(connections_route.router)
    client = TestClient(app)
    bad = client.post("/api/connections", json={"vendor": "gemini", "label": "g", "auth_type": "cli"})
    assert bad.status_code == 422
    ok = client.post("/api/connections", json={"vendor": "anthropic", "label": "c", "auth_type": "cli"})
    assert ok.status_code == 201 and ok.json()["secretHint"] == ""


def test_signing_out_last_cli_connection_signs_the_cli_out(isolated_store, monkeypatch):
    calls = []
    monkeypatch.setattr(connections_route, "logout_cli", lambda vendor: calls.append(vendor) or True)
    app = FastAPI()
    app.include_router(connections_route.router)
    client = TestClient(app)
    first = isolated_store.create(vendor="anthropic", label="a", secret="", auth_type="cli")
    second = isolated_store.create(vendor="anthropic", label="b", secret="", auth_type="cli")

    # Another CLI connection still shares the login, so it is kept.
    assert client.delete(f"/api/connections/{first.id}").json()["cliLoggedOut"] is False
    assert calls == []
    assert client.delete(f"/api/connections/{second.id}").json()["cliLoggedOut"] is True
    assert calls == ["anthropic"]


def test_oauth_connection_resolves_to_bearer_and_persists_refresh(isolated_store, monkeypatch):
    import json
    from agentdev.connections import google_oauth, oauth_store

    conn = oauth_store.save_oauth_connection("G", "gemini", {"access_token": "old", "email": "a@b.c"})
    assert isolated_store.get(conn.id).to_public()["secretHint"] == "a@b.c"
    monkeypatch.setattr(
        google_oauth, "get_valid_access_token", lambda t: ("new-token", {"access_token": "new-token", "email": "a@b.c"})
    )
    creds = resolve_connection(conn.id)
    assert creds.token.endswith("new-token") and creds.token.startswith("oauth-bearer:")
    assert json.loads(isolated_store.get(conn.id).secret)["access_token"] == "new-token"


def test_api_cannot_create_oauth_directly(isolated_store):
    app = FastAPI()
    app.include_router(connections_route.router)
    r = TestClient(app).post("/api/connections", json={"vendor": "gemini", "label": "g", "auth_type": "oauth"})
    assert r.status_code == 422


# ---- hardening ---------------------------------------------------------------------------

def test_api_keys_can_no_longer_be_created_or_used(isolated_store, tmp_path):
    import json

    from agentdev.connections.store import ConnectionInputError

    app = FastAPI()
    app.include_router(connections_route.router)
    client = TestClient(app)
    refused = client.post("/api/connections", json={"vendor": "openai", "label": "x", "auth_type": "api_key"})
    assert refused.status_code == 422
    with pytest.raises(ConnectionInputError):
        isolated_store.create(vendor="openai", label="x", auth_type="api_key", secret="sk-123")
    # A key connection saved by an older version still loads, but cannot run anything.
    (tmp_path / "connections.json").write_text(
        json.dumps({"connections": [{"id": "old", "vendor": "openai", "label": "old", "secret": "sk-legacy-1234"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ConnectionResolutionError, match="no longer supported"):
        resolve_connection("old")
    vendors = client.get("/api/connections/vendors").json()["vendors"]
    assert all(v["authMethods"] in (["cli"], ["oauth"]) for v in vendors)
    assert all("envKeyHint" not in v and "defaultBaseUrl" not in v for v in vendors)


def test_cross_origin_writes_are_blocked(isolated_store, monkeypatch):
    monkeypatch.setattr(connections_route, "detect_cli", lambda vendor: {"installed": True, "logged_in": True})
    app = FastAPI()
    app.include_router(connections_route.router)
    client = TestClient(app)
    body = {"vendor": "openai", "label": "x", "auth_type": "cli"}
    assert client.post("/api/connections", json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/connections", json=body, headers={"Origin": "http://localhost:5173"}).status_code == 201
    assert client.get("/api/connections", headers={"Origin": "https://evil.example"}).status_code == 200


def test_undecryptable_secret_survives_other_writes(tmp_path):
    import json

    path = tmp_path / "connections.json"
    blob = "dpapi:AAAA-not-a-valid-blob"
    path.write_text(
        json.dumps({"connections": [{"id": "keep", "vendor": "gemini", "label": "keep", "auth_type": "oauth", "secret": blob}]}),
        encoding="utf-8",
    )
    store = ConnectionStore(path)
    store.create(vendor="openai", label="other", auth_type="cli")
    stored = json.loads(path.read_text(encoding="utf-8"))["connections"]
    assert next(c for c in stored if c["id"] == "keep")["secret"] == blob


def test_corrupt_file_is_never_overwritten(tmp_path):
    from agentdev.connections.store import ConnectionInputError

    path = tmp_path / "connections.json"
    path.write_text("{ not json", encoding="utf-8")
    store = ConnectionStore(path)
    assert store.list() == []
    with pytest.raises(ConnectionInputError):
        store.create(vendor="openai", label="x", auth_type="cli")
    assert path.read_text(encoding="utf-8") == "{ not json"
    assert (tmp_path / "connections.json.bak").exists()


def test_pre_run_check_accepts_cli_and_oauth_connections(isolated_store):
    from agentdev.connections.validation import check_workflow_connections

    cli = isolated_store.create(vendor="anthropic", label="cli", secret="", auth_type="cli")
    doc = {"graph": {"nodes": [{"id": "a", "type": "agent", "config": {"connection": cli.id, "name": "m"}}]}}
    assert check_workflow_connections(doc) == []


def test_cli_connection_requires_a_signed_in_account(isolated_store, monkeypatch):
    app = FastAPI()
    app.include_router(connections_route.router)
    client = TestClient(app)
    body = {"vendor": "anthropic", "label": "c", "auth_type": "cli"}

    monkeypatch.setattr(connections_route, "detect_cli", lambda vendor: {"installed": False, "logged_in": None})
    assert client.post("/api/connections", json=body).status_code == 422
    monkeypatch.setattr(connections_route, "detect_cli", lambda vendor: {"installed": True, "logged_in": False})
    refused = client.post("/api/connections", json=body)
    assert refused.status_code == 422 and "sign in" in refused.json()["detail"].lower()
    assert isolated_store.list() == []  # nothing was created on failure
    monkeypatch.setattr(connections_route, "detect_cli", lambda vendor: {"installed": True, "logged_in": True})
    assert client.post("/api/connections", json=body).status_code == 201


def test_oauth_tokens_are_not_stored_in_plaintext_on_windows(tmp_path):
    import sys

    path = tmp_path / "connections.json"
    store = ConnectionStore(path)
    conn = store.create(vendor="gemini", label="enc", auth_type="oauth", secret='{"access_token": "tok-should-not-appear"}')
    assert "tok-should-not-appear" in store.get(conn.id).secret
    if sys.platform == "win32":
        assert "tok-should-not-appear" not in path.read_text(encoding="utf-8")
