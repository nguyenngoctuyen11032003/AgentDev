"""Lab core audit: honest grading (unjudged), paid gates skipped, real cancellation, stable run ids."""

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from agentdev.api.services import workflow_lab
from agentdev.api.services.workflow_lab import LabRunner, Scenario
from agentdev.entity.messages import Message, MessageRole
from agentdev.runtime.node.agent import ModelResponse, ProviderRegistry
from agentdev.runtime.node.executor import agent_executor as agent_executor_module
from agentdev.utils.human_prompt import AUTO_SKIP_PAID, AutoAnswerChannel

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _lab_store(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow_lab, "_lab_dir", lambda: tmp_path / "lab_jobs")


def _wait(job):
    deadline = time.monotonic() + 20
    while job.status in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(0.02)
    return job.to_dict()


def _agent(node_id, role="r"):
    return {"id": node_id, "type": "agent",
            "config": {"connection": "fake", "provider": "fake", "name": "m", "role": role}}


def _fake_engine(monkeypatch, provider_cls):
    creds = SimpleNamespace(provider="fake", vendor="fake", token="", base_url="")
    monkeypatch.setattr(agent_executor_module, "resolve_connection", lambda _id: creds)
    monkeypatch.setattr(ProviderRegistry, "get_provider", lambda _name: provider_cls)


# ---------------------------------------------------------------------------- L1: judge down -> unjudged


@pytest.mark.parametrize("answer", [
    "TODO: điền nội dung sau",  # placeholder
    "Kế hoạch: 1. Dev làm web 2. QA kiểm thử",  # plan only
    "Xin lỗi, tôi không thể làm việc này.",  # refusal
])
def test_judge_failure_never_counts_as_pass(answer):
    def judge(*args, **kwargs):
        raise RuntimeError("No signed-in account")

    job = LabRunner().start(Path("x.yaml"), "x.yaml", [Scenario("a", "c")], 1,
                            run_once=lambda *a: {"answer": answer, "questions": []}, judge=judge)
    data = _wait(job)
    result = data["results"][0]
    assert result["status"] == "unjudged"
    assert result["judge"]["judged_by"] == "basic" and result["judge"]["verdict"] == "unjudged"
    assert result["judge"]["pass"] is False
    assert data["passed"] == 0 and data["unjudged"] == 1
    assert data["verdict"] == "not_ready"


def test_unjudged_runs_are_excluded_from_pass_rate():
    calls = {"n": 0}
    lock = threading.Lock()

    def judge(prompt, criteria, answer, questions):
        with lock:
            calls["n"] += 1
            first = calls["n"] == 1
        if first:
            raise RuntimeError("judge down")
        return {"pass": True, "score": 9, "judged_by": "ai"}

    job = LabRunner().start(Path("x.yaml"), "x.yaml", [Scenario("a", "c")], 2,
                            run_once=lambda *a: {"answer": "ok", "questions": []}, judge=judge)
    data = _wait(job)
    assert sorted(r["status"] for r in data["results"]) == ["passed", "unjudged"]
    assert data["pass_rate"] == 1.0  # 1 passed / 1 graded: the unjudged run is in neither
    assert data["unjudged"] == 1 and data["done"] == 2
    assert data["scenarios"][0]["runs"] == 1 and data["scenarios"][0]["unjudged"] == 1
    assert data["verdict"] == "not_ready"


def test_empty_answer_still_fails_without_judge():
    verdict = workflow_lab._basic_verdict("")
    assert verdict["pass"] is False and verdict["verdict"] == "fail"


# ---------------------------------------------------------------------------- L4: strict judge JSON


class _Conn:
    id = "acc1"
    label = "Acc"


class _Account:
    def current(self):
        return _Conn(), "mid"

    def switch(self, failed_id):
        return False


def test_parse_verdict_takes_first_balanced_object():
    text = 'Here: {"pass": true, "score": 8, "reason": "ok"} and also {"note": 1}'
    assert workflow_lab._parse_verdict(text) == {"pass": True, "score": 8, "reason": "ok"}
    assert workflow_lab._parse_verdict("no json") == {}
    assert workflow_lab._parse_verdict('{"pass": tru') == {}


