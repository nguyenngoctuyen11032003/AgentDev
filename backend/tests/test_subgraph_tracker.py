"""A subgraph runs under its parent's token tracker with its own node ids (``S/W``) and its own run_limits."""

import pytest
import yaml

from agentdev.runtime.sdk import run_workflow
from agentdev.utils.token_tracker import BudgetExceededError, ScopedTokenTracker, TokenTracker, TokenUsage


def _lit(node_id, text):
    return {"id": node_id, "type": "literal", "config": {"content": text, "role": "assistant"}}


def _write(tmp_path, inner, outer_limits=None):
    graph = {"id": "p", "start": ["W"], "end": ["S"],
             "nodes": [_lit("W", "outer"), {"id": "S", "type": "subgraph", "config": {"type": "config", "config": inner}}],
             "edges": [{"from": "W", "to": "S"}]}
    if outer_limits:
        graph["run_limits"] = outer_limits
    path = tmp_path / "wf.yaml"
    path.write_text(yaml.safe_dump({"version": "0.4.0", "graph": graph}), encoding="utf-8")
    return path


def test_same_node_id_in_parent_and_subgraph_does_not_share_the_per_node_cap(tmp_path):
    inner = {"id": "inner", "start": ["W"], "end": ["W"], "nodes": [_lit("W", "inner")], "edges": []}
    result = run_workflow(_write(tmp_path, inner, {"node_max_runs": {"W": 1}}), task_prompt="go")
    assert result.final_message.text_content() == "inner"
    runs = [r["node"] for r in result.meta_info.token_usage["node_runs"]]
    assert "S/W" in runs and runs.count("W") == 1 and "S" in runs


def test_subgraph_run_limits_are_enforced(tmp_path):
    inner = {"id": "inner", "start": ["A"], "end": ["B"], "run_limits": {"max_node_runs": 1},
             "nodes": [_lit("A", "a"), _lit("B", "b")], "edges": [{"from": "A", "to": "B"}]}
    with pytest.raises(Exception) as info:
        run_workflow(_write(tmp_path, inner), task_prompt="go")
    chain = [info.value, info.value.__cause__, info.value.__context__]
    assert any(isinstance(e, BudgetExceededError) or "node runs" in str(e) for e in chain if e)


def test_scoped_tracker_forwards_usage_to_parent_with_prefix():
    parent = TokenTracker("p")
    parent.configure_limits({"max_tokens": 100})
    scope = ScopedTokenTracker(parent, "S", {"node_max_runs": {"W": 1}})
    scope.record_usage("W", "m", TokenUsage(input_tokens=10, output_tokens=5, total_tokens=15))
    assert parent.get_token_usage()["node_usages"]["S/W"]["total_tokens"] == 15
    assert parent.total_usage.total_tokens == 15
    scope.check_budget("W", starting=True)
    scope.record_node_run("W", 1.0)
    with pytest.raises(BudgetExceededError):
        scope.check_budget("W", starting=True)  # the subgraph's own per-node cap
    parent.check_budget("W", starting=True)  # the parent's W is another node
    with pytest.raises(BudgetExceededError):  # the parent's budget still covers the nested calls
        scope.record_usage("X", "m", TokenUsage(input_tokens=90, output_tokens=0, total_tokens=90))
