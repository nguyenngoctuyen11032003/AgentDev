"""Lab: team plan approval (two turns), AI judge without criteria, config check in the verdict."""

import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentdev.api.services import workflow_lab
from agentdev.api.services.workflow_lab import FAIL, PASS, PLAN_APPROVAL, LabRunner, Scenario


@pytest.fixture(autouse=True)
def _lab_store(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow_lab, "_lab_dir", lambda: tmp_path / "lab_jobs")


def _wait(job):
    deadline = time.monotonic() + 20
    while job.status in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(0.02)
    return job.to_dict()


# ---------------------------------------------------------------------------- 1. plan approval


def test_plan_pending_runs_a_second_turn_with_the_approval():
    prompts = []

    def run_turn(path, session, prompt, cancel):
        prompts.append((session, prompt))
        if len(prompts) == 1:
            return {"answer": "Kế hoạch: 1. Dev làm web", "tokens": 100, "cost_usd": 0.01, "agents": {"Lead": 1},
                    "questions": [], "team": [], "exchanges": [],
                    "plan": {"node": "Lead", "summary": "Làm web", "plan": "1. Dev làm web"}}
        return {"answer": "Đã làm xong web", "tokens": 300, "cost_usd": 0.03, "agents": {"Lead": 1, "Dev": 1},
                "questions": [], "team": [{"member": "Dev", "task": "web", "report": "ok"}], "exchanges": [],
                "plan": None, "output_dir": "out"}

    result = workflow_lab._run_once(Path("wf.yaml"), Scenario("Làm web bán hàng"), workflow_lab.threading.Event(),
                                    run_turn=run_turn)
    assert len(prompts) == 2
    assert prompts[0][0] == prompts[1][0]  # same session folder: the work continues in place
    assert prompts[1][1].rstrip().endswith(PLAN_APPROVAL)
    assert "Làm web bán hàng" in prompts[1][1] and "Kế hoạch" in prompts[1][1]
    assert result["answer"] == "Đã làm xong web"
    assert result["plan"] == {"node": "Lead", "summary": "Làm web", "text": "Kế hoạch: 1. Dev làm web"}
    assert result["turns"] == 2 and result["tokens"] == 400 and result["cost_usd"] == 0.04
    assert result["agents"] == {"Lead": 2, "Dev": 1} and result["members"] == ["Dev"]


def test_plan_approval_is_capped_at_two_turns():
    calls = []

    def run_turn(path, session, prompt, cancel):
        calls.append(prompt)
        return {"answer": "Kế hoạch mới", "plan": {"plan": "again"}}

    result = workflow_lab._run_once(Path("wf.yaml"), Scenario("x"), workflow_lab.threading.Event(), run_turn=run_turn)
    assert len(calls) == 2 and result["turns"] == 2


def test_no_plan_runs_a_single_turn():
    calls = []

    def run_turn(path, session, prompt, cancel):
        calls.append(prompt)
        return {"answer": "Xin chào", "tokens": 5, "agents": {"Lead": 1}}

    result = workflow_lab._run_once(Path("wf.yaml"), Scenario("chào"), workflow_lab.threading.Event(), run_turn=run_turn)
    assert calls == ["chào"] and result["turns"] == 1 and "plan" not in result
    assert result["answer"] == "Xin chào"


def test_pending_plan_read_from_global_state():
    executor = SimpleNamespace(_get_execution_context=lambda: SimpleNamespace(
        global_state={"plan_pending": {"node": "Lead", "summary": "s", "plan": "p"}}))
    state = workflow_lab._global_state(executor, None)
    assert workflow_lab._pending_plan(state) == {"node": "Lead", "summary": "s", "plan": "p"}
    assert workflow_lab._pending_plan({}) is None
    broken = SimpleNamespace(_get_execution_context=lambda: (_ for _ in ()).throw(RuntimeError("x")))
    assert workflow_lab._global_state(broken, SimpleNamespace()) == {}


# ---------------------------------------------------------------------------- 2. judge


def test_judge_uses_default_criteria_without_criteria(monkeypatch):
    seen = []
    account = SimpleNamespace(current=lambda: (SimpleNamespace(id="c", label="claude"), "m"))
    monkeypatch.setattr(workflow_lab, "_judge_call",
                        lambda conn, model, user: (seen.append(user), '{"pass": true, "score": 8, "reason": "ok"}')[1])
    verdict = workflow_lab._judge("p", "", "answer", [], account=account)
    assert verdict["judged_by"] == "ai" and verdict["pass"] is True
    assert workflow_lab.DEFAULT_CRITERIA in seen[0]


def test_runner_falls_back_to_basic_when_judge_fails():
    def judge(*args):
        raise RuntimeError("No signed-in account")

    job = LabRunner().start(Path("x.yaml"), "x.yaml", [Scenario("a")], 1,
                            run_once=lambda *a: {"answer": "ok", "questions": []}, judge=judge)
    data = _wait(job)
    result = data["results"][0]
    assert result["status"] == "unjudged" and result["judge"]["judged_by"] == "basic"
    assert "No signed-in account" in result["judge"]["reason"]
    assert data["basic_graded"] == 1 and data["unjudged"] == 1 and data["passed"] == 0


# ---------------------------------------------------------------------------- 3. config check in verdict


def _job(config_status):
    job = LabRunner().start(
        Path("x.yaml"), "x.yaml", [Scenario("a", "c")], 1,
        run_once=lambda *a: {"answer": "ok", "seconds": 2.0, "tokens": 7, "members": ["Dev"], "agents": {"Lead": 1}},
        judge=lambda *a: {"pass": True, "reason": "fine", "judged_by": "ai"}, config_status=config_status)
    return _wait(job)


def test_failed_config_check_means_not_ready():
    data = _job(FAIL)
    assert data["pass_rate"] == 1.0 and data["config_failed"] is True and data["verdict"] == "not_ready"


def test_passing_config_and_runs_is_ready_with_scenario_report():
    data = _job(PASS)
    assert data["verdict"] == "ready" and data["config_failed"] is False
    scenario = data["scenarios"][0]
    assert scenario["seconds"] == 2.0 and scenario["tokens"] == 7 and scenario["members"] == ["Dev", "Lead"]
