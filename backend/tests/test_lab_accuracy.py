"""Accuracy regressions found by auditing the Lab: hung runs, verdict parsing, false-positive findings."""
import threading
import time
from pathlib import Path

import pytest

from agentdev.api.services import lab_diagnosis, workflow_lab
from agentdev.api.services.workflow_lab import Scenario


def test_hung_run_turn_is_abandoned_after_timeout(monkeypatch):
    # A model call that never returns must not block the worker forever: the watchdog only sets an event.
    monkeypatch.setattr(workflow_lab, "RUN_TIMEOUT_SECONDS", 1)
    monkeypatch.setattr(workflow_lab, "TIMEOUT_GRACE_SECONDS", 1)
    release = threading.Event()

    def hung(path, session, prompt, cancel):
        release.wait(30)  # ignores cancel_event
        return {"answer": "late"}

    started = time.time()
    try:
        try:
            workflow_lab._run_once(Path("wf.yaml"), Scenario("x"), threading.Event(), run_turn=hung)
            raised = False
        except RuntimeError as exc:
            raised = "stopped after" in str(exc)
    finally:
        release.set()
    assert raised and time.time() - started < 10


def test_hung_run_turn_is_abandoned_after_job_cancel(monkeypatch):
    monkeypatch.setattr(workflow_lab, "TIMEOUT_GRACE_SECONDS", 1)
    release = threading.Event()
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()

    def hung(path, session, prompt, cancel_event):
        release.wait(30)
        return {"answer": "late"}

    started = time.time()
    try:
        try:
            workflow_lab._run_once(Path("wf.yaml"), Scenario("x"), cancel, run_turn=hung)
            raised = False
        except RuntimeError:
            raised = True
    finally:
        release.set()
    assert raised and time.time() - started < 10


def test_borderline_rejudge_garbage_leaves_run_unjudged(monkeypatch):
    # Product rule: a pass is never counted without proper grading, so a failed second look is not
    # replaced by the cheap model's borderline verdict.
    calls = []

    class Acc:
        def current(self):
            return type("C", (), {"id": "a", "label": "acc"})(), "mid-model"

    def fake_call(conn, model, user, system=""):
        calls.append(model)
        return '{"pass": true, "score": 7, "reason": "ok"}' if model == "mid-model" else "sorry, no JSON"

    monkeypatch.setattr(workflow_lab, "_judge_call", fake_call)
    import agentdev.runtime.node.agent.account_fallback as af
    monkeypatch.setattr(af, "default_model_for", lambda conn: "strong-model")
    with pytest.raises(workflow_lab.JudgeUnparsable):
        workflow_lab._judge("p", "c", "answer", [], account=Acc())
    assert calls == ["mid-model", "strong-model"]


def test_score_with_denominator_is_not_a_pass():
    assert workflow_lab._rubric_pass({"pass": True, "score": "5/10"}) is False
    assert workflow_lab._rubric_pass({"pass": True, "score": "8/10"}) is True
    assert workflow_lab._rubric_pass({"pass": True, "score": 9}) is True


def test_short_real_task_with_explicit_budget_is_not_overkill():
    run = {"status": "passed", "seconds": 100, "tokens": 1000, "agents": {"a": 1, "b": 1, "c": 1},
           "budget_seconds": 600, "budget_tokens": 150000}
    assert not [f for f in lab_diagnosis.diagnose_run(run, "Viết bài blog về AI") if f["code"] == "overkill"]
    greeting = {"status": "passed", "seconds": 10, "tokens": 1000, "agents": {"a": 1, "b": 1, "c": 1}}
    assert [f for f in lab_diagnosis.diagnose_run(greeting, "chào") if f["code"] == "overkill"]


def test_two_round_review_loop_is_not_flagged():
    # The fix text allows 2 rounds: writer/reviewer then run 3 times, which must not be reported again.
    run = {"status": "passed", "seconds": 10, "tokens": 1,
           "node_runs": [{"node": n, "wall_ms": 1000} for n in ["writer", "reviewer"] * 3]}
    assert not [f for f in lab_diagnosis.diagnose_run(run, "x" * 300) if f["code"] == "loop"]
    run["node_runs"] += [{"node": n, "wall_ms": 1} for n in ["writer", "reviewer"]]
    assert [f for f in lab_diagnosis.diagnose_run(run, "x" * 300) if f["code"] == "loop"]


def test_fix_brief_caps_huge_prompt():
    sc = Scenario("p" * 20000, "c" * 20000, "n")
    run = {"scenario": 0, "repeat": 1, "status": "failed", "error": "boom"}
    brief = lab_diagnosis.build_fix_brief("wf", [run], [sc], [], 0.0, 0.8)
    assert len(brief) < 8000


def test_baseline_found_once_under_concurrency(tmp_path):
    job = workflow_lab.LabJob(id="a" * 12, workflow="wf", scenarios=[], repeats=1, store_dir=tmp_path)
    import json
    (tmp_path / ("b" * 12 + ".json")).write_text(json.dumps(
        {"id": "b" * 12, "workflow": "wf", "status": "completed", "verdict": "ready", "finished_at": 1, "started_at": 1}))
    seen = []
    orig = workflow_lab.list_stored_jobs

    def slow(*a, **k):
        time.sleep(0.2)
        return orig(*a, **k)

    workflow_lab.list_stored_jobs = slow
    try:
        ts = [threading.Thread(target=lambda: seen.append(job._find_baseline())) for _ in range(4)]
        [t.start() for t in ts]
        [t.join() for t in ts]
    finally:
        workflow_lab.list_stored_jobs = orig
    assert all(s is not None for s in seen)
