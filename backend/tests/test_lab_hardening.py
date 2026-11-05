"""Lab hardening: one job per workflow, coded errors, job delete, judge choice."""

import json
import threading
import time
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev import paths
from agentdev.api.routes import lab as lab_route
from agentdev.api.services import workflow_lab
from agentdev.api.services.workflow_lab import JudgeAccount, LabRunner, Scenario


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
    return SimpleNamespace(store=store, runner=runner, wf=wf, tmp=tmp_path, client=TestClient(app))


def _blocking_run(gate):
    def run_once(yaml_path, scenario, cancel):
        gate.wait(10)
        return {"status": "passed", "answer": "ok", "seconds": 0.1, "tokens": 1, "cost_usd": 0.0}
    return run_once


def _judge(*a, **k):
    return {"pass": True, "score": 9, "verdict": "pass", "reason": "r", "judged_by": "ai"}


def _wait(job):
    deadline = time.monotonic() + 10
    while job.status in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(0.02)


def test_second_start_for_same_workflow_is_refused_until_first_ends(env):
    gate = threading.Event()
    first = env.runner.start(env.wf, "wf.yaml", [Scenario(prompt="a")], 1, run_once=_blocking_run(gate), judge=_judge)
    with pytest.raises(workflow_lab.LabError) as info:
        env.runner.start(env.wf, "wf.yaml", [Scenario(prompt="b")], 1, run_once=_blocking_run(gate), judge=_judge)
    assert info.value.code == "lab_job_running"
    # another workflow may run in parallel
    other = env.runner.start(env.wf, "other.yaml", [Scenario(prompt="b")], 1, run_once=_blocking_run(gate), judge=_judge)
    gate.set()
    _wait(first)
    _wait(other)
    third = env.runner.start(env.wf, "wf.yaml", [Scenario(prompt="c")], 1, run_once=_blocking_run(gate), judge=_judge)
    _wait(third)


