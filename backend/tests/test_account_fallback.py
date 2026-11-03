"""Claude -> Codex (and back) when an account runs out of quota mid-run."""

from types import SimpleNamespace

import pytest
import yaml

from agentdev.connections import store as store_module
from agentdev.connections.store import Connection
from agentdev.entity.messages import Message, MessageRole
from agentdev.runtime.node.agent import ModelResponse, ProviderRegistry
from agentdev.runtime.node.agent import account_fallback
from agentdev.runtime.node.agent.account_fallback import (
    QuotaExceededError,
    is_exhaustion_error,
    is_quota_error,
    looks_like_quota,
    pick_fallback,
)
from agentdev.runtime.node.executor import agent_executor as agent_executor_module

CLAUDE = Connection(id="claude-main", vendor="anthropic", label="Claude account")
CODEX = Connection(id="codex-main", vendor="openai", label="Codex account")
GEMINI = Connection(id="gemini-main", vendor="gemini", label="Gemini", auth_type="oauth")


@pytest.mark.parametrize(
    "text",
    [
        "Claude AI usage limit reached|1730000000",
        "You've hit your usage limit. Upgrade to Pro",
        "5-hour limit reached - resets 3pm",
        "Your credit balance is too low",
        "RESOURCE_EXHAUSTED: Quota exceeded for quota metric",
    ],
)
def test_quota_messages_are_recognised(text):
    assert looks_like_quota(text)
    assert is_exhaustion_error(RuntimeError(text))
    assert not is_quota_error(RuntimeError(text))  # only provider-raised QuotaExceededError is "quota"


@pytest.mark.parametrize(
    "text",
    [
        "`claude` CLI is not logged in", "timed out after 300s", "Overloaded",
        "Error: 429 Too Many Requests", "rate_limit_error: slow down", "error at line 429",
        "max output tokens limit reached", "disk quota exceeded", "implement rate-limit middleware",
    ],
)
def test_transient_or_unrelated_errors_do_not_switch_accounts(text):
    assert not looks_like_quota(text)
    assert not is_exhaustion_error(RuntimeError(text))


def test_quota_error_in_cause_chain():
    try:
        try:
            raise QuotaExceededError("limit")
        except QuotaExceededError as inner:
            raise ValueError("wrapped") from inner
    except ValueError as exc:
        assert is_quota_error(exc)


def test_pick_fallback_skips_same_cli_login():
    claude_cli_2 = Connection(id="claude-cli-2", vendor="anthropic", label="Claude CLI 2")
    assert pick_fallback("claude-main", needs_tools=True, exhausted={"codex-main"}, connections=[CLAUDE, claude_cli_2, CODEX]) is None


def test_pick_fallback_prefers_other_vendor():
    claude2 = Connection(id="claude-2", vendor="anthropic", label="Claude 2", auth_type="oauth")
    pool = [CLAUDE, claude2, GEMINI, CODEX]
    assert pick_fallback("claude-main", needs_tools=True, exhausted=set(), connections=pool).id == "codex-main"
    assert pick_fallback("codex-main", needs_tools=True, exhausted=set(), connections=pool).id == "claude-main"
    # Gemini (OAuth) is usable; same-vendor second account is the last resort.
    assert pick_fallback("claude-main", needs_tools=True, exhausted={"codex-main"}, connections=pool).id == "gemini-main"
    assert (
        pick_fallback("claude-main", needs_tools=True, exhausted={"codex-main", "gemini-main"}, connections=pool).id
        == "claude-2"
    )
    assert pick_fallback("claude-main", needs_tools=True, exhausted={"codex-main"}, connections=[CLAUDE, CODEX]) is None


# ---------------------------------------------------------------- end to end

class FakeStore:
    def __init__(self, conns):
        self.conns = {c.id: c for c in conns}

    def list(self):
        return list(self.conns.values())

    def get(self, conn_id):
        return self.conns.get(conn_id)

    def default_connection(self):
        return None


def _provider_for(vendor, calls, exhausted_vendors):
    class Provider:
        def __init__(self, config):
            self.config = config

        def create_client(self):
            return None

        def call_model(self, client, conversation, timeline, tool_specs=None, **kwargs):
            calls.append((self.config.node_id, vendor, self.config.name))
            if vendor in exhausted_vendors:
                raise QuotaExceededError(f"{vendor} usage limit reached")
            return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=f"{self.config.node_id} via {vendor}"))

        def extract_token_usage(self, response):
            return None

    return Provider


def test_run_switches_account_and_remembers_it(tmp_path, monkeypatch):
    fake_store = FakeStore([CLAUDE, CODEX])
    monkeypatch.setattr(store_module, "get_store", lambda: fake_store)
    monkeypatch.setattr(account_fallback, "get_store", lambda: fake_store)
    monkeypatch.setattr(account_fallback, "default_model_for", lambda conn: {"openai": "gpt-codex", "anthropic": "claude-x"}[conn.vendor])
    monkeypatch.setattr(agent_executor_module, "default_model_for", account_fallback.default_model_for)
    creds = {
        "claude-main": SimpleNamespace(provider="fake_claude", vendor="anthropic", token="", base_url=""),
        "codex-main": SimpleNamespace(provider="fake_codex", vendor="openai", token="", base_url=""),
    }
    monkeypatch.setattr(agent_executor_module, "resolve_connection", lambda conn_id: creds[conn_id])
    calls = []
    providers = {
        "fake_claude": _provider_for("anthropic", calls, {"anthropic"}),
        "fake_codex": _provider_for("openai", calls, set()),
    }
    monkeypatch.setattr(ProviderRegistry, "get_provider", lambda name: providers[name])

    def agent(node_id):
        return {"id": node_id, "type": "agent",
                "config": {"connection": "claude-main", "provider": "anthropic", "name": "claude-x", "role": "r"}}

    definition = {"version": "0.4.0", "graph": {"id": "fallback_test", "start": ["A"], "end": ["B"],
                                                 "nodes": [agent("A"), agent("B")],
                                                 "edges": [{"from": "A", "to": "B"}]}}
    path = tmp_path / "fallback.yaml"
    path.write_text(yaml.safe_dump(definition), encoding="utf-8")

    from agentdev.runtime.sdk import run_workflow

    result = run_workflow(path, task_prompt="go")

    assert result.final_message.text_content() == "B via openai"
    # A hit the limit once on Claude, then ran on Codex with the Codex model; B went straight to Codex.
    assert calls == [("A", "anthropic", "claude-x"), ("A", "openai", "gpt-codex"), ("B", "openai", "gpt-codex")]
