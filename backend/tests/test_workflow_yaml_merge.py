"""Saving from the visual editor must change only what was edited in a hand-written workflow YAML."""

import copy
import difflib
import json
from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import workflows as workflows_route
from agentdev.api.services.workflow_yaml_merge import merge_workflow_document

TEMPLATES = Path(__file__).resolve().parents[2] / "workspace" / "workflows"

SOURCE = """\
version: 0.4.0
vars: {}
graph:
  id: demo
  description: >-
    A hand-written workflow with comments, anchors
    and folded text.
  start:
    - Lead
  nodes:
    # ------------------------------------------------ lead
    - id: Lead
      type: agent
      description: Talks to the user   # trailing comment
      config:
        provider: anthropic
        name: claude-opus-5-5
        role: |-
          You are the lead.

          Keep answers short.
        tooling: &doc_tools
          - type: function
            config:
              tools:
                - name: read_file_segment
                - name: save_file
        retry: null
        params:
          effort: medium

    # ------------------------------------------------ team
    - id: Writer
      type: agent
      description: 'Writes things'
      config:
        provider: anthropic
        name: claude-sonnet-5-5
        role: |-
          You write.
        tooling: *doc_tools
        params:
          effort: low

    - id: Reviewer
      type: agent
      config:
        provider: anthropic
        name: claude-sonnet-5-5
        tooling: *doc_tools
  edges:
    - from: Lead
      to: Writer
    - from: Writer
      to: Reviewer
"""


def _desired(text: str) -> dict:
    # What the editor sends: plain JSON data, aliases expanded into independent copies.
    return json.loads(json.dumps(yaml.safe_load(text)))


def _node(document: dict, node_id: str) -> dict:
    return next(node for node in document["graph"]["nodes"] if node["id"] == node_id)


def _changed_lines(before: str, after: str) -> list[str]:
    return [
        line
        for line in difflib.unified_diff(before.splitlines(), after.splitlines(), lineterm="", n=0)
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]


def test_unchanged_document_is_byte_identical():
    assert merge_workflow_document(SOURCE, _desired(SOURCE)) == SOURCE


@pytest.mark.parametrize("path", sorted(TEMPLATES.glob("*.yaml")), ids=lambda p: p.name)
def test_shipped_templates_round_trip_unchanged(path):
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    assert merge_workflow_document(text, _desired(text)) == text


def test_editing_one_node_changes_only_that_node():
    desired = _desired(SOURCE)
    writer = _node(desired, "Writer")
    writer["description"] = "Writes the drafts"
    writer["config"]["params"]["effort"] = "high"
    # what the form used to add on save: nulls for fields the node never had
    writer["config"].update({"thinking": None, "team": None, "native_mode": None, "retry": None})

    result = merge_workflow_document(SOURCE, desired)

    assert _changed_lines(SOURCE, result) == [
        "-      description: 'Writes things'",
        "+      description: 'Writes the drafts'",
        "-          effort: low",
        "+          effort: high",
    ]
    # comments, the anchor, its aliases, the literal and folded blocks and the existing null survive
    assert "# ------------------------------------------------ team" in result
    assert "# trailing comment" in result
    assert "tooling: &doc_tools" in result
    assert result.count("tooling: *doc_tools") == 2
    assert "role: |-\n          You are the lead.\n\n          Keep answers short." in result
    assert "description: >-\n    A hand-written workflow" in result
    assert "retry: null" in result  # Lead's own null is kept
    parsed = yaml.safe_load(result)
    assert "thinking" not in _node(parsed, "Writer")["config"]
    assert parsed == _strip(desired)


def _strip(document: dict) -> dict:
    """Desired data minus null keys that were not in the source (what the merge must produce)."""
    expected = copy.deepcopy(document)
    for key in ("thinking", "team", "native_mode", "retry"):
        _node(expected, "Writer")["config"].pop(key, None)
    return expected


def test_multiline_edit_stays_a_literal_block():
    desired = _desired(SOURCE)
    _node(desired, "Lead")["config"]["role"] = "You are the lead.\n\nKeep answers short.\nCite files."

    result = merge_workflow_document(SOURCE, desired)

    assert _changed_lines(SOURCE, result) == ["+          Cite files."]
    assert yaml.safe_load(result) == desired


def test_editing_an_aliased_value_does_not_change_the_anchor_owner():
    desired = _desired(SOURCE)
    _node(desired, "Writer")["config"]["tooling"][0]["config"]["tools"].append({"name": "run_shell_command"})

    result = merge_workflow_document(SOURCE, desired)
    parsed = yaml.safe_load(result)

    assert parsed == desired
    lead_tools = _node(parsed, "Lead")["config"]["tooling"][0]["config"]["tools"]
    assert {"name": "run_shell_command"} not in lead_tools
    # the anchor and the untouched alias are still there
    assert "tooling: &doc_tools" in result
    assert "tooling: *doc_tools" in result


def test_cleared_field_is_removed_and_new_node_has_no_nulls():
    desired = _desired(SOURCE)
    del _node(desired, "Writer")["description"]
    desired["graph"]["nodes"].append(
        {"id": "Editor", "type": "agent", "description": None, "config": {"provider": "anthropic", "name": "x", "retry": None}}
    )

    result = merge_workflow_document(SOURCE, desired)
    parsed = yaml.safe_load(result)

    assert "description" not in _node(parsed, "Writer")
    assert _node(parsed, "Editor") == {"id": "Editor", "type": "agent", "config": {"provider": "anthropic", "name": "x"}}
    assert "# ------------------------------------------------ lead" in result


