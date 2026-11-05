"""Tokens of a call that fails (CLI error, timeout, kill) are still spent: they reach the TokenTracker, so the
run's max_tokens / max_cost guards see them. Also the per-node ``agentdev.run_summary`` log line."""

from __future__ import annotations

import json
import logging
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agentdev.entity.messages import Message, MessageRole
from agentdev.runtime.node.agent.providers._cli_common import CliClient, CliProviderError, CliTimeoutError
from agentdev.runtime.node.agent.providers.claude_cli_provider import ClaudeCliProvider
from agentdev.runtime.node.agent.providers.codex_cli_provider import CodexCliProvider
from agentdev.utils.token_tracker import BudgetExceededError, TokenTracker

ERROR_RESULT = {
    "type": "result", "is_error": True, "result": "API Error: overloaded",
    "usage": {"input_tokens": 5000, "output_tokens": 800}, "total_cost_usd": 0.12,
}


def _provider(cls, tracker, limits=None):
    if limits:
        tracker.configure_limits(limits)
    cfg = SimpleNamespace(base_url=None, api_key=None, name="m1", provider="x", params={}, token_tracker=tracker,
                          node_id="N1")
    return cls(cfg)


def _conv():
    return [Message(role=MessageRole.SYSTEM, content="be brief"), Message(role=MessageRole.USER, content="hello")]


def _done(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


def _call(provider):
    return provider.call_model(CliClient("claude"), _conv(), [])


def test_claude_is_error_result_is_recorded():
    tracker = TokenTracker("wf")
    p = _provider(ClaudeCliProvider, tracker)
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(1, json.dumps(ERROR_RESULT))):
        with pytest.raises(CliProviderError, match="overloaded"):
            _call(p)
    usage = tracker.get_token_usage()
    assert usage["total_usage"]["input_tokens"] == 5000 and usage["total_usage"]["output_tokens"] == 800
    assert usage["summary"]["cost_usd"] == 0.12 and usage["summary"]["cost_known"] is True


def test_claude_nonzero_exit_with_json_is_recorded():
    tracker = TokenTracker("wf")
    p = _provider(ClaudeCliProvider, tracker)
    ok_shape = {**ERROR_RESULT, "is_error": False}
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(1, json.dumps(ok_shape), "boom")):
        with pytest.raises(CliProviderError, match="code 1"):
            _call(p)
    assert tracker.get_token_usage()["total_usage"]["total_tokens"] == 5800


def test_claude_timeout_records_partial_usage_without_inventing_a_price():
    tracker = TokenTracker("wf")
    p = _provider(ClaudeCliProvider, tracker)
    assistant = {"type": "assistant", "message": {"id": "m1", "content": [],
                                                   "usage": {"input_tokens": 700, "output_tokens": 40,
                                                             "cache_read_input_tokens": 300}}}

    def fake(cmd, **kw):
        kw["on_stdout_line"](json.dumps(assistant) + "\n")
        kw["on_stdout_line"](json.dumps(assistant) + "\n")  # the CLI repeats a message: counted once
        raise subprocess.TimeoutExpired(cmd, 1)

    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        with pytest.raises(CliTimeoutError):
            _call(p)
    usage = tracker.get_token_usage()
    assert usage["total_usage"]["input_tokens"] == 1000 and usage["total_usage"]["output_tokens"] == 40
    assert usage["summary"]["cost_known"] is False and usage["summary"]["cost_usd"] == 0
    assert usage["node_rollups"]["N1"]["cost_known"] is False
    assert usage["call_history"][-1]["cost_known"] is False


def test_codex_failed_run_with_usage_is_recorded():
    tracker = TokenTracker("wf")
    p = _provider(CodexCliProvider, tracker)
    events = '{"type":"turn.completed","usage":{"input_tokens":4000,"cached_input_tokens":0,"output_tokens":500}}\n'
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(1, events, "boom")):
        with pytest.raises(CliProviderError, match="code 1"):
            p.call_model(CliClient("codex"), _conv(), [])
    assert tracker.get_token_usage()["total_usage"]["total_tokens"] == 4500


def test_budget_guard_sees_failed_calls_and_does_not_hide_the_error():
    tracker = TokenTracker("wf")
    p = _provider(ClaudeCliProvider, tracker, {"max_tokens": 1000})
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(1, json.dumps(ERROR_RESULT))):
        with pytest.raises(CliProviderError, match="overloaded"):  # not BudgetExceededError masking the cause
            _call(p)
    with pytest.raises(BudgetExceededError):  # the next check of the run stops it
        tracker.check_budget("N1")

    tracker = TokenTracker("wf")
    p = _provider(ClaudeCliProvider, tracker, {"max_cost_usd": 0.1})
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(1, json.dumps(ERROR_RESULT))):
        with pytest.raises(CliProviderError):
            _call(p)
    with pytest.raises(BudgetExceededError):
        tracker.check_budget("N1")


def test_every_failed_attempt_adds_up():
    tracker = TokenTracker("wf")
    p = _provider(ClaudeCliProvider, tracker)
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(1, json.dumps(ERROR_RESULT))):
        for _ in range(3):
            with pytest.raises(CliProviderError):
                _call(p)
    assert tracker.get_token_usage()["total_usage"]["total_tokens"] == 3 * 5800
    assert tracker.get_node_execution_count("N1") == 3


def test_resumed_session_error_keeps_the_per_call_cost_share():
    from agentdev.runtime.node.agent.providers._cli_common import CliSession

    p = _provider(ClaudeCliProvider, TokenTracker("wf"))
    session = CliSession(session_id="s1", scope="x")
    session.options["cost_usd"] = 0.5
    data = {"total_cost_usd": 0.62}
    ClaudeCliProvider._apply_session_cost(data, session, True)
    assert data["total_cost_usd"] == pytest.approx(0.12) and session.options["cost_usd"] == 0.62


def test_run_summary_line_per_node_run(caplog):
    from scripts import bench_tokens

    caplog.set_level(logging.INFO, logger="agentdev.run_summary")
    bench_tokens.run_all("fake", ["chat"], max_usd=0.5, max_runs=1)
    rows = [json.loads(r.getMessage()) for r in caplog.records if r.name == "agentdev.run_summary"]
    assert [r["node"] for r in rows] == ["Chat"]
    row = rows[0]
    assert set(row) == {"session", "node", "model", "tokens_in", "tokens_out", "cache_read", "cost_usd", "cost_known",
                        "duration_s", "status"}
    assert row["status"] == "ok" and row["tokens_in"] > 0 and row["tokens_out"] > 0
    assert row["cost_known"] is False  # the fake provider reports no price
    assert "Request" not in caplog.text and "be brief" not in caplog.text  # no prompt text in the log
