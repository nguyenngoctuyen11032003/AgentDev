"""Git checkpoints: a hidden snapshot before a run turn, and an undo that never overwrites the user's work."""

import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev import paths
from agentdev.api.routes import session_outputs as route
from agentdev.api.services import app_preview as ap
from agentdev.api.services import git_checkpoint as gc
from agentdev.api.services import session_outputs
from agentdev.api.services.lab_outputs import LabOutputsError

KEY = "s1"
SID = "0b6c2a8e-1111-2222-3333-444455556666"


def git(root: Path, *args: str) -> str:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    out = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, env={**os.environ, **env}, check=True)
    return out.stdout


def write(root: Path, rel: str, text: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.encode("utf-8"))


@pytest.fixture(autouse=True)
def _flag_default(monkeypatch):
    monkeypatch.delenv("AGENTDEV_GIT_CHECKPOINT", raising=False)


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    git(root, "init", "-q")
    write(root, "a.txt", "one\n")
    write(root, "b.txt", "bee\n")
    write(root, "src/c.txt", "sea\n")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "init")
    return root.resolve()


def state(root: Path) -> dict:
    return {
        "head": git(root, "rev-parse", "HEAD"),
        "branches": git(root, "branch", "--list", "-a"),
        "index": (root / ".git" / "index").read_bytes(),
        "status": git(root, "status", "--porcelain"),
    }


def by_path(result: dict) -> dict:
    return {f["path"]: f for f in result["files"]}


def test_snapshot_changes_nothing_visible(repo):
    write(repo, "a.txt", "uncommitted\n")
    write(repo, "new.txt", "untracked\n")
    git(repo, "add", "a.txt")  # a staged edit must stay staged
    before = state(repo)
    result = gc.begin_turn_at(repo, KEY)
    assert result["status"] == "ok" and result["turn"] == 1
    assert state(repo) == before
    assert (repo / "a.txt").read_text() == "uncommitted\n"
    refs = git(repo, "for-each-ref", "refs/agentdev/").split()
    assert any(r.endswith(f"run-{KEY}/1") for r in refs)
    assert "agentdev" not in git(repo, "branch", "--list", "-a")


def test_undo_restores_run_edits(repo):
    gc.begin_turn_at(repo, KEY)
    write(repo, "a.txt", "changed\n")  # modified
    (repo / "b.txt").unlink()  # deleted
    write(repo, "src/new/d.txt", "created\n")  # created in a new folder
    gc.end_turn_at(repo, KEY)
    listed = gc.changes_at(repo, KEY)
    files = by_path(listed)
    assert {p: f["change"] for p, f in files.items()} == {"a.txt": "modified", "b.txt": "deleted", "src/new/d.txt": "added"}
    assert all(f["state"] == "pending" for f in files.values())
    assert "-one" in files["a.txt"]["diff"] and "+changed" in files["a.txt"]["diff"]
    before = state(repo)
    result = gc.undo_at(repo, KEY)
    assert sorted(result["restored"]) == ["a.txt", "b.txt"] and result["removed"] == ["src/new/d.txt"]
    assert result["conflicts"] == []
    assert (repo / "a.txt").read_text() == "one\n" and (repo / "b.txt").read_text() == "bee\n"
    assert not (repo / "src" / "new").exists()  # empty folder pruned
    assert state(repo)["index"] == before["index"] and state(repo)["head"] == before["head"]
    again = by_path(gc.changes_at(repo, KEY))
    assert all(f["state"] == "reverted" for f in again.values())
    assert gc.undo_at(repo, KEY)["restored"] == []  # idempotent


def test_user_edit_after_run_blocks_that_file_only(repo):
    gc.begin_turn_at(repo, KEY)
    write(repo, "a.txt", "run edit\n")
    write(repo, "b.txt", "run edit b\n")
    gc.end_turn_at(repo, KEY)
    write(repo, "a.txt", "user edit after the run\n")
    files = by_path(gc.changes_at(repo, KEY))
    assert files["a.txt"]["state"] == "conflict" and files["b.txt"]["state"] == "pending"
    result = gc.undo_at(repo, KEY)
    assert result["restored"] == ["b.txt"] and [c["path"] for c in result["conflicts"]] == ["a.txt"]
    assert (repo / "a.txt").read_text() == "user edit after the run\n"
    assert (repo / "b.txt").read_text() == "bee\n"


