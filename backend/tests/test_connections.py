import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import connections as connections_route
from agentdev.connections import ConnectionResolutionError, ConnectionStore, resolve_connection
from agentdev.connections import store as store_module
from agentdev.connections.store import mask_secret
from agentdev.entity.configs.node.agent import AgentConfig


@pytest.fixture()
def isolated_store(tmp_path, monkeypatch):
    store = ConnectionStore(tmp_path / "connections.json")
    monkeypatch.setattr(store_module, "_store", store)
    return store


def test_store_roundtrip_and_unique_ids(isolated_store):
    a = isolated_store.create(vendor="anthropic", label="Work", secret="sk-ant-1234567890")
    b = isolated_store.create(vendor="anthropic", label="Work", secret="sk-ant-other-key-00")
    assert a.id == "work" and b.id != a.id
    assert {c.id for c in isolated_store.list()} == {a.id, b.id}
    assert isolated_store.delete(a.id) is True
    assert isolated_store.delete(a.id) is False


def test_public_view_never_leaks_secret(isolated_store):
    conn = isolated_store.create(vendor="openai", label="x", secret="sk-supersecretvalue1234")
    public = conn.to_public()
    assert "supersecret" not in str(public)
    assert public["secretHint"] == mask_secret("sk-supersecretvalue1234")


def test_resolver_expands_env_reference(isolated_store, monkeypatch):
    monkeypatch.setenv("MY_TEST_API_KEY", "real-key")
    conn = isolated_store.create(vendor="openai", label="env", secret="${MY_TEST_API_KEY}")
    creds = resolve_connection(conn.id)
    assert creds.api_key == "real-key" and creds.vendor == "openai"


def test_resolver_errors(isolated_store, monkeypatch):
    with pytest.raises(ConnectionResolutionError):
        resolve_connection("missing")
    monkeypatch.delenv("UNSET_TEST_API_KEY", raising=False)
    conn = isolated_store.create(vendor="openai", label="empty", secret="${UNSET_TEST_API_KEY}")
    with pytest.raises(ConnectionResolutionError):
        resolve_connection(conn.id)


def test_agent_config_connection_makes_provider_optional():
    cfg = AgentConfig.from_dict({"connection": "work", "name": "claude-sonnet-5-5"}, path="t")
    assert cfg.connection == "work" and cfg.provider == ""
    legacy = AgentConfig.from_dict({"provider": "openai", "name": "gpt-4o"}, path="t")
    assert legacy.connection is None and legacy.provider == "openai"
    with pytest.raises(Exception):
        AgentConfig.from_dict({"name": "gpt-4o"}, path="t")


def test_connection_field_becomes_enum_when_connections_exist(isolated_store):
    assert AgentConfig.field_specs()["connection"].enum is None
    isolated_store.create(vendor="gemini", label="G", secret="k-123456789")
    assert AgentConfig.field_specs()["connection"].enum == ["g"]


def test_api_create_list_delete(isolated_store):
    app = FastAPI()
    app.include_router(connections_route.router)
    client = TestClient(app)

    assert client.post("/api/connections", json={"vendor": "nope", "label": "a", "api_key": "k"}).status_code == 422
    assert (
        client.post(
            "/api/connections",
            json={"vendor": "gemini", "label": "a", "api_key": "k", "auth_type": "oauth"},
        ).status_code
        == 422
    )
    created = client.post(
        "/api/connections", json={"vendor": "anthropic", "label": "Main", "api_key": "sk-ant-abcdefgh1234"}
    )
    assert created.status_code == 201
    body = created.json()
    assert "api_key" not in body and "secret" not in body
    listed = client.get("/api/connections").json()["connections"]
    assert [c["id"] for c in listed] == [body["id"]]
    assert len(client.get("/api/connections/vendors").json()["vendors"]) == 3
    assert client.delete(f"/api/connections/{body['id']}").status_code == 200
    assert client.delete(f"/api/connections/{body['id']}").status_code == 404


def test_secret_is_not_stored_in_plaintext_on_windows(tmp_path):
    import sys

    path = tmp_path / "connections.json"
    store = ConnectionStore(path)
    conn = store.create(vendor="openai", label="enc", secret="sk-plaintext-should-not-appear")
    assert store.get(conn.id).secret == "sk-plaintext-should-not-appear"
    if sys.platform == "win32":
        assert "sk-plaintext-should-not-appear" not in path.read_text(encoding="utf-8")


def test_legacy_plaintext_file_still_loads(tmp_path):
    import json

    path = tmp_path / "connections.json"
    path.write_text(
        json.dumps({"connections": [{"id": "old", "vendor": "openai", "label": "old", "secret": "sk-legacy-1234"}]}),
        encoding="utf-8",
    )
    assert ConnectionStore(path).get("old").secret == "sk-legacy-1234"


