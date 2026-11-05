"""Several end nodes: the one that finished LAST (with output) gives the answer; the lint warns when two can run together."""

import yaml

from agentdev.api.services.workflow_patterns.proposal_lint import lint
from agentdev.runtime.sdk import run_workflow


def _lit(node_id, text):
    return {"id": node_id, "type": "literal", "config": {"content": text, "role": "assistant"}}


def _kw(regex):
    return {"type": "keyword", "config": {"regex": [regex], "case_sensitive": True}}


def _wf(nodes, edges, end):
    return {"version": "0.4.0", "graph": {"id": "t", "start": ["A"], "end": end, "nodes": nodes, "edges": edges}}


def _run(tmp_path, data):
    path = tmp_path / "wf.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return run_workflow(path, task_prompt="go").final_message.text_content()


def test_only_one_end_node_runs_its_result_wins(tmp_path):
    data = _wf([_lit("A", "NO"), _lit("B", "b"), _lit("E1", "first"), _lit("E2", "second")],
               [{"from": "A", "to": "E1", "condition": _kw("^NO")}, {"from": "A", "to": "B", "condition": _kw("^YES")},
                {"from": "B", "to": "E2"}], ["E1", "E2"])
    assert _run(tmp_path, data) == "first"
    data["graph"]["end"] = ["E2", "E1"]  # declaration order must not matter when only one ran
    assert _run(tmp_path, data) == "first"


def test_two_end_nodes_run_the_last_finished_wins(tmp_path):
    data = _wf([_lit("A", "go"), _lit("B", "b"), _lit("E1", "early"), _lit("E2", "late")],
               [{"from": "A", "to": "E1"}, {"from": "A", "to": "B"}, {"from": "B", "to": "E2"}], ["E1", "E2"])
    assert _run(tmp_path, data) == "late"
    data["graph"]["end"] = ["E2", "E1"]
    assert _run(tmp_path, data) == "late"


def _notes(data):
    return [n for n in lint(data)[0] if "MULTIPLE_END_NODES" in n]


def test_lint_warns_when_two_end_nodes_can_run_together():
    data = _wf([_lit("A", "x"), _lit("B", "b"), _lit("E1", "e1"), _lit("E2", "e2")],
               [{"from": "A", "to": "E1"}, {"from": "A", "to": "B"}, {"from": "B", "to": "E2"}], ["E1", "E2"])
    assert len(_notes(data)) == 1


def test_lint_quiet_when_end_nodes_exclude_each_other():
    data = _wf([_lit("A", "x"), _lit("E1", "e1"), _lit("E2", "e2")],
               [{"from": "A", "to": "E1", "condition": _kw("^OK")}, {"from": "A", "to": "E2", "condition": _kw("^NO")}],
               ["E1", "E2"])
    assert _notes(data) == []
    single = _wf([_lit("A", "x"), _lit("E1", "e1")], [{"from": "A", "to": "E1"}], ["E1"])
    assert _notes(single) == []
