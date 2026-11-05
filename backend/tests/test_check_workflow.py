"""Workflow structure lint: always-true conditions, the single natural end rule, duplicate-pair edges."""

import pytest

from agentdev.validation.check_workflow import check_workflow_structure, is_always_true_condition


def _literal(nid, **extra):
    return {"id": nid, "type": "literal", "config": {"content": nid}, **extra}


@pytest.mark.parametrize(
    "condition",
    [
        None,
        True,
        "true",
        " True ",
        {"type": "function", "config": {"name": "true"}},  # what the canvas writes for a new edge
        {"type": "function", "config": None},
        {"type": "function"},
    ],
)
def test_always_true_conditions_are_recognized(condition):
    assert is_always_true_condition(condition) is True


@pytest.mark.parametrize(
    "condition",
    [
        "is_approved",
        {"type": "function", "config": {"name": "is_approved"}},
        {"type": "keyword", "config": {"regex": ["^ok"]}},
        {"type": "keyword", "config": {"any": ["true"]}},
        False,
    ],
)
def test_real_conditions_are_not_always_true(condition):
    assert is_always_true_condition(condition) is False


def test_continue_on_error_accepts_canvas_default_condition():
    data = {"graph": {"end": ["B"], "nodes": [_literal("A", continue_on_error=True), _literal("B")], "edges": [
        {"from": "A", "to": "B", "condition": {"type": "function", "config": {"name": "true"}}}]}}
    assert check_workflow_structure(data) == []


def test_continue_on_error_still_rejects_function_condition():
    data = {"graph": {"end": ["B"], "nodes": [_literal("A", continue_on_error=True), _literal("B")], "edges": [
        {"from": "A", "to": "B", "condition": {"type": "function", "config": {"name": "is_approved"}}}]}}
    assert any("continue_on_error" in e for e in check_workflow_structure(data))


def test_single_natural_end_needs_no_explicit_end():
    data = {"graph": {"nodes": [_literal("A"), _literal("B")], "edges": [{"from": "A", "to": "B"}]}}
    assert check_workflow_structure(data) == []


def test_several_natural_ends_require_explicit_end():
    # Without 'end' the runtime would silently take the first sink's output; the lint must flag it.
    nodes = [_literal("A"), _literal("B"), _literal("C")]
    edges = [{"from": "A", "to": "B"}, {"from": "A", "to": "C"}]
    errors = check_workflow_structure({"graph": {"nodes": nodes, "edges": edges}})
    assert any("unique natural end" in e for e in errors)
    assert check_workflow_structure({"graph": {"nodes": nodes, "edges": edges, "end": ["B", "C"]}}) == []


def test_end_referencing_unknown_node_is_reported():
    data = {"graph": {"end": ["Z"], "nodes": [_literal("A")], "edges": []}}
    assert any("unknown node id 'Z'" in e for e in check_workflow_structure(data))


def test_duplicate_pair_edges_are_allowed_and_counted_once_per_edge():
    # Two edges between the same pair (e.g. one carries data, one triggers) are valid YAML.
    data = {"graph": {"nodes": [_literal("A"), _literal("B")], "edges": [
        {"from": "A", "to": "B", "trigger": False},
        {"from": "A", "to": "B", "condition": {"type": "keyword", "config": {"regex": ["^ok"]}}},
    ]}}
    assert check_workflow_structure(data) == []


def test_duplicate_pair_edges_on_continue_on_error_flag_only_the_conditional_one():
    data = {"graph": {"end": ["B"], "nodes": [_literal("A", continue_on_error=True), _literal("B")], "edges": [
        {"from": "A", "to": "B"},
        {"from": "A", "to": "B", "condition": {"type": "keyword", "config": {"regex": ["^ok"]}}},
    ]}}
    errors = check_workflow_structure(data)
    assert len(errors) == 1 and "continue_on_error" in errors[0]


@pytest.mark.parametrize(
    "condition,flagged",
    [
        ({"type": "function", "config": {"name": "is_aproved_typo"}}, True),
        ("is_aproved_typo", True),
        ({"type": "function", "config": {"name": "code_pass"}}, False),
        ({"type": "function", "config": {"name": "true"}}, False),
        ({"type": "keyword", "config": {"any": ["ok"]}}, False),
    ],
)
def test_unknown_condition_function_is_reported(condition, flagged):
    # At runtime an unknown function never fires (fail-closed), so the lint must catch the typo up front.
    data = {"graph": {"nodes": [_literal("A"), _literal("B")], "edges": [{"from": "A", "to": "B", "condition": condition}]}}
    errors = check_workflow_structure(data)
    assert any("unknown condition function" in e for e in errors) is flagged


def test_edge_function_added_after_first_lint_is_found(tmp_path):
    """The lint must not cache the function list forever: a file added later is picked up without a restart."""
    from agentdev.validation.check_workflow import _edge_function_exists

    (tmp_path / "base.py").write_text("def existing(data):\n    return True\n", encoding="utf-8")
    assert _edge_function_exists("existing", tmp_path) is True
    assert _edge_function_exists("added_later", tmp_path) is False
    (tmp_path / "later.py").write_text("def added_later(data):\n    return True\n", encoding="utf-8")
    assert _edge_function_exists("added_later", tmp_path) is True
