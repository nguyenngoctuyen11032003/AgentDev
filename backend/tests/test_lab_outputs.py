"""Lab outputs: browse, serve, delete the files of a run and clean up old runs, confined to the run folder."""

import json
import os
import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev import paths
from agentdev.api.routes import lab as lab_route
from agentdev.api.services import lab_outputs, workflow_lab
from agentdev.api.services.workflow_lab import LabJob, LabRunner, Scenario


@pytest.fixture()
def env(tmp_path, monkeypatch):
    warehouse = tmp_path / "warehouse"
    warehouse.mkdir()
    store = tmp_path / "lab_jobs"
    store.mkdir()
    monkeypatch.setattr(paths, "WAREHOUSE_DIR", warehouse)
    monkeypatch.setattr(workflow_lab, "_lab_dir", lambda: store)
    runner = LabRunner(store_dir=store)
    monkeypatch.setattr(workflow_lab, "get_lab_runner", lambda: runner)
    app = FastAPI()
    app.include_router(lab_route.router)
    return type("Env", (), {"warehouse": warehouse, "store": store, "runner": runner, "tmp": tmp_path,
                            "client": TestClient(app)})


def _store_job(env, job_id, output_dirs, status="completed"):
    results = [{"scenario": i, "repeat": 1, "status": "passed", "output_dir": str(d) if d else ""}
               for i, d in enumerate(output_dirs)]
    data = {"id": job_id, "workflow": "wf.yaml", "status": status, "results": results, "started_at": time.time()}
    (env.store / f"{job_id}.json").write_text(json.dumps(data), encoding="utf-8")


def _run_dir(env, name="lab_wf_20261105100000_abc123_20261105100000", workspace=True):
    run = env.warehouse / name
    product = run / "code_workspace" if workspace else run
    product.mkdir(parents=True)
    (run / "execution_logs.json").write_text("{}", encoding="utf-8")
    (run / "token_usage_x.json").write_text("{}", encoding="utf-8")
    return run, product


JOB = "0123456789ab"


def test_list_files_kinds_and_skip_dirs(env):
    run, product = _run_dir(env)
    (product / "index.html").write_text("<h1>hi</h1>", encoding="utf-8")
    (product / "README.md").write_text("# x", encoding="utf-8")
    (product / "src").mkdir()
    (product / "src" / "app.js").write_text("1", encoding="utf-8")
    (product / "logo.png").write_bytes(b"\x89PNG")
    (product / "clip.mp4").write_bytes(b"0")
    (product / "song.mp3").write_bytes(b"0")
    (product / "doc.pdf").write_bytes(b"%PDF")
    (product / "notes.txt").write_text("n", encoding="utf-8")
    (product / "blob.bin").write_bytes(b"\0")
    for skipped in ("node_modules/pkg", ".git", ".venv", "__pycache__", ".next/cache", "dist/.vite"):
        (product / skipped).mkdir(parents=True, exist_ok=True)
        (product / skipped / "f.js").write_text("x", encoding="utf-8")
    _store_job(env, JOB, [run])

    data = env.client.get(f"/api/lab/jobs/{JOB}/runs/0/files").json()
    kinds = {f["path"]: f["kind"] for f in data["files"]}
    assert data["available"] is True and Path(data["root"]) == product.resolve()
    assert kinds == {"README.md": "markdown", "blob.bin": "binary", "clip.mp4": "video", "doc.pdf": "pdf",
                     "index.html": "html", "logo.png": "image", "notes.txt": "text", "song.mp3": "audio",
                     "src/app.js": "code"}
    assert data["file_count"] == 9 and data["truncated"] is False
    assert data["project"]["type"] == "static" and data["project"]["can_preview"] is True


