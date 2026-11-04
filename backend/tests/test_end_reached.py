"""A run that never reaches its end step must not be reported as a completed run (repros from the engine audit)."""

import pytest
import yaml

from agentdev.runtime.sdk import run_workflow
from agentdev.utils.exceptions import WorkflowExecutionError


def _lit(node_id, text, **extra):
    return {"id": node_id, "type": "literal", "config": {"content": text, "role": "assistant"}, **extra}


def _kw(regex):
    return {"type": "keyword", "config": {"regex": [regex], "case_sensitive": True}}


def _run(tmp_path, nodes, edges, end, start="S"):
    path = tmp_path / "wf.yaml"
    path.write_text(yaml.safe_dump({"version": "0.4.0", "graph": {
        "id": "t", "start": [start], "end": end, "nodes": nodes, "edges": edges}}), encoding="utf-8")
    return run_workflow(path, task_prompt="go")


def test_no_branch_matches_is_an_error_not_an_empty_success(tmp_path):
    nodes = [_lit("S", "neither"), _lit("A", "a"), _lit("B", "b"), _lit("E", "done")]
    edges = [{"from": "S", "to": "A", "condition": _kw("^X")}, {"from": "S", "to": "B", "condition": _kw("^Y")},
             {"from": "A", "to": "E"}, {"from": "B", "to": "E"}]
    with pytest.raises(WorkflowExecutionError, match="'S'"):
        _run(tmp_path, nodes, edges, ["E"])


def test_side_branch_output_is_never_returned_as_the_answer(tmp_path):
    nodes = [_lit("S", "go"), _lit("A", "a out"), _lit("Side", "Side out"), _lit("E", "done")]
    edges = [{"from": "S", "to": "A"}, {"from": "S", "to": "Side"}, {"from": "A", "to": "E", "condition": _kw("^X")}]
    with pytest.raises(WorkflowExecutionError):
        _run(tmp_path, nodes, edges, ["E"])


def test_loop_that_stops_without_its_exit_is_an_error(tmp_path):
    nodes = [_lit("S", "go"), _lit("A", "draft"), _lit("B", "MAYBE"), _lit("E", "done")]
    edges = [{"from": "S", "to": "A"}, {"from": "A", "to": "B"}, {"from": "B", "to": "A", "condition": _kw("^REV")},
             {"from": "B", "to": "E", "condition": _kw("^OK")}]
    with pytest.raises(WorkflowExecutionError):
        _run(tmp_path, nodes, edges, ["E"])


def test_reached_end_still_completes(tmp_path):
    nodes = [_lit("S", "OK"), _lit("A", "a"), _lit("E", "done")]
    edges = [{"from": "S", "to": "A", "condition": _kw("^NO")}, {"from": "S", "to": "E", "condition": _kw("^OK")}]
    result = _run(tmp_path, nodes, edges, ["A", "E"])
    assert result.final_message.text_content() == "done"
