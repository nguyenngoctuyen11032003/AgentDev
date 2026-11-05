import json

import pytest

from agentdev.connections import ConnectionStore
from agentdev.connections import store as store_module
from agentdev.connections.autobind import bind_default_connections
from agentdev.entity.configs import ConfigError


@pytest.fixture()
def store(tmp_path, monkeypatch):
    s = ConnectionStore(tmp_path / "c.json")
    monkeypatch.setattr(store_module, "_store", s)
    # Model lookups read the CLI's own caches; keep them out of the tests
    monkeypatch.setattr("agentdev.connections.autobind._default_model", lambda conn: None)
    return s


def _doc(provider="anthropic", name="claude-sonnet-5-5", tooling=False, **extra):
    cfg = {"name": name, "provider": provider, "api_key": "${ANTHROPIC_API_KEY}", "base_url": "${BASE_URL}", **extra}
    if tooling:
        cfg["tooling"] = [{"type": "function", "config": {"tools": [{"name": "x"}]}}]
    return {"vars": {}, "graph": {"nodes": [{"id": "a", "type": "agent", "config": cfg}]}}


def _cfg(doc):
    return doc["graph"]["nodes"][0]["config"]


def test_legacy_node_binds_to_same_vendor_account_and_drops_keys(store):
    codex = store.create(vendor="openai", label="Codex", auth_type="cli")
    claude = store.create(vendor="anthropic", label="Claude", auth_type="cli")
    store.set_default(codex.id)
    doc = _doc()  # provider anthropic: the same-vendor account beats the default
    bind_default_connections(doc, {"ANTHROPIC_API_KEY": "set-in-env"})
    assert _cfg(doc)["connection"] == claude.id
    assert "api_key" not in _cfg(doc) and "base_url" not in _cfg(doc)

    store.set_default(claude.id)
    doc = _doc(provider="openai", name="gpt-6.1-sol")  # A4-1: provider openai -> Codex, not the default
    bind_default_connections(doc, {})
    assert _cfg(doc)["connection"] == codex.id
    assert _cfg(doc)["name"] == "gpt-6.1-sol"


def test_node_without_provider_uses_default_and_keeps_model(store):
    """A4-3: no provider means no vendor mismatch, so the chosen model name is never overwritten."""
    store.create(vendor="anthropic", label="Claude", auth_type="cli")
    cfg = {"name": "claude-haiku-4-5"}
    doc = {"graph": {"nodes": [{"id": "a", "type": "agent", "config": cfg}]}}
    bind_default_connections(doc, {})
    assert cfg["name"] == "claude-haiku-4-5" and cfg["connection"]


def test_env_key_no_longer_keeps_a_node_on_api_key(store):
    claude = store.create(vendor="anthropic", label="Claude", auth_type="cli")
    doc = _doc()
    bind_default_connections(doc, {"ANTHROPIC_API_KEY": "sk-from-env", "BASE_URL": "https://x"})
    assert _cfg(doc)["connection"] == claude.id and "api_key" not in _cfg(doc)


def test_other_vendor_account_swaps_model(store):
    claude = store.create(vendor="anthropic", label="Claude", auth_type="cli")
    doc = _doc(provider="openai", name="gpt-4o")
    bind_default_connections(doc, {})
    assert _cfg(doc)["connection"] == claude.id
    assert _cfg(doc)["name"].startswith("claude-")


def test_explicit_connection_kept_and_legacy_keys_dropped(store):
    store.create(vendor="anthropic", label="Claude", auth_type="cli")
    doc = _doc(connection="mine")
    bind_default_connections(doc, {})
    assert _cfg(doc)["connection"] == "mine" and "api_key" not in _cfg(doc)


def test_unset_model_placeholder_uses_account_default(store):
    store.create(vendor="anthropic", label="Claude", auth_type="cli")
    doc = _doc(name="${MODEL_NAME}")
    bind_default_connections(doc, {})
    assert _cfg(doc)["name"] == "claude-fable-5-1"  # first model of the catalog fallback

    doc = _doc(name="${MODEL_NAME}")
    doc["vars"] = {"MODEL_NAME": "claude-haiku-5-5"}
    bind_default_connections(doc, {})
    assert _cfg(doc)["name"] == "${MODEL_NAME}"  # set in vars: resolved later as usual


