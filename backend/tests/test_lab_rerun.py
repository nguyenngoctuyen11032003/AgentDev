"""Lab: rerun only the failed scenarios of a finished job (cost estimate first, then a before/after compare)."""

import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev import paths
from agentdev.api.routes import lab as lab_route
from agentdev.api.services import workflow_lab
from agentdev.api.services.workflow_lab import LabRunner, Scenario


def _run(seconds=10.0, cost=0.01):
    def run_once(yaml_path, scenario, cancel):
        return {"answer": f"answer to {scenario.prompt}", "questions": [], "seconds": seconds, "tokens": 5,
                "cost_usd": cost, "cost_known": True}
    return run_once


def _judge(passing):
    def judge(prompt, criteria, answer, questions, **kwargs):
        ok = prompt in passing
        return {"pass": ok, "score": 9 if ok else 2, "verdict": "pass" if ok else "fail", "reason": "r",
                "judged_by": "ai", "cost_usd": 0.002, "cost_known": True}
    return judge


def _wait(job):
    deadline = time.monotonic() + 10
    while job.status in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(0.02)
    return job.to_dict()


@pytest.fixture()
def env(tmp_path, monkeypatch):
    store = tmp_path / "lab_jobs"
    store.mkdir()
    (tmp_path / "warehouse").mkdir()
    monkeypatch.setattr(paths, "WAREHOUSE_DIR", tmp_path / "warehouse")
    monkeypatch.setattr(workflow_lab, "_lab_dir", lambda: store)
    runner = LabRunner(store_dir=store)
    monkeypatch.setattr(workflow_lab, "get_lab_runner", lambda: runner)
    monkeypatch.setattr(lab_route, "get_lab_runner", lambda: runner)
    wf = tmp_path / "wf.yaml"
    wf.write_text("x: 1", encoding="utf-8")
    monkeypatch.setattr(lab_route, "_resolve_yaml_path", lambda name: tmp_path / name)
    monkeypatch.setattr(lab_route, "static_check", lambda path: {"status": "ok"})
    app = FastAPI()
    app.include_router(lab_route.router)
    return SimpleNamespace(store=store, runner=runner, wf=wf, client=TestClient(app))


def _source(env, passing=("a",)):
    """Two scenarios x two repeats: ``a`` passes, ``b`` fails (unless listed in ``passing``)."""
    job = env.runner.start(env.wf, "wf.yaml", [Scenario("a", "ca", "A"), Scenario("b", "cb", "B", max_seconds=60)],
                           2, run_once=_run(), judge=_judge(set(passing)))
    data = _wait(job)
    assert data["status"] == "completed"
    return job


def _fake_rerun(env, monkeypatch, run_once, judge):
    original = env.runner.rerun_failed
    monkeypatch.setattr(env.runner, "rerun_failed",
                        lambda *a, **k: original(*a, run_once=run_once, judge=judge, **k))


def test_estimate_counts_failed_scenarios_and_their_average_cost(env):
    job = _source(env)
    res = env.client.get(f"/api/lab/jobs/{job.id}/rerun-failed/estimate")
    assert res.status_code == 200
    body = res.json()
    assert body["scenarios"] == [1]
    assert body["runs"] == 2  # one scenario x two repeats
    # run 0.01 + grading 0.002 per run of scenario "b", times 2 runs
    assert body["estimate_usd"] == pytest.approx(0.024)
    assert body["cost_known"] is True


def test_estimate_is_unknown_when_no_priced_run(env):
    job = env.runner.start(env.wf, "wf.yaml", [Scenario("b", "c")], 1,
                           run_once=lambda *a: {"answer": "x", "questions": [], "cost_known": False},
                           judge=_judge(set()))
    _wait(job)
    body = env.client.get(f"/api/lab/jobs/{job.id}/rerun-failed/estimate").json()
    assert body["scenarios"] == [0] and body["runs"] == 1
    assert body["estimate_usd"] is None and body["cost_known"] is False


def test_rerun_requires_confirm(env):
    job = _source(env)
    res = env.client.post(f"/api/lab/jobs/{job.id}/rerun-failed", json={})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "confirm_required"


def test_nothing_to_rerun_when_every_scenario_passed(env):
    job = _source(env, passing=("a", "b"))
    res = env.client.post(f"/api/lab/jobs/{job.id}/rerun-failed", json={"confirm": True})
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "nothing_to_rerun"
    assert env.client.get(f"/api/lab/jobs/{job.id}/rerun-failed/estimate").json()["scenarios"] == []


def test_unknown_job_is_404(env):
    assert env.client.get("/api/lab/jobs/0123456789ab/rerun-failed/estimate").status_code == 404
    assert env.client.post("/api/lab/jobs/0123456789ab/rerun-failed", json={"confirm": True}).status_code == 404


def test_rerun_runs_only_failed_scenarios_and_compares(env, monkeypatch):
    job = _source(env)
    seen = []

    def run_once(yaml_path, scenario, cancel):
        seen.append(scenario)
        return _run(seconds=20.0)(yaml_path, scenario, cancel)

    _fake_rerun(env, monkeypatch, run_once, _judge({"a", "b"}))
    res = env.client.post(f"/api/lab/jobs/{job.id}/rerun-failed", json={"confirm": True})
    assert res.status_code == 202
    body = res.json()
    assert body["rerun_of"] == job.id
    assert body["rerun_scenarios"] == [1]
    new = env.runner.get(body["id"])
    data = _wait(new)
    assert [s.prompt for s in seen] == ["b", "b"]  # same repeats, only the failed scenario
    assert seen[0].criteria == "cb" and seen[0].max_seconds == 60
    assert data["total"] == 2 and data["pass_rate"] == 1.0
    compare = data["rerun_compare"]
    assert compare["before"] == {"pass_rate": 0.0, "avg_seconds": 10.0, "cost_usd": 0.02, "done": 2}
    assert compare["after"] == {"pass_rate": 1.0, "avg_seconds": 20.0, "cost_usd": 0.02, "done": 2}
    assert set(compare["flags"]) == {"avg_seconds"}  # slower (+100%) is flagged; better pass rate is not


def test_rerun_info_survives_reload(env, monkeypatch):
    job = _source(env)
    new = env.runner.rerun_failed(job.id, env.wf, run_once=_run(), judge=_judge({"b"}))
    _wait(new)
    reloaded = LabRunner(store_dir=env.store).get(new.id).to_dict()
    assert reloaded["rerun_of"] == job.id
    assert reloaded["rerun_scenarios"] == [1]
    assert reloaded["rerun_compare"]["before"]["pass_rate"] == 0.0
    assert reloaded["rerun_compare"]["after"]["pass_rate"] == 1.0
    assert reloaded["rerun_compare"]["flags"] == {}