def test_evaluate_route_returns_409_with_code(env, monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr(workflow_lab, "_run_once", _blocking_run(gate))
    orig = LabRunner.start
    monkeypatch.setattr(LabRunner, "start", lambda self, *a, **k: orig(
        self, *a, **{**k, "run_once": _blocking_run(gate), "judge": _judge}))
    body = {"yaml_file": "wf.yaml", "scenarios": [{"prompt": "hi"}]}
    assert env.client.post("/api/lab/evaluate", json=body).status_code == 202
    res = env.client.post("/api/lab/evaluate", json=body)
    gate.set()
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "lab_job_running"


def test_route_errors_carry_codes(env):
    res = env.client.post("/api/lab/evaluate", json={"yaml_file": "wf.yaml", "scenarios": [{"prompt": "  "}]})
    assert res.status_code == 400 and res.json()["detail"]["code"] == "lab_no_scenarios"
    res = env.client.post("/api/lab/check", json={"yaml_file": "missing.yaml"})
    assert res.status_code == 404 and res.json()["detail"]["code"] == "lab_workflow_not_found"
    res = env.client.post("/api/lab/check", json={"yaml_file": ""})
    assert res.status_code == 400 and res.json()["detail"]["code"] == "lab_yaml_required"


def test_resume_errors_carry_codes(env):
    data = {"id": "0123456789ab", "workflow": "wf.yaml", "status": "completed", "results": [], "scenarios": [],
            "started_at": time.time()}
    (env.store / "0123456789ab.json").write_text(json.dumps(data), encoding="utf-8")
    res = env.client.post("/api/lab/jobs/0123456789ab/resume")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "lab_not_resumable"


def test_delete_job_removes_record_and_refuses_running(env):
    data = {"id": "0123456789ab", "workflow": "wf.yaml", "status": "completed", "results": [],
            "started_at": time.time()}
    path = env.store / "0123456789ab.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert env.client.delete("/api/lab/jobs/0123456789ab").status_code == 200
    assert not path.exists()
    assert env.client.delete("/api/lab/jobs/0123456789ab").status_code == 404
    gate = threading.Event()
    job = env.runner.start(env.wf, "wf.yaml", [Scenario(prompt="a")], 1, run_once=_blocking_run(gate), judge=_judge)
    res = env.client.delete(f"/api/lab/jobs/{job.id}")
    gate.set()
    _wait(job)
    assert res.status_code == 409 and res.json()["detail"]["code"] == "lab_job_running"


def _conn(cid, vendor):
    return SimpleNamespace(id=cid, vendor=vendor, label=cid, auth_type="cli")


def _patch_store(monkeypatch, conns, default_id, logged_out=()):
    from agentdev.connections import cli_auth, store

    fake = SimpleNamespace(default_connection=lambda: next(c for c in conns if c.id == default_id),
                           list=lambda: conns)
    monkeypatch.setattr(store, "get_store", lambda: fake)
    monkeypatch.setattr(cli_auth, "detect_cli_recent",
                        lambda vendor, *a, **k: {"installed": True, "logged_in": vendor not in logged_out})


def test_judge_prefers_other_vendor(monkeypatch):
    conns = [_conn("c1", "claude"), _conn("x1", "codex")]
    _patch_store(monkeypatch, conns, "c1")
    assert JudgeAccount()._pick().id == "x1"


def test_judge_skips_logged_out_cli_and_falls_back_to_default(monkeypatch):
    conns = [_conn("c1", "claude"), _conn("x1", "codex")]
    _patch_store(monkeypatch, conns, "c1", logged_out=("codex",))
    assert JudgeAccount()._pick().id == "c1"


def test_history_avg_run_cost_ignores_failed_and_unpriced_runs(env):
    results = [
        {"scenario": 0, "repeat": 1, "status": "passed", "cost_usd": 0.10, "cost_known": True,
         "judge": {"cost_usd": 0.02}},
        {"scenario": 1, "repeat": 1, "status": "failed", "cost_usd": 0.20, "cost_known": True,
         "judge": {"cost_usd": 0.02}},
        {"scenario": 2, "repeat": 1, "status": "error", "cost_usd": 0.0},
        {"scenario": 3, "repeat": 1, "status": "error", "cost_usd": 0.0},
    ]
    data = {"id": "0123456789ab", "workflow": "wf.yaml", "status": "completed", "results": results,
            "started_at": time.time(), "cost_usd": 0.34, "done": 4}
    (env.store / "0123456789ab.json").write_text(json.dumps(data), encoding="utf-8")
    row = env.runner.list_jobs("wf.yaml")[0]
    assert row["avg_run_cost_usd"] == pytest.approx((0.12 + 0.22) / 2)


def test_invalid_yaml_file_component_has_its_own_code(env):
    res = env.client.post("/api/lab/check", json={"yaml_file": "..\evil.yaml"})
    assert res.status_code == 400
    assert res.json()["detail"]["code"] == "lab_yaml_invalid"


def test_delete_job_removes_record_before_outputs_and_reports_failure(env, monkeypatch):
    import pathlib

    data = {"id": "0123456789ab", "workflow": "wf.yaml", "status": "completed", "started_at": time.time(),
            "results": [{"scenario": 0, "repeat": 1, "status": "passed", "run_id": "r1", "output_dir": "x"}]}
    path = env.store / "0123456789ab.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    deleted = []
    monkeypatch.setattr(lab_route.lab_outputs, "delete_run_outputs", lambda *a, **k: deleted.append(a))
    real_unlink = pathlib.Path.unlink

    def failing_unlink(self, *a, **k):
        if self == path:
            raise PermissionError("locked")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "unlink", failing_unlink)
    res = env.client.delete("/api/lab/jobs/0123456789ab")
    assert res.status_code == 500 and res.json()["detail"]["code"] == "lab_job_delete_failed"
    assert deleted == [] and path.exists()  # nothing half-deleted: the outputs are still there
    monkeypatch.setattr(pathlib.Path, "unlink", real_unlink)
    assert env.client.delete("/api/lab/jobs/0123456789ab").status_code == 200
    assert deleted and not path.exists()
