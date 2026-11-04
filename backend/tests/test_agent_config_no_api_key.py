"""Models run only on account sign-in: an agent node that still carries API-key settings is refused."""

import pytest

from agentdev.entity.configs import AgentConfig, ConfigError
from agentdev.runtime.node.agent.providers.gemini_provider import GeminiProvider


@pytest.mark.parametrize("key, value", [("api_key", "${API_KEY}"), ("api_key", ""), ("base_url", "https://x")])
def test_agent_config_rejects_api_key_settings_with_a_helpful_message(key, value):
    with pytest.raises(ConfigError) as info:
        AgentConfig.from_dict({"connection": "work", "name": "claude-sonnet-5-5", key: value}, path="graph.nodes[0].config")
    message = str(info.value)
    assert f"'{key}' is no longer supported" in message
    assert "Connections page" in message and "connection" in message
    assert info.value.path == f"graph.nodes[0].config.{key}"


def test_agent_config_without_api_key_loads_and_has_no_credentials():
    cfg = AgentConfig.from_dict({"connection": "work", "name": "claude-sonnet-5-5"}, path="t")
    assert cfg.auth_token is None and cfg.base_url == ""
    assert not hasattr(cfg, "api_key")
    specs = AgentConfig.field_specs()
    assert "api_key" not in specs and "auth_token" not in specs and "base_url" not in specs


@pytest.mark.parametrize("token", [None, "", "oauth-bearer:", "oauth-bearer:   ", "AIza-plain-api-key"])
def test_gemini_refuses_anything_but_a_google_sign_in_token(token):
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.auth_token, provider.base_url = token, ""
    with pytest.raises(ValueError, match="Google account sign-in"):
        provider.create_client()
