"""continue_on_error: an optional step's failure becomes a note for the next steps instead of ending the run."""

import threading
from types import SimpleNamespace

import pytest
import yaml

from agentdev.entity.configs import ConfigError
from agentdev.entity.messages import Message, MessageRole
from agentdev.runtime.node.agent import ModelResponse, ProviderRegistry
from agentdev.runtime.node.executor import agent_executor as agent_executor_module
from agentdev.utils.exceptions import WorkflowCancelledError
from agentdev.utils.token_tracker import BudgetExceededError


class Provider:
    fail = {}  # node id -> exception to raise
    seen = {}  # node id -> texts of the conversation it got
    lock = threading.Lock()

    def __init__(self, config):
        self.config = config

    def create_client(self):
        return None

    def call_model(self, client, conversation, timeline, tool_specs=None, **kwargs):
        node_id = self.config.node_id
        with self.lock:
            self.seen[node_id] = [m.text_content() for m in conversation]
        if node_id in self.fail:
            raise self.fail[node_id]
        return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=f"{node_id} result"))

    def extract_token_usage(self, response):
        return None


@pytest.fixture
def provider(monkeypatch):
    creds = SimpleNamespace(provider="fake", vendor="fake", token="", base_url="")
    monkeypatch.setattr(agent_executor_module, "resolve_connection", lambda _id: creds)
    monkeypatch.setattr(ProviderRegistry, "get_provider", lambda _name: Provider)
    Provider.fail, Provider.seen = {}, {}
    return Provider


def _fanout(tmp_path, soft: bool):
    def agent(node_id, **extra):
        return {"id": node_id, "type": "agent", "description": node_id, **extra,
                "config": {"connection": "fake", "provider": "fake", "name": "fake-model", "role": node_id}}

    workers = ["W1", "W2", "W3"]
    extra = {"continue_on_error": True} if soft else {}
    definition = {"version": "0.4.0", "graph": {
        "id": "soft", "start": ["Plan"], "end": ["Merge"],
        "nodes": [agent("Plan"), *[agent(w, **extra) for w in workers], agent("Merge")],
        "edges": [{"from": "Plan", "to": w} for w in workers] + [{"from": w, "to": "Merge"} for w in workers]}}
    path = tmp_path / "wf.yaml"
    path.write_text(yaml.safe_dump(definition), encoding="utf-8")
    return path


def test_default_failure_still_stops_the_run(tmp_path, provider):
    from agentdev.runtime.sdk import run_workflow

    provider.fail = {"W2": RuntimeError("model down")}
    with pytest.raises(Exception):
        run_workflow(_fanout(tmp_path, soft=False), task_prompt="go")
    assert "Merge" not in provider.seen


def test_soft_failure_reaches_merge_as_a_note(tmp_path, provider):
    from agentdev.runtime.sdk import run_workflow

    provider.fail = {"W2": RuntimeError("model down")}
    result = run_workflow(_fanout(tmp_path, soft=True), task_prompt="go")
    merged = "\n".join(provider.seen["Merge"])
    assert "W1 result" in merged and "W3 result" in merged
    assert "Step 'W2' failed and was skipped" in merged and "model down" in merged
    assert result.final_message.text_content() == "Merge result"
    # the timing table must not show the failed step as ok
    runs = {r["node"]: r["status"] for r in result.meta_info.token_usage["node_runs"]}
    assert runs["W2"] == "error" and runs["W1"] == "ok" and runs["Merge"] == "ok"


@pytest.mark.parametrize("error", [WorkflowCancelledError("stopped"), BudgetExceededError("budget spent")])
def test_stop_errors_are_never_skipped(tmp_path, provider, error):
    from agentdev.runtime.sdk import run_workflow

    provider.fail = {"W2": error}
    with pytest.raises(Exception):
        run_workflow(_fanout(tmp_path, soft=True), task_prompt="go")
    assert "Merge" not in provider.seen


def test_continue_on_error_must_be_a_boolean():
    from agentdev.entity.configs import Node

    node = {"id": "A", "type": "literal", "config": {"content": "x"}, "continue_on_error": "yes"}
    with pytest.raises(ConfigError):
        Node.from_dict(node, path="graph.nodes[0]")
    node["continue_on_error"] = True
    assert Node.from_dict(node, path="graph.nodes[0]").continue_on_error is True


def test_continue_on_error_node_cannot_have_conditional_edges():
    from agentdev.validation.check_workflow import check_workflow_structure

    def graph(condition):
        edge = {"from": "A", "to": "B", **({"condition": condition} if condition else {})}
        return {"graph": {"end": ["B"], "edges": [edge], "nodes": [
            {"id": "A", "type": "literal", "continue_on_error": True, "config": {"content": "x"}},
            {"id": "B", "type": "literal", "config": {"content": "y"}}]}}

    assert check_workflow_structure(graph(None)) == []
    assert check_workflow_structure(graph("true")) == []
    keyword = {"type": "keyword", "config": {"regex": ["^ok"]}}
    assert any("continue_on_error" in e for e in check_workflow_structure(graph(keyword)))