def test_untracked_file_created_by_run(repo):
    gc.begin_turn_at(repo, KEY)
    write(repo, "keep.txt", "v1\n")
    write(repo, "gone.txt", "v1\n")
    gc.end_turn_at(repo, KEY)
    write(repo, "keep.txt", "user changed\n")
    result = gc.undo_at(repo, KEY)
    assert result["removed"] == ["gone.txt"] and [c["path"] for c in result["conflicts"]] == ["keep.txt"]
    assert (repo / "keep.txt").exists() and not (repo / "gone.txt").exists()


def test_preexisting_user_changes_are_not_attributed_to_the_run(repo):
    write(repo, "a.txt", "user wip\n")
    write(repo, "wip.txt", "wip\n")
    gc.begin_turn_at(repo, KEY)
    write(repo, "b.txt", "run\n")
    gc.end_turn_at(repo, KEY)
    assert list(by_path(gc.changes_at(repo, KEY))) == ["b.txt"]
    gc.undo_at(repo, KEY)
    assert (repo / "a.txt").read_text() == "user wip\n" and (repo / "wip.txt").exists()


def test_undo_subset_and_path_traversal(repo):
    gc.begin_turn_at(repo, KEY)
    write(repo, "a.txt", "x\n")
    write(repo, "b.txt", "y\n")
    gc.end_turn_at(repo, KEY)
    outside = repo.parent / "outside.txt"
    outside.write_text("keep")
    for bad in ("../outside.txt", "/etc/passwd", "a.txt/../../outside.txt", "not-changed.txt"):
        with pytest.raises(LabOutputsError) as err:
            gc.undo_at(repo, KEY, paths=[bad])
        assert err.value.status_code == 400
    assert outside.read_text() == "keep"
    assert gc.undo_at(repo, KEY, paths=["a.txt"])["restored"] == ["a.txt"]
    assert (repo / "b.txt").read_text() == "y\n"


def test_turn_numbers_and_latest_turn_is_listed(repo):
    gc.begin_turn_at(repo, KEY)
    write(repo, "a.txt", "turn1\n")
    gc.end_turn_at(repo, KEY)
    assert gc.begin_turn_at(repo, KEY)["turn"] == 2
    write(repo, "b.txt", "turn2\n")
    gc.end_turn_at(repo, KEY)
    listed = gc.changes_at(repo, KEY)
    assert listed["turn"] == 2 and list(by_path(listed)) == ["b.txt"]