def test_merge_endpoint_preserves_crlf_and_untouched_lines(tmp_path, monkeypatch):
    template = (TEMPLATES / "software_company.yaml").read_bytes().decode("utf-8").replace("\r\n", "\n")
    target = tmp_path / "copy_test.yaml"
    target.write_bytes(template.replace("\n", "\r\n").encode("utf-8"))
    monkeypatch.setattr(workflows_route, "YAML_DIR", tmp_path)

    desired = _desired(template)
    node = desired["graph"]["nodes"][1]
    node["description"] = "Edited from the form"

    app = FastAPI()
    app.include_router(workflows_route.router)
    response = TestClient(app).put("/api/workflows/copy_test.yaml/merge", json={"document": desired})

    assert response.status_code == 200, response.text
    saved = target.read_bytes().decode("utf-8")
    assert "\r\n" in saved and "\n" not in saved.replace("\r\n", "")
    changed = _changed_lines(template, saved.replace("\r\n", "\n"))
    assert len(changed) == 2 and changed[1].endswith("description: Edited from the form")
    assert response.json()["content"] == saved.replace("\r\n", "\n")


def test_list_can_include_descriptions(tmp_path, monkeypatch):
    (tmp_path / "a.yaml").write_text("graph:\n  description: First\n", encoding="utf-8")
    (tmp_path / "b.yaml").write_text("graph: {}\n", encoding="utf-8")
    monkeypatch.setattr(workflows_route, "YAML_DIR", tmp_path)
    app = FastAPI()
    app.include_router(workflows_route.router)
    client = TestClient(app)

    assert client.get("/api/workflows").json() == {"workflows": ["a.yaml", "b.yaml"]}
    assert client.get("/api/workflows?include_descriptions=true").json() == {
        "workflows": ["a.yaml", "b.yaml"],
        "descriptions": {"a.yaml": "First", "b.yaml": ""},
    }


def test_new_regex_in_flow_edge_stays_parseable():
    """A regex like ^(?!\s*A) written into a flow-style edge must be quoted (PyYAML rejects it plain)."""
    original = "graph:\n  edges:\n    - {from: A, to: B, trigger: false}\n"
    desired = {"graph": {"edges": [{
        "from": "A", "to": "B", "trigger": False,
        "condition": {"type": "keyword", "config": {"regex": [r"^(?!\s*SCRIPT\b)"], "case_sensitive": True}},
    }]}}
    text = merge_workflow_document(original, desired)
    assert yaml.safe_load(text) == desired


DUP_PAIR_SOURCE = """\
version: 0.4.0
graph:
  id: dup
  start: [A]
  nodes:
    - id: A
      type: literal
      config: {content: a}
    - id: B
      type: literal
      config: {content: b}
  edges:
    # carries the draft, does not start B
    - from: A
      to: B
      trigger: false
    # starts B only on approval
    - from: A
      to: B
      condition:
        type: keyword
        config:
          regex: ["^OK"]
"""


def test_editing_second_of_two_same_pair_edges_keeps_the_first():
    # The editor identifies an edge by its index in graph.edges, so two edges between the same pair
    # are edited separately and the save keeps the untouched one byte for byte.
    desired = yaml.safe_load(DUP_PAIR_SOURCE)
    desired["graph"]["edges"][1]["condition"]["config"]["regex"] = ["^APPROVED"]
    merged = merge_workflow_document(DUP_PAIR_SOURCE, desired)
    edges = yaml.safe_load(merged)["graph"]["edges"]
    assert edges[0] == {"from": "A", "to": "B", "trigger": False}
    assert edges[1]["condition"]["config"]["regex"] == ["^APPROVED"]
    assert "# carries the draft, does not start B" in merged
    assert "# starts B only on approval" in merged
    changed = [line for line in difflib.ndiff(DUP_PAIR_SOURCE.splitlines(), merged.splitlines())
               if line.startswith(("- ", "+ "))]
    assert all("OK" in line or "APPROVED" in line for line in changed)


def test_edited_edge_appended_by_the_editor_keeps_its_place():
    # The edge form saves the list without the edited edge plus the edited edge at the end: one save
    # must put it back where it was, without touching the other edges.
    original = yaml.safe_load(DUP_PAIR_SOURCE)
    first, second = original["graph"]["edges"]
    edited_first = {**first, "trigger": True}
    desired = copy.deepcopy(original)
    desired["graph"]["edges"] = [second, edited_first]
    merged = merge_workflow_document(DUP_PAIR_SOURCE, desired)
    edges = yaml.safe_load(merged)["graph"]["edges"]
    assert edges[0] == {"from": "A", "to": "B", "trigger": True}
    assert edges[1]["condition"]["config"]["regex"] == ["^OK"]
    assert merged.index("# carries the draft") < merged.index("trigger: true") < merged.index("# starts B only")


def test_real_reorder_without_edit_is_kept():
    original = yaml.safe_load(DUP_PAIR_SOURCE)
    desired = copy.deepcopy(original)
    desired["graph"]["edges"].reverse()
    edges = yaml.safe_load(merge_workflow_document(DUP_PAIR_SOURCE, desired))["graph"]["edges"]
    assert edges == desired["graph"]["edges"]