def test_broken_judge_json_is_retried_once_then_graded(monkeypatch):
    replies = ["Tôi nghĩ là đạt {pass: yes}", '{"pass": true, "score": 9, "reason": "tốt"}']
    seen = []

    def fake_call(conn, model, user, system=""):
        seen.append(user)
        return replies.pop(0)

    monkeypatch.setattr(workflow_lab, "_judge_call", fake_call)
    verdict = workflow_lab._judge("p", "c", "answer", [], account=_Account())
    assert verdict["pass"] is True and verdict["judged_by"] == "ai"
    assert len(seen) == 2 and "JSON" in seen[1]


def test_still_broken_judge_json_leaves_run_unjudged(monkeypatch):
    monkeypatch.setattr(workflow_lab, "_judge_call", lambda *a, **k: "không phải JSON")
    job = LabRunner().start(Path("x.yaml"), "x.yaml", [Scenario("a", "c")], 1,
                            run_once=lambda *a: {"answer": "ok", "questions": []},
                            judge=lambda p, c, a, q: workflow_lab._judge(p, c, a, q, account=_Account()))
    data = _wait(job)
    assert data["results"][0]["status"] == "unjudged" and data["passed"] == 0


def test_empty_run_is_not_recorded_as_ai_judged(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("no judge call for an empty run")

    monkeypatch.setattr(workflow_lab, "_judge_call", boom)
    verdict = workflow_lab._judge("p", "c", "  ", [], account=_Account())
    assert verdict["pass"] is False and verdict["judged_by"] == "basic" and verdict["judge_model"] == ""


# ---------------------------------------------------------------------------- L2: paid gates


def test_auto_answer_channel_refuses_paid_gate():
    channel = AutoAnswerChannel()
    result = channel.request(node_id="Render Approval", task="Tạo video?", metadata={"node_type": "human", "paid": True})
    assert result.text == AUTO_SKIP_PAID and not result.text.startswith("[Automatic answer")
    assert channel.skipped_gates == ["Render Approval"]
    normal = channel.request(node_id="Script Approval", task="Duyệt?", metadata={"node_type": "human"})
    assert normal.text.startswith("[Automatic answer")
    assert channel.skipped_gates == ["Render Approval"]


def test_video_workflow_marks_render_gate_paid():
    data = yaml.safe_load((REPO / "workspace" / "workflows" / "phong_san_xuat_video.yaml").read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in data["graph"]["nodes"]}
    assert nodes["Render Approval"]["config"]["paid"] is True
    report = workflow_lab.static_check_data(data)
    human = next(c for c in report["checks"] if c["id"] == "human_auto")
    assert "Render Approval" not in (human.get("nodes") or [])


class _PaidProvider:
    calls = []

    def __init__(self, config):
        self.config = config

    def create_client(self):
        return None

    def call_model(self, client, conversation, timeline, tool_specs=None, **kwargs):
        _PaidProvider.calls.append(self.config.node_id)
        return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=f"done by {self.config.node_id}"))

    def extract_token_usage(self, response):
        return None


def test_lab_run_never_takes_the_paid_branch(tmp_path, monkeypatch):
    _fake_engine(monkeypatch, _PaidProvider)
    _PaidProvider.calls = []
    approve = r"^\s*((ok|có|co|đồng ý|dong y)\W*)?(tạo|tao)\s+video\b"
    path = tmp_path / "video.yaml"
    path.write_text(yaml.safe_dump({"version": "0.4.0", "graph": {
        "id": "video", "start": ["Writer"], "end": ["Renderer", "Skipped"],
        "nodes": [
            _agent("Writer"),
            {"id": "Render Approval", "type": "human", "config": {"description": "Tạo video (có phí)?", "paid": True}},
            _agent("Renderer"),
            _agent("Skipped"),
        ],
        "edges": [
            {"from": "Writer", "to": "Render Approval"},
            {"from": "Render Approval", "to": "Renderer",
             "condition": {"type": "keyword", "config": {"regex": [approve + r"|\[Automatic answer"]}}},
            {"from": "Render Approval", "to": "Skipped",
             "condition": {"type": "keyword", "config": {"regex": [rf"^(?!{approve}|\[Automatic answer)"]}}},
        ]}}, allow_unicode=True), encoding="utf-8")
    result = workflow_lab._run_once(path, Scenario("Làm video"), threading.Event())
    assert "Renderer" not in _PaidProvider.calls and "Skipped" in _PaidProvider.calls
    assert result["skipped_gates"] == ["Render Approval"]

    seen = []
    monkeypatch.setattr(workflow_lab, "_judge_call", lambda c, m, user, system="": seen.append(user) or
                        '{"pass": false, "score": 3, "reason": "x"}')
    workflow_lab._judge("p", "c", "answer", result["questions"], account=_Account())
    assert "cổng Render Approval bị bỏ qua, không phải đã duyệt" in seen[0]


