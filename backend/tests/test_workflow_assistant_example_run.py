"""Run the reference's Example 2 (article pipeline) on the real engine with scripted models and a scripted
person, to prove what each node actually receives. The model copies this example as its pattern for
gates, so the publishing node must get the article, not just the person's "OK"."""

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from agentdev.api.services.workflow_lab import static_check_data
from agentdev.entity.messages import Message, MessageRole
from agentdev.runtime.node.agent import ModelResponse, ProviderRegistry
from agentdev.runtime.node.executor import agent_executor as agent_executor_module
from agentdev.utils.human_prompt import HumanPromptService, PromptResult

REFERENCE = Path(__file__).resolve().parents[1] / "agentdev" / "api" / "services" / "workflow_assistant_reference.md"


def _example_2():
    blocks = re.findall(r"^```yaml\n(.*?)^```", REFERENCE.read_text(encoding="utf-8"), flags=re.MULTILINE | re.DOTALL)
    return yaml.safe_load(blocks[1])


class ScriptedProvider:
    scripts: dict = {}
    seen: dict = {}

    def __init__(self, config):
        self.config = config

    def create_client(self):
        return None

    def call_model(self, client, conversation, timeline, tool_specs=None, **kwargs):
        node_id = self.config.node_id
        self.seen.setdefault(node_id, []).append([m.text_content() for m in conversation])
        return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=self.scripts[node_id].pop(0)))

    def extract_token_usage(self, response):
        return None


@pytest.fixture()
def run_example(tmp_path, monkeypatch):
    data = _example_2()
    for node in data["graph"]["nodes"]:
        if node["type"] == "agent":
            node["config"]["connection"] = "fake"  # no signed-in account in tests
    path = tmp_path / "article_pipeline.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    creds = SimpleNamespace(provider="fake", vendor="fake", token="", base_url="")
    monkeypatch.setattr(agent_executor_module, "resolve_connection", lambda _id: creds)
    monkeypatch.setattr(ProviderRegistry, "get_provider", lambda _name: ScriptedProvider)
    human = {"answers": [], "inputs": []}

    def fake_request(self, node_id, task_description, *, inputs=None, metadata=None):
        human["inputs"].append(inputs or "")
        return PromptResult(text=human["answers"].pop(0))

    monkeypatch.setattr(HumanPromptService, "request", fake_request)

    def run(scripts, answers):
        from agentdev.runtime.sdk import run_workflow

        ScriptedProvider.scripts = {k: list(v) for k, v in scripts.items()}
        ScriptedProvider.seen = {}
        human["answers"] = list(answers)
        human["inputs"] = []
        run_workflow(path, task_prompt="Viết bài về cà phê Đà Lạt")
        publisher_calls = ScriptedProvider.seen.get("Publisher", [])
        assert len(publisher_calls) == 1, publisher_calls
        return "\n".join(publisher_calls[0]), human

    return run


def test_publisher_receives_the_approved_article(run_example):
    received, human = run_example(
        {"Writer": ["DRAFT-1 cà phê"], "Reviewer": ["APPROVED"], "Publisher": ["# Done"]},
        ["OK"],
    )
    # The person approves the draft they were shown, and that same draft is what gets published.
    assert "DRAFT-1" in human["inputs"][0]
    assert "DRAFT-1" in received


def test_publisher_receives_only_the_newest_article_after_change_notes(run_example):
    received, human = run_example(
        {"Writer": ["DRAFT-1", "DRAFT-2"], "Reviewer": ["APPROVED", "APPROVED"], "Publisher": ["# Done"]},
        ["Sửa tiêu đề", "ok"],
    )
    assert "DRAFT-1" in human["inputs"][0] and "DRAFT-1" not in human["inputs"][1]
    assert "DRAFT-2" in human["inputs"][1]
    assert re.findall(r"DRAFT-\d", received) == ["DRAFT-2"]


def test_at_the_limit_the_person_and_publisher_see_the_last_draft(run_example):
    received, human = run_example(
        {"Writer": ["DRAFT-1", "DRAFT-2", "DRAFT-3", "DRAFT-4"],
         "Reviewer": ["REVISE\n1. fix", "REVISE\n1. fix", "REVISE\n1. fix"],
         "Publisher": ["# Done"]},
        ["OK"],
    )
    assert len(human["inputs"]) == 1
    # Minor 9: the person decides on the last reviewed draft, not on the guard message alone.
    assert "Revision limit reached" in human["inputs"][0]
    assert re.findall(r"DRAFT-\d", human["inputs"][0]) == ["DRAFT-3"]
    assert re.findall(r"DRAFT-\d", received) == ["DRAFT-3"]
    assert len(ScriptedProvider.seen["Writer"]) == 3  # the Writer does not run again after the limit


def test_example_2_feeds_the_publisher_through_a_data_edge_and_still_passes_static_check():
    data = _example_2()
    edges = data["graph"]["edges"]
    into_publisher = [e for e in edges if e["to"] == "Publisher"]
    triggering = [e for e in into_publisher if e.get("trigger", True)]
    # Only the person's OK starts the publishing node.
    assert [e["from"] for e in triggering] == ["Editor Approval"]
    data_edges = [e for e in into_publisher if e.get("trigger", True) is False]
    assert len(data_edges) == 1
    data_edge = data_edges[0]
    nodes = {n["id"]: n for n in data["graph"]["nodes"]}
    assert nodes[data_edge["from"]]["type"] == "agent"
    assert data_edge.get("carry_data", True) is True
    # Only the newest article reaches the publishing node.
    assert data_edge.get("clear_context") is True
    report = static_check_data(data)
    failed = [c for c in report["checks"] if c["status"] == "fail" and c["id"] != "accounts"]
    assert failed == [], failed