def test_not_git_workspace_is_a_noop(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    write(plain, "a.txt", "x")
    assert gc.begin_turn_at(plain, KEY)["status"] == "not_git"
    assert gc.changes_at(plain, KEY)["status"] == "not_git"
    assert not (plain / ".git").exists()


def test_folder_inside_a_bigger_repo_is_not_snapshotted(repo):
    inner = repo / "src"
    assert gc.begin_turn_at(inner, KEY)["status"] == "not_git"
    assert git(repo, "for-each-ref", "refs/agentdev/") == ""


def test_flag_off_is_a_noop(repo, monkeypatch):
    monkeypatch.setenv("AGENTDEV_GIT_CHECKPOINT", "0")
    assert gc.begin_turn_at(repo, KEY)["status"] == "disabled"
    assert gc.changes_at(repo, KEY)["status"] == "disabled"
    assert git(repo, "for-each-ref", "refs/agentdev/") == ""


def test_no_checkpoint_yet(repo):
    assert gc.changes_at(repo, KEY)["status"] == "no_checkpoint"
    with pytest.raises(LabOutputsError) as err:
        gc.undo_at(repo, KEY)
    assert err.value.status_code == 404


def test_undo_refused_while_running(repo):
    gc.begin_turn_at(repo, KEY)
    write(repo, "a.txt", "x\n")
    with pytest.raises(LabOutputsError) as err:
        gc.undo_at(repo, KEY, running=True)
    assert err.value.status_code == 409
    assert (repo / "a.txt").read_text() == "x\n"


def test_keep_as_branch(repo):
    gc.begin_turn_at(repo, KEY)
    write(repo, "a.txt", "kept\n")
    gc.end_turn_at(repo, KEY)
    head = git(repo, "rev-parse", "HEAD")
    first = gc.keep_branch_at(repo, KEY)
    assert first["branch"] == f"agentdev/run-{KEY}"
    assert git(repo, "show", f"{first['branch']}:a.txt") == "kept\n"
    assert git(repo, "rev-parse", "HEAD") == head and git(repo, "branch", "--show-current").strip() != first["branch"]
    second = gc.keep_branch_at(repo, KEY)
    assert second["branch"] != first["branch"]


def test_hostile_run_id_is_sanitized(repo):
    result = gc.begin_turn_at(repo, "we ird..id:*~^")
    assert result["status"] == "ok"
    git(repo, "check-ref-format", "--allow-onelevel", result["ref"])


def test_crlf_file_roundtrip(repo):
    git(repo, "config", "core.autocrlf", "true")
    write(repo, "w.txt", "l1\r\nl2\r\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "crlf")
    gc.begin_turn_at(repo, KEY)
    write(repo, "w.txt", "l1\r\nl2 edited\r\n")
    gc.end_turn_at(repo, KEY)
    files = by_path(gc.changes_at(repo, KEY))
    assert files["w.txt"]["state"] == "pending"
    gc.undo_at(repo, KEY)
    assert (repo / "w.txt").read_bytes() == b"l1\r\nl2\r\n"


def test_long_diff_is_capped(repo):
    gc.begin_turn_at(repo, KEY)
    write(repo, "big.txt", "".join(f"line {i}\n" for i in range(40_000)))
    gc.end_turn_at(repo, KEY)
    big = by_path(gc.changes_at(repo, KEY))["big.txt"]
    assert big["truncated"] is True and len(big["diff"]) <= gc.MAX_DIFF_CHARS + 200


# ------------------------------------------------------------------------------------------------ routes


@pytest.fixture()
def api(tmp_path, monkeypatch):
    warehouse = tmp_path / "warehouse"
    warehouse.mkdir()
    monkeypatch.setattr(paths, "WAREHOUSE_DIR", warehouse)
    monkeypatch.setattr(ap, "_allowed_root", lambda: warehouse.resolve())
    project = tmp_path / "opened"
    project.mkdir()
    git(project, "init", "-q")
    write(project, "a.txt", "one\n")
    git(project, "add", "-A")
    git(project, "commit", "-q", "-m", "i")
    sessions = {SID: SimpleNamespace(projects=[{"local_path": str(project)}], status=None)}
    monkeypatch.setattr(session_outputs, "session_lookup", lambda sid: sessions.get(sid))
    monkeypatch.setattr(gc, "run_in_progress_for", lambda sid: False)
    app = FastAPI()
    app.include_router(route.router)
    return SimpleNamespace(client=TestClient(app), project=project.resolve())


def test_routes_roundtrip(api):
    gc.begin_turn(SID)
    write(api.project, "a.txt", "two\n")
    gc.end_turn(SID)
    url = f"/api/sessions/{SID}/outputs/changes"
    data = api.client.get(url).json()
    assert data["status"] == "ok" and [f["path"] for f in data["files"]] == ["a.txt"]
    undone = api.client.post(f"{url}/undo", json={}).json()
    assert undone["restored"] == ["a.txt"]
    assert (api.project / "a.txt").read_text() == "one\n"
    bad = api.client.post(f"{url}/undo", json={"paths": ["../x"]})
    assert bad.status_code == 400
    branch = api.client.post(f"{url}/keep-branch").json()
    assert branch["branch"].startswith("agentdev/run-")