# ---------------------------------------------------------------------------- L3: cancel stops model calls


class _SlowProvider:
    calls = []
    entered = threading.Event()
    release = threading.Event()

    def __init__(self, config):
        self.config = config

    def create_client(self):
        return None

    def call_model(self, client, conversation, timeline, tool_specs=None, **kwargs):
        _SlowProvider.calls.append(self.config.node_id)
        _SlowProvider.entered.set()
        _SlowProvider.release.wait(10)  # a hung HTTP call that ignores the cancel event
        return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content="x"))

    def extract_token_usage(self, response):
        return None


def test_cancelled_run_makes_no_further_model_call(tmp_path, monkeypatch):
    _fake_engine(monkeypatch, _SlowProvider)
    _SlowProvider.calls = []
    _SlowProvider.entered.clear()
    _SlowProvider.release.clear()
    monkeypatch.setattr(workflow_lab, "TIMEOUT_GRACE_SECONDS", 0.5)
    path = tmp_path / "chain.yaml"
    path.write_text(yaml.safe_dump({"version": "0.4.0", "graph": {
        "id": "chain", "start": ["A"], "end": ["C"],
        "nodes": [_agent("A"), _agent("B"), _agent("C")],
        "edges": [{"from": "A", "to": "B"}, {"from": "B", "to": "C"}]}}), encoding="utf-8")
    job_cancel = threading.Event()
    errors = []

    def run():
        try:
            workflow_lab._run_once(path, Scenario("x"), job_cancel)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    assert _SlowProvider.entered.wait(10)
    job_cancel.set()
    worker.join(15)
    assert errors and "cancel" in str(errors[0]).lower()
    _SlowProvider.release.set()  # the hung call returns after the run was abandoned
    time.sleep(1.0)
    assert _SlowProvider.calls == ["A"]


# ---------------------------------------------------------------------------- L8: stable run ids


def test_every_result_has_a_stable_run_id_across_resume(tmp_path):
    def run_once(path, scenario, cancel):
        if scenario.prompt == "b":
            raise RuntimeError("boom")
        return {"answer": "ok", "questions": []}

    runner = LabRunner(store_dir=tmp_path / "store")
    yaml_path = tmp_path / "wf.yaml"
    yaml_path.write_text("x: 1", encoding="utf-8")
    job = runner.start(yaml_path, "wf.yaml", [Scenario("a", "c"), Scenario("b", "c")], 1, run_once=run_once,
                       judge=lambda p, c, a, q: {"pass": True, "score": 9, "judged_by": "ai"})
    data = _wait(job)
    ids = {r["scenario"]: r["run_id"] for r in data["results"]}
    assert all(ids.values()) and len(set(ids.values())) == 2
    job.status = "cancelled"
    runner._save(job)
    runner._jobs.pop(job.id)
    resumed = runner.resume(job.id, yaml_path, run_once=lambda *a: {"answer": "ok", "questions": []},
                            judge=lambda p, c, a, q: {"pass": True, "score": 9, "judged_by": "ai"})
    again = {r["scenario"]: r["run_id"] for r in _wait(resumed)["results"]}
    assert again[0] == ids[0]  # graded run kept with its id
    assert again[1] and again[1] != ids[1]  # the re-run is a new run


# ---------------------------------------------------------------------------- L9: scenario generator


