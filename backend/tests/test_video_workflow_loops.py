"""The real video workflow's revision loops, run through the engine with scripted stand-ins.

Every agent and human node of ``workspace/workflows/phong_san_xuat_video.yaml`` is replaced by a literal node
that always answers the same text, so the loop counters, gates and exits are exercised exactly as wired in the
YAML, without any model call. Each test then checks how many times each step ran and where the run ended.
"""

import collections
from pathlib import Path

import pytest
import yaml

from agentdev.paths import BACKEND_ROOT
from agentdev.runtime.node.executor.literal_executor import LiteralNodeExecutor
from agentdev.runtime.sdk import run_workflow

VIDEO_YAML = BACKEND_ROOT.parent / "workspace" / "workflows" / "phong_san_xuat_video.yaml"
REJECT = "Sửa lại màu cảnh 2"


def _scripted_copy(tmp_path: Path, answers: dict) -> Path:
    """Copy the workflow with every agent/human node turned into a literal that says ``answers[id]``."""
    data = yaml.safe_load(VIDEO_YAML.read_text(encoding="utf-8"))
    for node in data["graph"]["nodes"]:
        if node["type"] in ("agent", "human"):
            text = answers.get(node["id"], f"{node['id']} output")
            role = "user" if node["type"] == "human" else "assistant"
            node_id = node["id"]
            node.clear()
            node.update({"id": node_id, "type": "literal", "config": {"content": text, "role": role}})
    path = tmp_path / "video.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def runs(monkeypatch):
    counts = collections.Counter()
    original = LiteralNodeExecutor.execute

    def counting(self, node, inputs):
        counts[node.id] += 1
        return original(self, node, inputs)

    monkeypatch.setattr(LiteralNodeExecutor, "execute", counting)
    return counts


def _run(tmp_path, **answers):
    base = {"Intake": "EPISODE 1: tập mở đầu", "Script Reviewer": "APPROVED", "Script Approval": "ok",
            "Video Approval": "ok", "Final Approval": "ok", "Archivist": "Đã lưu hồ sơ tập 1"}
    base.update(answers)
    return run_workflow(_scripted_copy(tmp_path, base), task_prompt="Làm tập 1")


def test_happy_path_runs_each_step_once(tmp_path, runs):
    result = _run(tmp_path)
    assert result.final_message is not None and "Đã lưu" in result.final_message.text_content()
    for step in ("Writer", "Script Reviewer", "Visual Director", "Voice & Subtitles", "Thumbnail Title",
                 "Production QA", "Video Approval", "Archivist"):
        assert runs[step] == 1, (step, dict(runs))


def test_script_review_loop_stops_at_its_limit(tmp_path, runs):
    """A reviewer that never approves: the Writer gets 2 rewrites at most, then the person decides."""
    result = _run(tmp_path, **{"Script Reviewer": "Cần sửa: mở đầu yếu"})
    assert runs["Writer"] == 2 and runs["Script Reviewer"] == 2, dict(runs)
    assert runs["Script Approval"] == 1 and runs["Archivist"] == 1, dict(runs)
    assert "Đã lưu" in result.final_message.text_content()


def test_production_loop_stops_after_three_revisions(tmp_path, runs):
    """A person who keeps sending notes: 3 revisions are applied, the 4th note leads to one last check, then
    the episode is archived."""
    result = _run(tmp_path, **{"Video Approval": REJECT})
    assert runs["Visual Director"] == 4, dict(runs)  # first package + 3 revisions
    assert runs["Video Approval"] == 4, dict(runs)
    assert runs["Final Approval"] == 1 and runs["Archivist"] == 1, dict(runs)
    assert "Đã lưu" in result.final_message.text_content()


def test_production_loop_can_stop_without_archiving(tmp_path, runs):
    """Still not happy at the final check: the run ends with a clear message and nothing is archived."""
    result = _run(tmp_path, **{"Video Approval": REJECT, "Final Approval": "chưa được"})
    assert runs["Visual Director"] == 4 and runs["Archivist"] == 0, dict(runs)
    assert "chưa được lưu" in result.final_message.text_content()


def test_silence_never_archives_the_episode(tmp_path, runs):
    """Nobody answers the gates: the loop stays bounded and the run stops without archiving anything."""
    from agentdev.api.services.session_execution import NO_REPLY_TEXT

    result = _run(tmp_path, **{"Video Approval": NO_REPLY_TEXT, "Final Approval": NO_REPLY_TEXT})
    assert runs["Visual Director"] == 4 and runs["Archivist"] == 0, dict(runs)
    assert "chưa được lưu" in result.final_message.text_content()


# --- the static check flags a counter the engine never reaches ---------------------------------------------

def _loop_graph(guard_back_to: str) -> dict:
    """Director -> QA -> Approval loop, notes go back to Director and to a Guard wired back to ``guard_back_to``."""
    edges = [{"from": "Intake", "to": "Director"}, {"from": "Director", "to": "QA"}, {"from": "QA", "to": "Approval"},
             {"from": "Approval", "to": "Director"}, {"from": "Approval", "to": "Guard"},
             {"from": "Guard", "to": guard_back_to}, {"from": "Guard", "to": "Done"}]
    nodes = [{"id": n, "type": "agent"} for n in ("Intake", "Director", "QA", "Done")]
    nodes += [{"id": "Approval", "type": "human"}, {"id": "Guard", "type": "loop_counter"}]
    return {"graph": {"start": ["Intake"], "end": ["Done"], "nodes": nodes, "edges": edges}}


def test_counter_on_inner_loop_is_flagged_and_loop_counts_as_unguarded():
    from agentdev.api.services.workflow_patterns.graph_analysis import Graph
    from agentdev.api.services.workflow_patterns.proposal_lint import lint

    bad = Graph.from_workflow(_loop_graph("Approval"))
    assert bad.counters_in_inner_loop() == ["Guard"]
    assert bad.unguarded_cycles(), "a counter that never runs must not count as a guard"
    assert any("Guard" in note and "never counts" in note for note in lint(_loop_graph("Approval"))[0])

    good = Graph.from_workflow(_loop_graph("Director"))
    assert good.counters_in_inner_loop() == [] and good.unguarded_cycles() == []


def test_shipped_workflows_have_no_unreachable_counters():
    from agentdev.api.services.workflow_patterns.graph_analysis import Graph

    folders = [BACKEND_ROOT.parent / "workspace" / "workflows",
               BACKEND_ROOT / "agentdev" / "api" / "services" / "workflow_patterns"]
    for path in sorted(p for folder in folders for p in folder.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert Graph.from_workflow(data).counters_in_inner_loop() == [], path.name


def test_counter_dead_from_one_of_two_entries_is_flagged():
    """The engine starts a loop from the one entry that fired, so a counter dead from either entry is flagged."""
    from agentdev.api.services.workflow_patterns.graph_analysis import Graph

    # Guard -> QA: entering at QA (fed by Fix) it is fine; entering at Director it sits on QA -> Approval -> Guard.
    data = _loop_graph("QA")
    data["graph"]["nodes"].append({"id": "Fix", "type": "agent"})
    data["graph"]["edges"] += [{"from": "Intake", "to": "Fix"}, {"from": "Fix", "to": "QA"}]
    assert Graph.from_workflow(data).counters_in_inner_loop() == ["Guard"]


def test_misplaced_counter_is_reported_once():
    from agentdev.api.services.workflow_patterns.proposal_lint import lint

    notes = lint(_loop_graph("Approval"))[0]
    assert not any(n.startswith("Loop without a loop_counter") for n in notes)
    assert sum("Guard" in n for n in notes) == 1
