import copy

import pytest

from agentdev.connections import ConnectionStore
from agentdev.connections import store as store_module
from agentdev.connections.autobind import bind_default_connections
from agentdev.entity.configs import ConfigError


@pytest.fixture()
def store(tmp_path, monkeypatch):
    s = ConnectionStore(tmp_path / "c.json")
    monkeypatch.setattr(store_module, "_store", s)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return s


def _doc(tooling=False, key="${ANTHROPIC_API_KEY}"):
    cfg = {"name": "claude-sonnet-5-5", "provider": "anthropic", "api_key": key, "base_url": "${BASE_URL}"}
    if tooling:
        cfg["tooling"] = [{"type": "function", "config": {"tools": [{"name": "x"}]}}]
    return {"vars": {}, "graph": {"nodes": [{"id": "a", "type": "agent", "config": cfg}]}}


def _cfg(doc):
    return doc["graph"]["nodes"][0]["config"]


def test_unresolved_placeholder_binds_to_saved_connection(store):
    conn = store.create(vendor="anthropic", label="Main", secret="sk-ant-1234567890")
    doc = _doc()
    bind_default_connections(doc, {})
    assert _cfg(doc)["connection"] == conn.id and "api_key" not in _cfg(doc) and "base_url" not in _cfg(doc)


def test_working_env_variable_is_left_alone(store):
    store.create(vendor="anthropic", label="Main", secret="sk-ant-1234567890")
    doc = _doc()
    bind_default_connections(doc, {"ANTHROPIC_API_KEY": "from-env"})
    assert "connection" not in _cfg(doc) and _cfg(doc)["api_key"] == "${ANTHROPIC_API_KEY}"


def test_workflow_vars_count_as_resolved(store):
    doc = _doc()
    doc["vars"] = {"ANTHROPIC_API_KEY": "x"}
    bind_default_connections(doc, {})
    assert "connection" not in _cfg(doc)


def test_explicit_connection_and_literal_keys_untouched(store):
    store.create(vendor="anthropic", label="Main", secret="sk-ant-1234567890")
    doc = _doc(key="sk-literal-key")
    before = copy.deepcopy(doc)
    bind_default_connections(doc, {})
    assert doc == before


def test_no_connection_gives_friendly_error(store):
    with pytest.raises(ConfigError, match="Connections page"):
        bind_default_connections(_doc(), {})


def test_claude_cli_connection_serves_tool_nodes(store):
    cli = store.create(vendor="anthropic", label="CLI", secret="", auth_type="cli")
    doc = _doc(tooling=True)
    bind_default_connections(doc, {})
    assert _cfg(doc)["connection"] == cli.id


def test_codex_cli_connection_cannot_serve_tool_nodes(store):
    store.create(vendor="openai", label="CLI", secret="", auth_type="cli")
    doc = {"vars": {}, "graph": {"nodes": [{"id": "a", "type": "agent", "config": {
        "name": "gpt-4o", "provider": "openai", "api_key": "${API_KEY}",
        "tooling": [{"type": "function", "config": {"tools": [{"name": "x"}]}}]}}]}}
    with pytest.raises(ConfigError, match="tools"):
        bind_default_connections(doc, {})