def test_generator_switches_account_only_on_quota(tmp_path, monkeypatch):
    path = tmp_path / "wf.yaml"
    path.write_text(yaml.safe_dump({"graph": {"id": "wf", "nodes": []}}), encoding="utf-8")
    switched = []

    class Acc:
        def current(self):
            return _Conn(), "mid"

        def switch(self, failed_id):
            switched.append(failed_id)
            return True

    monkeypatch.setattr(workflow_lab, "JudgeAccount", Acc)

    def bad_request(*a, **k):
        raise ValueError("bad request: prompt too long")

    monkeypatch.setattr(workflow_lab, "_judge_call", bad_request)
    with pytest.raises(ValueError):
        workflow_lab.generate_scenarios(path)
    assert switched == []

    replies = []

    def quota_then_ok(*a, **k):
        replies.append(1)
        if len(replies) == 1:
            raise RuntimeError("You've hit your usage limit (429 rate limit)")
        return '[{"name": "n", "prompt": "p", "criteria": "c"}]'

    monkeypatch.setattr(workflow_lab, "_judge_call", quota_then_ok)
    monkeypatch.setattr(workflow_lab, "_out_of_quota", lambda exc: "usage limit" in str(exc))
    assert workflow_lab.generate_scenarios(path)[0]["prompt"] == "p"
    assert switched == ["acc1"]


# ---------------------------------------------------------------------------- L11: to_dict cache


def test_to_dict_recomputes_only_when_results_change(monkeypatch):
    job = LabRunner().start(Path("x.yaml"), "x.yaml", [Scenario("a", "c")], 1,
                            run_once=lambda *a: {"answer": "ok", "questions": []},
                            judge=lambda p, c, a, q: {"pass": True, "score": 9, "judged_by": "ai"})
    _wait(job)
    count = {"n": 0}
    real = workflow_lab.diagnose_job

    def counting(*a, **k):
        count["n"] += 1
        return real(*a, **k)

    first = job.to_dict()
    monkeypatch.setattr(workflow_lab, "diagnose_job", counting)
    job.to_dict()
    job.to_dict()
    assert count["n"] == 0  # nothing changed since the last poll
    job.update_result(job.results[0], note="changed")
    job.to_dict()
    job.to_dict()
    assert count["n"] == 1
    first["results"].clear()  # a caller mutating its copy must not corrupt the cache
    assert job.to_dict()["results"]


def _paid_gate_graph(edge_to_renderer):
    return {"version": "0.4.0", "graph": {
        "id": "video", "start": ["Writer"], "end": ["Renderer"],
        "nodes": [
            _agent("Writer"),
            {"id": "Render Approval", "type": "human", "config": {"description": "Tạo video (có phí)?", "paid": True}},
            _agent("Renderer"),
        ],
        "edges": [{"from": "Writer", "to": "Render Approval"}, edge_to_renderer]}}


def test_static_check_fails_paid_gate_with_unconditional_edge():
    """The skip answer must not be able to flow into the paid step: an unconditional edge out of a paid gate fails."""
    for edge in ({"from": "Render Approval", "to": "Renderer"},
                 {"from": "Render Approval", "to": "Renderer", "condition": "True"},
                 {"from": "Render Approval", "to": "Renderer", "condition": {"type": "function", "config": {"name": "true"}}}):
        report = workflow_lab.static_check_data(_paid_gate_graph(edge))
        human = next(c for c in report["checks"] if c["id"] == "human_auto")
        assert human["status"] == "fail" and "Render Approval" in human["nodes"], edge


def test_lab_run_skipped_paid_gate_does_not_flow_through_unconditional_edge(tmp_path, monkeypatch):
    _fake_engine(monkeypatch, _PaidProvider)
    _PaidProvider.calls = []
    path = tmp_path / "video.yaml"
    path.write_text(yaml.safe_dump(_paid_gate_graph({"from": "Render Approval", "to": "Renderer"}), allow_unicode=True),
                    encoding="utf-8")
    result = workflow_lab._run_once(path, Scenario("Làm video"), threading.Event())
    assert "Renderer" not in _PaidProvider.calls
    assert result["skipped_gates"] == ["Render Approval"]
