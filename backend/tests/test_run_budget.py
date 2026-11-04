import threading

import pytest

from agentdev.utils.token_tracker import BudgetExceededError, TokenTracker, TokenUsage


def _usage(total=100, **meta):
    return TokenUsage(input_tokens=total // 2, output_tokens=total - total // 2, total_tokens=total, metadata=meta)


def test_summary_math_and_cache():
    t = TokenTracker("wf")
    t.record_usage("a", "m", _usage(100, total_cost_usd=0.5, cache_read_input_tokens=150,
                                    cache_creation_input_tokens=50, duration_ms=1200), provider="p")
    t.record_usage("b", "m", _usage(40, total_cost_usd=0.25))
    t.record_node_run("a", 3000)
    t.record_node_run("b", 500)
    snap = t.get_token_usage()
    s = snap["summary"]
    assert s["tokens"] == 140
    assert s["cost_usd"] == 0.75
    assert s["cache_hit_pct"] == round(100 * 150 / (150 + 50 + 70), 1)
    assert [n["node"] for n in s["top_nodes"]] == ["a", "b"]
    assert s["top_nodes"][0]["wall_s"] == 3.0 and s["top_nodes"][0]["cost_usd"] == 0.5
    assert snap["node_rollups"]["a"]["cache_read_tokens"] == 150
    assert snap["call_history"][0]["duration_ms"] == 1200
    assert "total_usage" in snap and "node_usages" in snap


def test_cache_hit_none_without_data():
    t = TokenTracker("wf")
    t.record_usage("a", "m", _usage())
    assert t.get_token_usage()["summary"]["cache_hit_pct"] is None


def test_node_runs_keep_all_loop_runs():
    t = TokenTracker("wf")
    for _ in range(3):
        t.record_node_run("loop", 10)
    runs = t.get_token_usage()["node_runs"]
    assert [r["n"] for r in runs] == [1, 2, 3]
    assert t.get_token_usage()["summary"]["top_nodes"][0]["runs"] == 3


def test_budget_exceeded_raises_and_cancels(monkeypatch):
    monkeypatch.delenv("AGENTDEV_MAX_RUN_TOKENS", raising=False)
    monkeypatch.delenv("AGENTDEV_MAX_RUN_SECONDS", raising=False)
    cancelled = threading.Event()
    t = TokenTracker("wf")
    t.configure_limits({"max_tokens": 100}, cancel_cb=lambda msg: cancelled.set())
    t.record_usage("hot", "m", _usage(90))  # 90% -> warning only
    with pytest.raises(BudgetExceededError) as exc:
        t.record_usage("hot", "m", _usage(50))
    assert cancelled.is_set()
    assert "hot" in str(exc.value) and "Vượt giới hạn" in str(exc.value) and "budget exceeded" in str(exc.value)
    with pytest.raises(BudgetExceededError):
        t.check_budget("x", starting=True)


def test_node_run_limits(monkeypatch):
    monkeypatch.delenv("AGENTDEV_MAX_RUN_TOKENS", raising=False)
    monkeypatch.delenv("AGENTDEV_MAX_RUN_SECONDS", raising=False)
    t = TokenTracker("wf")
    t.configure_limits({"node_max_runs": {"loop": 2}})
    t.record_node_run("loop", 1)
    t.check_budget("loop", starting=True)
    t.record_node_run("loop", 1)
    with pytest.raises(BudgetExceededError):
        t.check_budget("loop", starting=True)


def test_env_cap(monkeypatch):
    monkeypatch.setenv("AGENTDEV_MAX_RUN_TOKENS", "10")
    t = TokenTracker("wf")
    t.configure_limits(None)
    with pytest.raises(BudgetExceededError):
        t.record_usage("a", "m", _usage(50))