def test_cli_connection_needs_no_secret_and_resolves_to_cli_provider(isolated_store):
    claude = isolated_store.create(vendor="anthropic", label="Claude CLI", secret="", auth_type="cli")
    creds = resolve_connection(claude.id)
    assert creds.provider == "claude_cli" and creds.api_key == ""
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


def test_oauth_connection_resolves_to_bearer_and_persists_refresh(isolated_store, monkeypatch):
    import json
    from agentdev.connections import google_oauth, oauth_store

    conn = oauth_store.save_oauth_connection("G", "gemini", {"access_token": "old", "email": "a@b.c"})
    assert isolated_store.get(conn.id).to_public()["secretHint"] == "a@b.c"
    monkeypatch.setattr(
        google_oauth, "get_valid_access_token", lambda t: ("new-token", {"access_token": "new-token", "email": "a@b.c"})
    )
    creds = resolve_connection(conn.id)
    assert creds.api_key.endswith("new-token") and creds.api_key.startswith("oauth-bearer:")
    assert json.loads(isolated_store.get(conn.id).secret)["access_token"] == "new-token"


def test_api_cannot_create_oauth_directly(isolated_store):
    app = FastAPI()
    app.include_router(connections_route.router)
    r = TestClient(app).post("/api/connections", json={"vendor": "gemini", "label": "g", "auth_type": "oauth"})
    assert r.status_code == 422


# ---- hardening (independent review findings) ----------------------------------------------

def test_env_reference_is_limited_to_credential_variables(isolated_store, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "top-secret")
    conn = isolated_store.create(vendor="openai", label="leak", secret="${GOOGLE_OAUTH_CLIENT_SECRET}")
    with pytest.raises(ConnectionResolutionError, match="cannot be used"):
        resolve_connection(conn.id)


def test_env_key_cannot_be_sent_to_a_foreign_host(isolated_store, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real")
    conn = isolated_store.create(
        vendor="openai", label="evil", secret="${OPENAI_API_KEY}", base_url="https://evil.example/v1"
    )
    with pytest.raises(ConnectionResolutionError, match="default URL or localhost"):
        resolve_connection(conn.id)
    ok = isolated_store.create(
        vendor="openai", label="local", secret="${OPENAI_API_KEY}", base_url="http://localhost:11434/v1"
    )
    assert resolve_connection(ok.id).api_key == "sk-real"


def test_api_rejects_unsafe_input(isolated_store):
    app = FastAPI()
    app.include_router(connections_route.router)
    client = TestClient(app)
    base = {"vendor": "openai", "label": "x"}
    assert client.post("/api/connections", json={**base, "api_key": "${HOME}"}).status_code == 422
    assert client.post("/api/connections", json={**base, "api_key": "k-123456789", "base_url": "http://evil.example"}).status_code == 422
    assert (
        client.post(
            "/api/connections", json={**base, "api_key": "${OPENAI_API_KEY}", "base_url": "https://evil.example"}
        ).status_code
        == 422
    )
    assert client.post("/api/connections", json={**base, "api_key": "k-123456789", "base_url": "https://u:p@x.com"}).status_code == 422


def test_cross_origin_writes_are_blocked(isolated_store):
    app = FastAPI()
    app.include_router(connections_route.router)
    client = TestClient(app)
    body = {"vendor": "openai", "label": "x", "api_key": "k-123456789"}
    assert client.post("/api/connections", json=body, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/connections", json=body, headers={"Origin": "http://localhost:5173"}).status_code == 201
    assert client.get("/api/connections", headers={"Origin": "https://evil.example"}).status_code == 200


def test_undecryptable_secret_survives_other_writes(tmp_path):
    import json

    path = tmp_path / "connections.json"
    blob = "dpapi:AAAA-not-a-valid-blob"
    path.write_text(
        json.dumps({"connections": [{"id": "keep", "vendor": "openai", "label": "keep", "secret": blob}]}),
        encoding="utf-8",
    )
    store = ConnectionStore(path)
    store.create(vendor="openai", label="other", secret="sk-other-key-12345")
    stored = json.loads(path.read_text(encoding="utf-8"))["connections"]
    assert next(c for c in stored if c["id"] == "keep")["secret"] == blob


def test_corrupt_file_is_never_overwritten(tmp_path):
    from agentdev.connections.store import ConnectionInputError

    path = tmp_path / "connections.json"
    path.write_text("{ not json", encoding="utf-8")
    store = ConnectionStore(path)
    assert store.list() == []
    with pytest.raises(ConnectionInputError):
        store.create(vendor="openai", label="x", secret="sk-1234567890")
    assert path.read_text(encoding="utf-8") == "{ not json"
    assert (tmp_path / "connections.json.bak").exists()


def test_short_secrets_are_fully_masked():
    assert mask_secret("sk-123456789") == "****"
    assert mask_secret("sk-ant-api03-abcdefghijklmnop").startswith("sk-a")


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