def test_no_account_gives_friendly_error(store):
    with pytest.raises(ConfigError, match="Connections page"):
        bind_default_connections(_doc(), {})


def test_legacy_api_key_connection_is_never_used(store, tmp_path):
    (tmp_path / "c.json").write_text(
        json.dumps({"version": 1, "connections": [{"id": "old", "vendor": "anthropic", "label": "Old key",
                                                   "auth_type": "api_key", "secret": "${X_API_KEY}"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="Connections page"):
        bind_default_connections(_doc(), {})


def test_tool_nodes_run_on_claude_and_codex(store):
    codex = store.create(vendor="openai", label="Codex", auth_type="cli")
    doc = _doc(provider="openai", name="gpt-6.1-sol", tooling=True)
    bind_default_connections(doc, {})
    assert _cfg(doc)["connection"] == codex.id


def test_nodes_inside_inline_subgraphs_are_bound(store):
    claude = store.create(vendor="anthropic", label="Claude", auth_type="cli")
    inner = _doc()["graph"]
    doc = {"graph": {"nodes": [{"id": "sg", "type": "subgraph", "config": {"type": "config", "config": inner}}]}}
    bind_default_connections(doc, {})
    assert inner["nodes"][0]["config"]["connection"] == claude.id


def test_validation_does_not_require_a_signed_in_account(monkeypatch):
    """CI has no signed-in accounts: structure validation must not fail on account binding."""
    from agentdev.connections import autobind

    class EmptyStore:
        def list(self):
            return []

        def default_connection(self):
            return None

    monkeypatch.setattr(autobind, "get_store", lambda: EmptyStore())
    data = {"graph": {"nodes": [{"id": "A", "type": "agent", "config": {"provider": "anthropic", "name": "m"}}]}}
    autobind.bind_default_connections(data, {}, require_accounts=False)
    assert "connection" not in data["graph"]["nodes"][0]["config"]
    import pytest
    from agentdev.entity.configs import ConfigError

    with pytest.raises(ConfigError):
        autobind.bind_default_connections(data, {})


def test_retired_gemini_model_is_replaced_with_catalog_default(store):
    from agentdev.connections.catalog import get_vendor

    gem = store.create(vendor="gemini", label="G", auth_type="oauth", secret="{}")
    default = get_vendor("gemini").models[0]
    for old in ("gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"):
        doc = _doc(provider="gemini", name=old, connection=gem.id)
        bind_default_connections(doc, {})
        assert _cfg(doc)["name"] == default, old
    # a valid or image model is left alone
    for ok in ("gemini-3.1-pro-preview", "gemini-2.5-flash-image"):
        doc = _doc(provider="gemini", name=ok, connection=gem.id)
        bind_default_connections(doc, {})
        assert _cfg(doc)["name"] == ok


def test_providerless_claude_model_is_not_left_on_a_codex_default(store):
    """A provider-less node naming a Claude model must not run that model name on the Codex default."""
    codex = store.create(vendor="openai", label="Codex", auth_type="cli")
    claude = store.create(vendor="anthropic", label="Claude", auth_type="cli")
    store.set_default(codex.id)
    cfg = {"name": "claude-haiku-4-5"}
    doc = {"graph": {"nodes": [{"id": "a", "type": "agent", "config": cfg}]}}
    bind_default_connections(doc, {})
    assert cfg["connection"] == claude.id and cfg["name"] == "claude-haiku-4-5"


def test_providerless_claude_model_with_only_codex_switches_to_its_default_model(store):
    codex = store.create(vendor="openai", label="Codex", auth_type="cli")
    cfg = {"name": "claude-haiku-4-5"}
    doc = {"graph": {"nodes": [{"id": "a", "type": "agent", "config": cfg}]}}
    bind_default_connections(doc, {})
    assert cfg["connection"] == codex.id and not cfg["name"].startswith("claude")
