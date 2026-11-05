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
