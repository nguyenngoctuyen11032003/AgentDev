"""Finishing a platform fix: list, report, verify (fake gate commands), merge into main, discard.

Every git operation runs in a temporary repository; the real checkout is never touched. Gate commands are replaced
by fast fake Python commands: no real uv / npm / pytest run and no model is called.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import lab as lab_route
from agentdev.api.services import platform_fix as pf
from agentdev.api.services import platform_fix_finish as pff
from agentdev.utils.process_registry import get_registry

JOB = "abcdef0123456789"
JOB2 = "0123456789abcdef"
REPORT = "## Platform report\nTool `read_file` raised KeyError in the engine."
PASSWORD = "AgentDev"
OK = [sys.executable, "-c", "print('3 passed in 0.1s')"]
FAIL = [sys.executable, "-c", "import sys; print('line 1'); print('FAILED test_x - token=abc123'); sys.exit(1)"]
SLEEP = [sys.executable, "-c", "import time; print('start', flush=True); time.sleep(60)"]


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout.strip()


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "dev@example.com")
    _git(root, "config", "user.name", "Dev Person")
    (root / "app.py").write_text("print('hi')\n", encoding="utf-8")
    (root / "backend").mkdir()
    (root / "backend" / "core.py").write_text("x = 1\n", encoding="utf-8")
    (root / "frontend").mkdir()
    (root / "frontend" / "main.js").write_text("export default 1\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "init")
    monkeypatch.setattr(pf, "repo_root", lambda: root)
    return root


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTDEV_SOURCE_FIX_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("AGENTDEV_PLATFORM_FIX", raising=False)
    monkeypatch.delenv("AGENTDEV_PLATFORM_FIX_TEST_TIMEOUT", raising=False)
    monkeypatch.setattr(pf, "_guard", pf.PasswordGuard())
    monkeypatch.setattr(pff, "STATE_DIR", tmp_path / "state")
    monkeypatch.setattr(pff, "COMMANDS", {code: list(OK) for code in pff.COMMANDS})
    pff._states.clear()
    yield
    pff.shutdown()
    for fix_id in list(pff._running):
        pff._running[fix_id].thread.join(timeout=10)
    pff._states.clear()


def _prepare(job=JOB):
    return Path(pf.prepare(job, REPORT, "wf.yaml")["worktree"])


@pytest.fixture()
def fix(repo):
    wt = _prepare()
    (wt / "backend" / "core.py").write_text("x = 2\n", encoding="utf-8")
    return wt


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(lab_route.router)
    return TestClient(app)


def _wait(fix_id, timeout=20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        verify = pff.get(fix_id)["verify"]
        if verify and verify["status"] not in ("running",):
            return verify
        time.sleep(0.05)
    raise AssertionError("verify did not finish")


def _verify(client, fix_id=JOB):
    res = client.post(f"/api/lab/platform-fixes/{fix_id}/verify")
    assert res.status_code == 202, res.text
    return _wait(fix_id)


def _merge(client, fix_id=JOB, **body):
    body = {"password": PASSWORD, "confirm": True, **body}
    return client.post(f"/api/lab/platform-fixes/{fix_id}/merge", json=body)


# --- list / report ------------------------------------------------------------------------------------------------

def test_list_shows_only_platform_fix_worktrees(client, repo, fix):
    _git(repo, "worktree", "add", "-q", "-b", "other", str(repo.parent / "other-wt"))
    body = client.get("/api/lab/platform-fixes").json()
    assert [item["id"] for item in body["items"]] == [JOB]
    item = body["items"][0]
    assert item["branch"] == f"platform-fix/{JOB}"
    assert Path(item["worktree"]).resolve() == fix.resolve()
    assert item["ahead"] == 0 and item["dirty_files"] == 1
    assert item["changed_files"] == ["backend/core.py"]  # PLATFORM_FIX.md never counts
    assert item["forbidden_touched"] == [] and item["verify"] is None
    assert item["mergeable"] is False and "verify_required" in item["blockers"]


def test_list_counts_commits_and_untracked_files(client, repo, fix):
    _git(fix, "commit", "-q", "-am", "fix core")
    (fix / "backend" / "new_test.py").write_text("def test_x(): pass\n", encoding="utf-8")
    item = client.get(f"/api/lab/platform-fixes/{JOB}").json()
    assert item["ahead"] == 1 and item["dirty_files"] == 1
    assert item["changed_files"] == ["backend/core.py", "backend/new_test.py"]


def test_detail_has_a_short_vietnamese_report(client, repo, fix):
    body = client.get(f"/api/lab/platform-fixes/{JOB}").json()
    report = body["report"]
    for heading in ("## Đã làm", "## Kiểm tra", "## Còn lỗi", "## Cách xử lý", "## Chặn merge"):
        assert heading in report
    assert "backend/core.py" in report and "verify_required" in report
    assert len(report) < 6000


def test_unknown_or_invalid_id_is_404(client, repo):
    assert client.get("/api/lab/platform-fixes/ffffffffffff").status_code == 404
    assert client.get("/api/lab/platform-fixes/..%2Fx").status_code == 404
    assert client.post("/api/lab/platform-fixes/NOTHEX!/verify").status_code == 404


# --- verify -------------------------------------------------------------------------------------------------------

def test_verify_runs_backend_gates_only_when_frontend_untouched(client, repo, fix):
    verify = _verify(client)
    assert verify["status"] == "passed" and verify["fingerprint"] and verify["finished_at"]
    status = {g["code"]: g["status"] for g in verify["gates"]}
    assert status["forbidden_untouched"] == "passed"
    assert status["backend_sync"] == status["backend_tests"] == "passed"
    assert all(status[c] == "skipped" for c in status if c.startswith("frontend_"))
    item = pff.get(JOB)
    assert item["mergeable"] is True and item["blockers"] == []


def test_verify_runs_frontend_gates_when_frontend_changed(client, repo, fix):
    (fix / "frontend" / "main.js").write_text("export default 2\n", encoding="utf-8")
    verify = _verify(client)
    status = {g["code"]: g["status"] for g in verify["gates"]}
    for code in ("frontend_install", "frontend_tests", "frontend_lint", "frontend_build", "frontend_i18n"):
        assert status[code] == "passed", code


def test_failing_gate_is_reported_with_a_redacted_tail(client, repo, fix, monkeypatch):
    monkeypatch.setitem(pff.COMMANDS, "backend_tests", list(FAIL))
    verify = _verify(client)
    assert verify["status"] == "failed"
    gate = next(g for g in verify["gates"] if g["code"] == "backend_tests")
    assert gate["status"] == "failed" and "FAILED test_x" in gate["tail"]
    assert "abc123" not in gate["tail"] and "abc123" not in json.dumps(pff.get(JOB))
    report = pff.get(JOB)["report"]
    assert "backend_tests" in report.split("## Còn lỗi")[1]
    assert "verify_required" in pff.get(JOB)["blockers"]


def test_failed_install_skips_the_dependent_tests(client, repo, fix, monkeypatch):
    monkeypatch.setitem(pff.COMMANDS, "backend_sync", list(FAIL))
    status = {g["code"]: g["status"] for g in _verify(client)["gates"]}
    assert status["backend_sync"] == "failed" and status["backend_tests"] == "skipped"


def test_missing_command_fails_the_gate(client, repo, fix, monkeypatch):
    monkeypatch.setitem(pff.COMMANDS, "backend_tests", ["definitely-not-a-command-xyz", "-q"])
    gate = next(g for g in _verify(client)["gates"] if g["code"] == "backend_tests")
    assert gate["status"] == "failed" and "not found" in gate["summary"]


def test_gate_timeout(client, repo, fix, monkeypatch):
    monkeypatch.setenv("AGENTDEV_PLATFORM_FIX_TEST_TIMEOUT", "1")
    monkeypatch.setitem(pff.COMMANDS, "backend_tests", list(SLEEP))
    gate = next(g for g in _verify(client)["gates"] if g["code"] == "backend_tests")
    assert gate["status"] == "timeout"
    assert get_registry().count(pff.run_id(JOB)) == 0


def test_second_verify_while_running_is_409_and_cancel_kills_the_process(client, repo, fix, monkeypatch):
    monkeypatch.setitem(pff.COMMANDS, "backend_sync", list(SLEEP))
    assert client.post(f"/api/lab/platform-fixes/{JOB}/verify").status_code == 202
    deadline = time.monotonic() + 15
    while pff._running[JOB].proc is None and time.monotonic() < deadline:
        time.sleep(0.05)
    proc = pff._running[JOB].proc
    assert proc is not None and proc.poll() is None
    again = client.post(f"/api/lab/platform-fixes/{JOB}/verify")
    assert again.status_code == 409 and again.json()["detail"]["code"] == "verify_running"
    res = client.post(f"/api/lab/platform-fixes/{JOB}/cancel")
    assert res.status_code == 200
    verify = _wait(JOB)
    assert verify["status"] == "cancelled"
    assert proc.poll() is not None
    assert get_registry().count(pff.run_id(JOB)) == 0
    assert {g["status"] for g in verify["gates"] if g["code"] == "backend_tests"} == {"cancelled"}


def test_cancel_without_running_verify_is_409(client, repo, fix):
    res = client.post(f"/api/lab/platform-fixes/{JOB}/cancel")
    assert res.status_code == 409 and res.json()["detail"]["code"] == "verify_not_running"


def test_verify_state_survives_restart_and_running_becomes_cancelled(client, repo, fix):
    _verify(client)
    saved = json.loads((pff.STATE_DIR / f"{JOB}.json").read_text(encoding="utf-8"))
    assert saved["verify"]["status"] == "passed"
    saved["verify"]["status"] = "running"
    (pff.STATE_DIR / f"{JOB}.json").write_text(json.dumps(saved), encoding="utf-8")
    pff._states.clear()  # a restart forgets everything in memory
    assert pff.get(JOB)["verify"]["status"] == "cancelled"


def test_change_after_verify_makes_it_stale(client, repo, fix):
    _verify(client)
    (fix / "backend" / "core.py").write_text("x = 3\n", encoding="utf-8")
    assert "verify_stale" in pff.get(JOB)["blockers"]
    res = _merge(client)
    assert res.status_code == 409 and res.json()["detail"]["code"] == "verify_stale"


def test_new_untracked_file_after_verify_makes_it_stale(client, repo, fix):
    _verify(client)
    (fix / "backend" / "extra.py").write_text("y = 1\n", encoding="utf-8")
    assert "verify_stale" in pff.get(JOB)["blockers"]


# --- merge blockers -----------------------------------------------------------------------------------------------

def test_merge_requires_confirm_then_password(client, repo, fix):
    res = _merge(client, confirm=False)
    assert res.status_code == 400 and res.json()["detail"]["code"] == "confirm_required"
    res = _merge(client, password="wrong")
    assert res.status_code == 403 and res.json()["detail"]["code"] == "bad_password"


def test_wrong_password_locks_out(client, repo, fix):
    for _ in range(5):
        _merge(client, password="wrong")
    res = _merge(client)
    assert res.status_code == 429 and res.json()["detail"]["code"] == "too_many_attempts"
    res = client.post(f"/api/lab/platform-fixes/{JOB}/discard", json={"password": PASSWORD, "confirm": True})
    assert res.status_code == 429


def test_merge_without_verify_is_blocked(client, repo, fix):
    res = _merge(client)
    assert res.status_code == 409 and res.json()["detail"]["code"] == "verify_required"


def test_forbidden_file_blocks_merge(client, repo, fix):
    target = fix / "backend/agentdev/utils/human_prompt.py"
    target.parent.mkdir(parents=True)
    target.write_text("AUTO = True\n", encoding="utf-8")
    verify = _verify(client)
    assert verify["status"] == "failed"
    assert next(g for g in verify["gates"] if g["code"] == "forbidden_untouched")["status"] == "failed"
    item = pff.get(JOB)
    assert item["forbidden_touched"] == ["backend/agentdev/utils/human_prompt.py"]
    assert "forbidden_touched" in item["blockers"]
    assert _merge(client).json()["detail"]["code"] == "verify_required"


def test_forbidden_check_sees_a_rename_away(repo, fix):
    target = repo / "backend/agentdev/utils/human_prompt.py"
    target.parent.mkdir(parents=True)
    target.write_text("AUTO = False\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-q", "-m", "add guarded file")
    wt = _prepare(JOB2)
    _git(wt, "mv", "backend/agentdev/utils/human_prompt.py", "backend/agentdev/utils/moved.py")
    assert pff.get(JOB2)["forbidden_touched"] == ["backend/agentdev/utils/human_prompt.py"]


def test_dirty_main_blocks_merge(client, repo, fix):
    _verify(client)
    (repo / "app.py").write_text("print('dirty')\n", encoding="utf-8")
    res = _merge(client)
    assert res.status_code == 409 and res.json()["detail"]["code"] == "main_dirty"


def test_repo_not_on_main_blocks_merge(client, repo, fix):
    _verify(client)
    _git(repo, "checkout", "-q", "-b", "feature")
    res = _merge(client)
    assert res.status_code == 409 and res.json()["detail"]["code"] == "not_on_main"


def test_nothing_to_merge(client, repo):
    _prepare()
    _verify(client)
    res = _merge(client)
    assert res.status_code == 409 and res.json()["detail"]["code"] == "nothing_to_merge"


# --- merge / discard ----------------------------------------------------------------------------------------------

def test_merge_commits_merges_and_cleans_up(client, repo, fix):
    _git(fix, "commit", "-q", "-am", "fix core")
    (fix / "backend" / "test_new.py").write_text("def test_x(): pass\n", encoding="utf-8")
    _verify(client)
    message = "fix(engine): read_file KeyError\n\nCo-Authored-By: Claude <noreply@anthropic.com>\n🤖 by Claude"
    res = _merge(client, message=message)
    assert res.status_code == 200, res.text
    body = res.json()
    assert set(body) >= {"commit", "merge_commit", "files", "actions", "next_steps"}
    assert body["files"] == ["backend/core.py", "backend/test_new.py"]
    log = _git(repo, "log", "--format=%H%x00%an%x00%ae%x00%cn%x00%B%x01", "-3")
    for entry in filter(None, (e.strip() for e in log.split("\x01"))):
        sha, an, ae, cn, msg = entry.split("\x00")
        assert (an, ae, cn) == ("Dev Person", "dev@example.com", "Dev Person")
        lowered = msg.lower()
        assert "claude" not in lowered and "anthropic" not in lowered and "co-authored-by" not in lowered
    assert _git(repo, "rev-parse", "HEAD") == body["merge_commit"]
    parents = _git(repo, "rev-list", "--parents", "-n", "1", "HEAD").split()
    assert len(parents) == 3  # a real merge commit (--no-ff)
    assert _git(repo, "log", "-1", "--format=%s", body["commit"]) == "fix(engine): read_file KeyError"
    assert (repo / "backend" / "core.py").read_text(encoding="utf-8") == "x = 2\n"
    assert (repo / "backend" / "test_new.py").exists()
    assert not (repo / "PLATFORM_FIX.md").exists()
    assert "PLATFORM_FIX.md" not in _git(repo, "ls-files")
    assert not fix.exists()
    assert _git(repo, "branch", "--list", f"platform-fix/{JOB}") == ""
    assert not (pff.STATE_DIR / f"{JOB}.json").exists()
    assert [s["code"] for s in body["next_steps"]] == ["restart_server", "push_when_ready"]
    codes = [a["code"] for a in body["actions"]]
    assert codes == ["committed", "merged", "removed_worktree", "deleted_branch"]
    assert client.get("/api/lab/platform-fixes").json()["items"] == []


def test_merge_default_message_comes_from_the_report(client, repo, fix):
    _verify(client)
    body = _merge(client).json()
    subject = _git(repo, "log", "-1", "--format=%s", body["commit"])
    assert subject.startswith("fix(platform): ")


def test_merge_conflict_aborts_and_changes_nothing(client, repo, fix):
    _verify(client)
    (repo / "backend" / "core.py").write_text("x = 99\n", encoding="utf-8")
    _git(repo, "commit", "-q", "-am", "main moved on")
    main_head = _git(repo, "rev-parse", "HEAD")
    branch_head = _git(fix, "rev-parse", "HEAD")
    res = _merge(client)
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["code"] == "merge_conflict" and detail["params"]["files"] == ["backend/core.py"]
    assert _git(repo, "rev-parse", "HEAD") == main_head
    assert _git(repo, "status", "--porcelain") == ""
    assert _git(fix, "rev-parse", "HEAD") == branch_head  # the worktree commit was undone
    assert (fix / "backend" / "core.py").read_text(encoding="utf-8") == "x = 2\n"
    assert fix.exists() and _git(repo, "branch", "--list", f"platform-fix/{JOB}")


def test_discard_removes_worktree_branch_and_state(client, repo, fix):
    _git(fix, "commit", "-q", "-am", "unmerged work")
    _verify(client)
    res = client.post(f"/api/lab/platform-fixes/{JOB}/discard", json={"password": PASSWORD, "confirm": False})
    assert res.status_code == 400
    res = client.post(f"/api/lab/platform-fixes/{JOB}/discard", json={"password": PASSWORD, "confirm": True})
    assert res.status_code == 200, res.text
    assert [a["code"] for a in res.json()["actions"]] == ["removed_worktree", "deleted_branch"]
    assert not fix.exists()
    assert _git(repo, "branch", "--list", f"platform-fix/{JOB}") == ""
    assert not (pff.STATE_DIR / f"{JOB}.json").exists()
    assert _git(repo, "log", "--format=%s") == "init"


def test_disabled_feature_refuses_merge(client, repo, fix, monkeypatch):
    monkeypatch.setenv("AGENTDEV_PLATFORM_FIX", "0")
    res = _merge(client)
    assert res.status_code == 403 and res.json()["detail"]["code"] == "disabled"


# --- AI attribution in commits made inside the worktree --------------------------------------------------------------

def test_commit_with_claude_trailer_blocks_merge(client, repo, fix):
    _git(fix, "commit", "-q", "-am", "fix core\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    sha = _git(fix, "rev-parse", "--short", "HEAD")
    _verify(client)
    item = pff.get(JOB)
    assert "ai_attribution" in item["blockers"] and item["ai_attribution_commits"] == [sha]
    assert "ai_attribution" in item["report"].split("## Cách xử lý")[1]
    res = _merge(client)
    assert res.status_code == 409
    detail = res.json()["detail"]
    assert detail["code"] == "ai_attribution" and detail["params"]["commits"] == [sha]
    assert _git(repo, "log", "--format=%s") == "init"


def test_commit_with_anthropic_author_email_blocks_merge(client, repo, fix):
    _git(fix, "-c", "user.email=noreply@anthropic.com", "commit", "-q", "-am", "fix core")
    _verify(client)
    assert "ai_attribution" in pff.get(JOB)["blockers"]


def test_clean_manual_commit_is_mergeable(client, repo, fix):
    _git(fix, "commit", "-q", "-am", "fix core")
    _verify(client)
    item = pff.get(JOB)
    assert item["mergeable"] is True and item["ai_attribution_commits"] == []
    assert _merge(client).status_code == 200


def test_human_co_author_and_claude_provider_subject_do_not_block(client, repo, fix):
    # AgentDev has a claude CLI provider: a subject naming it, or a human co-author, is not AI attribution.
    _git(fix, "commit", "-q", "-am", "fix(claude provider): retry on idle\n\nCo-Authored-By: Lan <lan@example.com>")
    _verify(client)
    item = pff.get(JOB)
    assert "ai_attribution" not in item["blockers"] and item["ai_attribution_commits"] == []


def test_generated_with_claude_code_line_blocks(client, repo, fix):
    _git(fix, "commit", "-q", "-am", "fix core\n\nGenerated with [Claude Code](https://claude.com/claude-code)")
    _verify(client)
    assert "ai_attribution" in pff.get(JOB)["blockers"]


def test_commit_message_keeps_a_human_co_author_line():
    text = pff._commit_message("fix(claude provider): x\n\nCo-Authored-By: Lan <lan@example.com>\n"
                               "Co-Authored-By: Claude <noreply@anthropic.com>", {})
    assert "fix(claude provider): x" in text and "Lan <lan@example.com>" in text
    assert "noreply@anthropic.com" not in text
