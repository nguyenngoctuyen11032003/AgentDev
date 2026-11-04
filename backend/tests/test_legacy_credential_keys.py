"""Old workflows with api_key/base_url on an agent load the same way on every path (save, Lab check, subgraph)."""

import copy

import yaml

from agentdev.connections.autobind import strip_legacy_keys
from agentdev.validation.check import check_config

OLD = {"version": "0.4.0", "graph": {"id": "old", "start": ["A"], "end": ["A"], "edges": [], "nodes": [
    {"id": "A", "type": "agent", "config": {"provider": "anthropic", "name": "claude-haiku-5-5", "role": "x",
                                             "api_key": "sk-old", "base_url": "http://x"}}]}}


def test_save_and_lab_check_accept_an_old_workflow_and_never_change_the_caller_copy():
    data = copy.deepcopy(OLD)
    assert "api_key" not in (check_config(data) or "")
    assert data["graph"]["nodes"][0]["config"]["api_key"] == "sk-old"  # the file text is not rewritten here


def test_strip_reaches_nested_subgraphs_and_leaves_other_nodes_alone():
    nested = {"graph": {"nodes": [
        {"id": "S", "type": "subgraph", "config": {"type": "config", "config": copy.deepcopy(OLD["graph"])}},
        {"id": "L", "type": "literal", "config": {"content": "api_key stays in text", "base_url": "kept"}}]}}
    strip_legacy_keys(nested)
    inner = nested["graph"]["nodes"][0]["config"]["config"]["nodes"][0]["config"]
    assert "api_key" not in inner and "base_url" not in inner
    assert nested["graph"]["nodes"][1]["config"]["base_url"] == "kept"


def test_file_subgraph_with_api_key_builds(tmp_path):
    from agentdev.runtime.sdk import run_workflow  # noqa: F401 - registers node schemas
    from agentdev.validation.check import load_config

    sub = tmp_path / "sub.yaml"
    sub.write_text(yaml.safe_dump({"version": "0.4.0", "graph": {
        "id": "sub", "start": ["L"], "end": ["L"], "edges": [],
        "nodes": [{"id": "L", "type": "literal", "config": {"content": "hi"}},
                  {"id": "Old", "type": "agent", "config": {"provider": "anthropic", "name": "claude-haiku-5-5",
                                                            "role": "x", "api_key": "sk-old"}}]}}), encoding="utf-8")
    parent = tmp_path / "parent.yaml"
    parent.write_text(yaml.safe_dump({"version": "0.4.0", "graph": {
        "id": "p", "start": ["S"], "end": ["S"], "edges": [],
        "nodes": [{"id": "S", "type": "subgraph", "config": {"type": "file", "config": {"path": str(sub)}}}]}}),
        encoding="utf-8")
    payload = yaml.safe_load(sub.read_text(encoding="utf-8"))
    strip_legacy_keys(payload)
    assert "api_key" not in payload["graph"]["nodes"][1]["config"]
    load_config(parent)  # the parent loads; the subgraph is built at run time with the keys stripped