def test_graph_dir_without_workspace_hides_internal_files(env):
    run, product = _run_dir(env, workspace=False)
    (product / "report.md").write_text("r", encoding="utf-8")
    _store_job(env, JOB, [run])
    data = env.client.get(f"/api/lab/jobs/{JOB}/runs/0/files").json()
    assert [f["path"] for f in data["files"]] == ["report.md"]


def test_truncated_listing(env, monkeypatch):
    run, product = _run_dir(env)
    for i in range(5):
        (product / f"f{i}.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(lab_outputs, "MAX_FILES", 3)
    _store_job(env, JOB, [run])
    data = env.client.get(f"/api/lab/jobs/{JOB}/runs/0/files").json()
    assert len(data["files"]) == 3 and data["file_count"] == 5 and data["truncated"] is True


def test_missing_dir_and_unsafe_output_dir_are_unavailable(env):
    outside = env.tmp / "elsewhere" / "lab_evil"
    outside.mkdir(parents=True)
    not_lab = env.warehouse / "session_x"
    not_lab.mkdir()
    _store_job(env, JOB, [env.warehouse / "lab_gone", outside, not_lab, None])
    for run in range(4):
        res = env.client.get(f"/api/lab/jobs/{JOB}/runs/{run}/files")
        assert res.status_code == 200 and res.json()["available"] is False
    assert env.client.get(f"/api/lab/jobs/{JOB}/runs/9/files").status_code == 404
    assert env.client.get("/api/lab/jobs/ffffffffffff/runs/0/files").status_code == 404


def test_file_refuses_traversal_and_absolute_paths(env):
    run, product = _run_dir(env)
    (product / "a.txt").write_text("ok", encoding="utf-8")
    secret = env.tmp / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    _store_job(env, JOB, [run])
    url = f"/api/lab/jobs/{JOB}/runs/0/file"
    assert env.client.get(url, params={"path": "a.txt"}).text == "ok"
    for bad in ("../execution_logs.json", "../../secret.txt", str(secret), "/etc/passwd", "C:/Windows/win.ini",
                "..\\..\\secret.txt"):
        assert env.client.get(url, params={"path": bad}).status_code == 400, bad
    assert env.client.get(url, params={"path": "nope.txt"}).status_code == 404
    site = f"/api/lab/jobs/{JOB}/runs/0/site/"
    assert env.client.get(site + "..%2F..%2Fsecret.txt").status_code in (400, 404)


def test_symlink_out_of_the_run_is_refused(env):
    run, product = _run_dir(env)
    secret = env.tmp / "secret.txt"
    secret.write_text("secret", encoding="utf-8")
    try:
        os.symlink(secret, product / "link.txt")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted on this machine")
    _store_job(env, JOB, [run])
    res = env.client.get(f"/api/lab/jobs/{JOB}/runs/0/file", params={"path": "link.txt"})
    assert res.status_code == 400
    listing = env.client.get(f"/api/lab/jobs/{JOB}/runs/0/files").json()
    assert all(f["path"] != "link.txt" for f in listing["files"])


@pytest.mark.skipif(sys.platform != "win32", reason="junctions are a Windows feature")
def test_junction_out_of_the_run_is_refused(env):
    import _winapi

    run, product = _run_dir(env)
    outside = env.tmp / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    _winapi.CreateJunction(str(outside), str(product / "jdir"))
    _store_job(env, JOB, [run])
    res = env.client.get(f"/api/lab/jobs/{JOB}/runs/0/file", params={"path": "jdir/secret.txt"})
    assert res.status_code == 400
    assert env.client.get(f"/api/lab/jobs/{JOB}/runs/0/site/jdir/secret.txt").status_code == 400
    listing = env.client.get(f"/api/lab/jobs/{JOB}/runs/0/files").json()
    assert all(not f["path"].startswith("jdir") for f in listing["files"])


def test_html_and_svg_get_sandbox_csp_and_text_limit(env, monkeypatch):
    run, product = _run_dir(env)
    (product / "index.html").write_text("<script>1</script>", encoding="utf-8")
    (product / "pic.svg").write_text("<svg/>", encoding="utf-8")
    (product / "big.md").write_text("x" * 100, encoding="utf-8")
    (product / "big.png").write_bytes(b"x" * 100)
    _store_job(env, JOB, [run])
    url = f"/api/lab/jobs/{JOB}/runs/0/file"
    res = env.client.get(url, params={"path": "index.html"})
    assert res.headers["content-security-policy"] == "sandbox allow-scripts allow-forms allow-popups"
    assert res.headers["content-type"].startswith("text/html")
    assert "sandbox" in env.client.get(url, params={"path": "pic.svg"}).headers["content-security-policy"]
    site = env.client.get(f"/api/lab/jobs/{JOB}/runs/0/site/")
    assert site.status_code == 200 and "sandbox" in site.headers["content-security-policy"]
    monkeypatch.setattr(lab_outputs, "MAX_TEXT_BYTES", 50)
    assert env.client.get(url, params={"path": "big.md"}).status_code == 413
    assert env.client.get(url, params={"path": "big.png"}).status_code == 200


def test_detect_project_types(tmp_path):
    node = tmp_path / "node"
    node.mkdir()
    (node / "index.html").write_text("x", encoding="utf-8")
    (node / "package.json").write_text(json.dumps({"scripts": {"dev": "vite"},
                                                   "dependencies": {"express": "1"},
                                                   "devDependencies": {"vite": "5"}}), encoding="utf-8")
    project = lab_outputs.detect_project(node)
    assert project["type"] == "node" and project["can_preview"] and "Vite" in project["summary"]

    mono = tmp_path / "mono"
    (mono / "client").mkdir(parents=True)
    (mono / "client" / "package.json").write_text(json.dumps({"scripts": {"dev": "vite"}}), encoding="utf-8")
    assert lab_outputs.detect_project(mono)["entry"] == "client/package.json"

    py = tmp_path / "py"
    py.mkdir()
    (py / "main.py").write_text("from fastapi import FastAPI\n", encoding="utf-8")
    assert lab_outputs.detect_project(py) | {"summary": ""} == {"type": "python", "can_preview": True,
                                                                 "entry": "main.py", "summary": ""}
    script = tmp_path / "script"
    script.mkdir()
    (script / "main.py").write_text("print(1)\n", encoding="utf-8")
    assert lab_outputs.detect_project(script)["can_preview"] is False

    nested = tmp_path / "nested"
    (nested / "site").mkdir(parents=True)
    (nested / "site" / "index.html").write_text("x", encoding="utf-8")
    assert lab_outputs.detect_project(nested)["entry"] == "site/index.html"
    assert lab_outputs.detect_project(tmp_path / "missing")["type"] == "none"


def _live_job(env, run_dirs):
    job = LabJob(id="aaaaaaaaaaaa", workflow="wf.yaml", scenarios=[Scenario("x")], repeats=1, status="running")
    job.results = [{"scenario": 0, "repeat": 1, "status": "running", "output_dir": str(d)} for d in run_dirs]
    env.runner._jobs[job.id] = job
    return job


def test_delete_refused_while_running_then_allowed(env):
    run, product = _run_dir(env)
    (product / "a.txt").write_text("hello", encoding="utf-8")
    job = _live_job(env, [run])
    url = f"/api/lab/jobs/{job.id}/runs/0/outputs"
    assert env.client.delete(url).status_code == 409
    assert run.is_dir()
    job.status = "completed"
    res = env.client.delete(url).json()
    assert res["deleted"] is True and res["freed_bytes"] >= 5 and not run.exists()
    assert env.client.get(f"/api/lab/jobs/{job.id}/runs/0/files").json()["available"] is False
    assert env.client.delete(url).json() == {"deleted": False, "freed_bytes": 0}


def test_delete_also_removes_the_plan_turn_folder_and_stops_previews(env, monkeypatch):
    first, _ = _run_dir(env, "lab_wf_20261105100000_abc123_20261105100000")
    last, _ = _run_dir(env, "lab_wf_20261105100000_abc123_20261105100130")
    other, _ = _run_dir(env, "lab_wf_20261105100000_def456_20261105100000")
    _store_job(env, JOB, [last])
    stopped = []
    fake = type("FakePreviewModule", (), {})()
    fake.get_preview_manager = lambda: type("M", (), {"stop_for_dir": lambda self, p: stopped.append(Path(p)),
                                                       "has_live_preview": lambda self, p: False})()
    monkeypatch.setitem(sys.modules, "agentdev.api.services.app_preview", fake)
    assert env.client.delete(f"/api/lab/jobs/{JOB}/runs/0/outputs").json()["deleted"] is True
    assert not first.exists() and not last.exists() and other.exists()
    assert last.resolve() in stopped


def _age(path, days):
    old = time.time() - days * 86400
    os.utime(path, (old, old))


def test_storage_stats_and_cleanup(env, monkeypatch):
    kept_recent, _ = _run_dir(env, "lab_recent")
    old_ref, _ = _run_dir(env, "lab_old_ref")
    old_orphan, _ = _run_dir(env, "lab_old_orphan")
    old_running, _ = _run_dir(env, "lab_old_running")
    old_preview, _ = _run_dir(env, "lab_old_preview")
    (env.warehouse / "session_other").mkdir()  # not a Lab folder: never counted or touched
    for path in (old_ref, old_orphan, old_running, old_preview):
        _age(path, 40)
    _store_job(env, JOB, [kept_recent, old_ref, old_preview])
    job = _live_job(env, [old_running])
    job.started_at = time.time()

    stats = env.client.get("/api/lab/storage").json()
    assert stats["run_dirs"] == 5 and stats["orphan_dirs"] == 1 and stats["oldest"]
    assert stats["total_bytes"] > 0

    fake = type("FakePreviewModule", (), {})()
    fake.get_preview_manager = lambda: type("M", (), {
        "has_live_preview": lambda self, p: Path(p).resolve().name == "lab_old_preview" or "lab_old_preview" in str(p),
        "stop_for_dir": lambda self, p: None})()
    monkeypatch.setitem(sys.modules, "agentdev.api.services.app_preview", fake)

    res = env.client.post("/api/lab/storage/cleanup", json={"older_than_days": 30, "orphans_only": True}).json()
    assert res["deleted"] == 1 and not old_orphan.exists() and old_ref.exists()

    res = env.client.post("/api/lab/storage/cleanup", json={"older_than_days": 30, "orphans_only": False}).json()
    assert res["deleted"] == 1 and not old_ref.exists()
    assert kept_recent.exists() and old_running.exists() and old_preview.exists()
    assert (env.warehouse / "session_other").exists()
    assert env.client.post("/api/lab/storage/cleanup", json={"older_than_days": -1}).status_code == 422


def test_cleanup_keeps_unrecorded_folders_of_a_running_job(env):
    in_progress, _ = _run_dir(env, "lab_in_progress")
    job = _live_job(env, [])
    job.started_at = time.time() - 60
    res = env.client.post("/api/lab/storage/cleanup", json={"older_than_days": 0, "orphans_only": True}).json()
    assert res["deleted"] == 0 and in_progress.exists()


def test_cleanup_all_deletes_everything_except_running(env):
    # "Delete all" in the UI = older_than_days 0, orphans_only False: recent and referenced folders go too
    recent_ref, _ = _run_dir(env, "lab_recent_ref")
    recent_orphan, _ = _run_dir(env, "lab_recent_orphan")
    live, _ = _run_dir(env, "lab_live")
    for path in (recent_ref, recent_orphan, live):
        _age(path, 0.01)
    _store_job(env, JOB, [recent_ref])
    job = _live_job(env, [live])
    job.started_at = time.time()
    res = env.client.post("/api/lab/storage/cleanup", json={"older_than_days": 0, "orphans_only": False}).json()
    assert res["deleted"] == 2 and not recent_ref.exists() and not recent_orphan.exists()
    assert live.exists()


def test_works_without_preview_module(env, monkeypatch):
    monkeypatch.setitem(sys.modules, "agentdev.api.services.app_preview", None)  # import raises ImportError
    run, _ = _run_dir(env)
    _store_job(env, JOB, [run])
    assert env.client.delete(f"/api/lab/jobs/{JOB}/runs/0/outputs").json()["deleted"] is True


def test_auto_prune_deletes_old_outputs_and_caps_job_records(env, monkeypatch):
    old_run, _ = _run_dir(env, "lab_wf_20261001100000_aaa111_20261001100000")
    new_run, _ = _run_dir(env, "lab_wf_20261105100000_bbb222_20261105100000")
    stale = time.time() - 20 * 86400
    os.utime(old_run, (stale, stale))
    for i in range(3):
        _store_job(env, f"{i:012d}", [old_run if i == 0 else new_run])
        record = env.store / f"{i:012d}.json"
        data = json.loads(record.read_text(encoding="utf-8"))
        data["started_at"] = 1000 + i
        record.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("AGENTDEV_LAB_OUTPUT_RETENTION_DAYS", "14")
    monkeypatch.setenv("AGENTDEV_LAB_JOBS_PER_WORKFLOW", "2")

    result = lab_outputs.auto_prune()

    assert not old_run.exists() and new_run.exists()
    assert result["jobs_deleted"] == 1
    assert sorted(p.name for p in env.store.glob("*.json")) == ["000000000001.json", "000000000002.json"]


def test_auto_prune_zero_keeps_everything(env, monkeypatch):
    old_run, _ = _run_dir(env, "lab_wf_20261001100000_aaa111_20261001100000")
    stale = time.time() - 400 * 86400
    os.utime(old_run, (stale, stale))
    _store_job(env, JOB, [old_run])
    monkeypatch.setenv("AGENTDEV_LAB_OUTPUT_RETENTION_DAYS", "0")
    monkeypatch.setenv("AGENTDEV_LAB_JOBS_PER_WORKFLOW", "0")

    assert lab_outputs.auto_prune() == {"deleted": 0, "freed_bytes": 0, "jobs_deleted": 0}
    assert old_run.exists()


def test_failed_run_keeps_its_output_folder(env, monkeypatch):
    from agentdev.runtime import sdk

    monkeypatch.setattr(sdk, "OUTPUT_ROOT", env.warehouse)

    def failing_turn(yaml_path, session, prompt, cancel_event):
        (env.warehouse / f"{session}_20261105090723" / "code_workspace").mkdir(parents=True)
        raise RuntimeError("agent crashed")

    with pytest.raises(RuntimeError) as info:
        workflow_lab._run_once(Path("wf.yaml"), Scenario(name="s", prompt="p", criteria="c"),
                               __import__("threading").Event(), run_turn=failing_turn)
    folder = Path(info.value.lab_output_dir)
    assert folder.parent == env.warehouse and folder.name.startswith("lab_wf_") and folder.is_dir()


def _job_with_ids(env, entries):
    """entries: (run_id, scenario, repeat, status, output_dir) in the order the job file stores them."""
    results = [{"run_id": rid, "scenario": sc, "repeat": rep, "status": st, "output_dir": str(d) if d else ""}
               for rid, sc, rep, st, d in entries]
    data = {"id": JOB, "workflow": "wf.yaml", "status": "completed", "results": results, "started_at": time.time()}
    (env.store / f"{JOB}.json").write_text(json.dumps(data), encoding="utf-8")


def test_runs_are_addressed_by_run_id_so_resume_does_not_shift_them(env):
    run_a, prod_a = _run_dir(env, "lab_wf_20261105100000_aaaaaa_20261105100000")
    run_b, prod_b = _run_dir(env, "lab_wf_20261105100000_bbbbbb_20261105100000")
    run_c, prod_c = _run_dir(env, "lab_wf_20261105100000_cccccc_20261105100000")
    (prod_b / "b.txt").write_text("b", encoding="utf-8")
    (prod_c / "c.txt").write_text("c", encoding="utf-8")
    # Before resume: scenario 0 errored (run a), scenario 1 passed (run b) -> b is position 1.
    _job_with_ids(env, [("ra", 0, 1, "error", run_a), ("rb", 1, 1, "passed", run_b)])
    files = lambda run: [f["path"] for f in env.client.get(f"/api/lab/jobs/{JOB}/runs/{run}/files").json()["files"]]
    assert files("rb") == files(1) == ["b.txt"]
    assert lab_outputs.canonical_run_key(JOB, 1) == "rb"  # a position maps onto the stable key
    # Resume drops the errored run before re-running it: b slides to position 0, its id does not move.
    _job_with_ids(env, [("rb", 1, 1, "passed", run_b)])
    assert files("rb") == files(0) == ["b.txt"]
    assert env.client.get(f"/api/lab/jobs/{JOB}/runs/1/files").status_code == 404  # the old position is gone
    # The re-run of scenario 0 (run c) sorts first again.
    _job_with_ids(env, [("rb", 1, 1, "passed", run_b), ("rc", 0, 1, "passed", run_c)])
    assert files("rb") == ["b.txt"] and files("rc") == files(0) == ["c.txt"]
    assert lab_outputs.canonical_run_key(JOB, "rb") == "rb"
    gone = env.client.get(f"/api/lab/jobs/{JOB}/runs/ra/files")
    assert gone.status_code == 404 and gone.json()["detail"]["code"] == "lab_run_not_found"
    assert gone.json()["detail"]["message"] == "Run not found in this Lab job"


def test_jobs_without_run_id_keep_position_keys(env, monkeypatch):
    run, product = _run_dir(env)
    (product / "x.txt").write_text("x", encoding="utf-8")
    old = {"status": "completed", "results": [{"scenario": 0, "repeat": 1, "status": "passed", "output_dir": str(run)}]}
    # A job object that reports no run_id at all (the runner may synthesize one; this covers when it does not).
    monkeypatch.setattr(env.runner, "get", lambda job_id: type("Old", (), {"to_dict": lambda self: old})())
    assert lab_outputs.canonical_run_key(JOB, 0) == "0" == lab_outputs.canonical_run_key(JOB, "0")
    assert env.client.get(f"/api/lab/jobs/{JOB}/runs/0/files").json()["available"] is True
    bad = env.client.get(f"/api/lab/jobs/{JOB}/runs/a.b/files")
    assert bad.status_code == 400 and bad.json()["detail"]["code"] == "lab_run_invalid"


def _stored_job_with_window(env, job_id, results, started, finished, workflow="wf.yaml"):
    data = {"id": job_id, "workflow": workflow, "status": "completed", "results": results,
            "started_at": started, "finished_at": finished}
    (env.store / f"{job_id}.json").write_text(json.dumps(data), encoding="utf-8")


def _stamp(epoch):
    from datetime import datetime

    return datetime.fromtimestamp(epoch).strftime("%Y%m%d%H%M%S")


def test_failed_runs_without_folder_are_matched_by_start_order(env):
    t0 = time.time() - 3600
    ok_run, _ = _run_dir(env, f"lab_wf_{_stamp(t0 + 1)}_aaaaaa_{_stamp(t0 + 1)}")
    first_failed, p1 = _run_dir(env, f"lab_wf_{_stamp(t0 + 2)}_bbbbbb_{_stamp(t0 + 2)}")
    second_failed, p2 = _run_dir(env, f"lab_wf_{_stamp(t0 + 60)}_cccccc_{_stamp(t0 + 80)}")
    (p2 / "index.html").write_text("<h1>app</h1>", encoding="utf-8")
    _run_dir(env, f"lab_other_{_stamp(t0 + 3)}_dddddd_{_stamp(t0 + 3)}")  # another workflow: ignored
    results = [{"scenario": 0, "repeat": 1, "status": "passed", "output_dir": str(ok_run)},
               {"scenario": 1, "repeat": 1, "status": "error", "error": "timeout"},
               {"scenario": 2, "repeat": 1, "status": "error", "error": "timeout"}]
    _stored_job_with_window(env, JOB, results, t0, t0 + 900)

    files = env.client.get(f"/api/lab/jobs/{JOB}/runs/2/files").json()
    assert files["available"] is True and files["inferred"] is True and Path(files["root"]) == p2.resolve()
    products = env.client.get(f"/api/lab/jobs/{JOB}/products").json()["runs"]
    assert [p["inferred"] for p in products] == [False, True, True]
    assert products[2]["project"]["type"] == "static" and products[2]["kinds"] == {"html": 1}
    assert lab_outputs.storage_stats()["orphan_dirs"] == 1  # only the other workflow's folder
    assert first_failed.exists()


def test_no_inference_when_ambiguous(env):
    t0 = time.time() - 3600
    _run_dir(env, f"lab_wf_{_stamp(t0 + 2)}_bbbbbb_{_stamp(t0 + 2)}")
    _run_dir(env, f"lab_wf_{_stamp(t0 + 3)}_cccccc_{_stamp(t0 + 3)}")
    _stored_job_with_window(env, JOB, [{"scenario": 0, "repeat": 1, "status": "error"}], t0, t0 + 900)
    assert env.client.get(f"/api/lab/jobs/{JOB}/runs/0/files").json()["available"] is False


def test_workflow_cleanup_keeps_current_and_baseline(env, monkeypatch):
    from agentdev.api.services import lab_cleanup

    t0 = time.time() - 7200
    old_a, _ = _run_dir(env, f"lab_wf_{_stamp(t0)}_aaaaaa_{_stamp(t0)}")
    baseline, _ = _run_dir(env, f"lab_wf_{_stamp(t0 + 100)}_bbbbbb_{_stamp(t0 + 100)}")
    current, _ = _run_dir(env, f"lab_wf_{_stamp(t0 + 200)}_cccccc_{_stamp(t0 + 200)}")
    other, _ = _run_dir(env, f"lab_other_{_stamp(t0)}_dddddd_{_stamp(t0)}")
    for job_id, folder, verdict, start in (("00000000000a", old_a, "not_ready", t0), ("00000000000b", baseline, "ready", t0 + 100),
                                           ("00000000000c", current, "not_ready", t0 + 200)):
        data = {"id": job_id, "workflow": "wf.yaml", "status": "completed", "verdict": verdict, "started_at": start,
                "finished_at": start + 50, "results": [{"scenario": 0, "repeat": 1, "status": "passed",
                                                        "output_dir": str(folder)}]}
        (env.store / f"{job_id}.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(lab_cleanup, "SUGGEST_MIN_RUNS", 1)

    hint = env.client.get("/api/lab/storage/suggestion", params={"workflow": "wf.yaml", "keep_job": "00000000000c"}).json()
    assert hint["suggest"] is True and hint["reclaimable_runs"] == 1 and hint["baseline_job"] == "00000000000b"
    done = env.client.post("/api/lab/storage/cleanup-workflow", json={"workflow": "wf.yaml", "keep_job": "00000000000c"}).json()
    assert done["deleted"] == 1
    assert not old_a.exists() and baseline.exists() and current.exists() and other.exists()
    assert len(list(env.store.glob("*.json"))) == 3  # scores and history stay
