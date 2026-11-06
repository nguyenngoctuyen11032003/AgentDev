"""Platform fix: a separate git worktree + brief for a suspected AgentDev bug, behind confirm + password.

Every git operation here runs in a temporary repository; the real checkout is never touched.
"""

import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import lab as lab_route
from agentdev.api.services import platform_fix as pf

JOB = "abcdef0123456789"
REPORT = "## Platform report\nTool `read_file` raised KeyError in the engine."
REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture()
def repo(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "app.py").write_text("print('hi')\n", encoding="utf-8")
    _git(root, "add", "app.py")
    _git(root, "commit", "-q", "-m", "init")
    monkeypatch.setattr(pf, "repo_root", lambda: root)
    return root


@pytest.fixture(autouse=True)
def fresh_guard(monkeypatch):
    monkeypatch.delenv("AGENTDEV_SOURCE_FIX_PASSWORD_HASH", raising=False)
    monkeypatch.delenv("AGENTDEV_PLATFORM_FIX", raising=False)
    monkeypatch.setattr(pf, "_guard", pf.PasswordGuard())


# --- password -----------------------------------------------------------------------------------------------------

def test_default_password_is_accepted_and_wrong_is_rejected():
    guard = pf.PasswordGuard()
    guard.check("AgentDev", JOB)
    with pytest.raises(pf.PlatformFixError) as err:
        guard.check("agentdev", JOB)
    assert (err.value.code, err.value.status_code) == ("bad_password", 403)


def test_plaintext_default_is_not_in_the_source():
    source = Path(pf.__file__).read_text(encoding="utf-8")
    assert '"AgentDev"' not in source and "'AgentDev'" not in source
    assert pf.DEFAULT_PASSWORD_HASH.startswith("pbkdf2_sha256$")


def test_env_override_replaces_the_default(monkeypatch):
    monkeypatch.setenv("AGENTDEV_SOURCE_FIX_PASSWORD_HASH", pf.hash_password("s3cret!", iterations=1000))
    guard = pf.PasswordGuard()
    guard.check("s3cret!", JOB)
    with pytest.raises(pf.PlatformFixError):
        guard.check("AgentDev", JOB)


def test_malformed_override_fails_closed(monkeypatch):
    monkeypatch.setenv("AGENTDEV_SOURCE_FIX_PASSWORD_HASH", "plaintext")
    with pytest.raises(pf.PlatformFixError) as err:
        pf.PasswordGuard().check("plaintext", JOB)
    assert err.value.code == "password_misconfigured"


def test_lockout_after_five_failures_and_unlock_after_300s():
    clock = FakeClock()
    guard = pf.PasswordGuard(clock=clock)
    for _ in range(5):
        with pytest.raises(pf.PlatformFixError) as err:
            guard.check("nope", JOB)
        assert err.value.code == "bad_password"
    with pytest.raises(pf.PlatformFixError) as err:
        guard.check("AgentDev", JOB)  # even the right password is refused while locked
    assert (err.value.code, err.value.status_code) == ("too_many_attempts", 429)
    assert err.value.params["retry_after_s"] > 0
    clock.now += 299
    with pytest.raises(pf.PlatformFixError) as err:
        guard.check("AgentDev", JOB)
    assert err.value.code == "too_many_attempts"
    clock.now += 2
    guard.check("AgentDev", JOB)


def test_success_resets_the_failure_count():
    guard = pf.PasswordGuard(clock=FakeClock())
    for _ in range(4):
        with pytest.raises(pf.PlatformFixError):
            guard.check("nope", JOB)
    guard.check("AgentDev", JOB)
    for _ in range(4):
        with pytest.raises(pf.PlatformFixError) as err:
            guard.check("nope", JOB)
        assert err.value.code == "bad_password"


def test_attempts_are_logged_without_the_password(caplog):
    caplog.set_level(logging.INFO, logger="agentdev.platform_fix")
    guard = pf.PasswordGuard()
    guard.check("AgentDev", JOB)
    with pytest.raises(pf.PlatformFixError):
        guard.check("wrong-Pa55", JOB)
    records = [r for r in caplog.records if r.name == "agentdev.platform_fix"]
    text = "\n".join(r.getMessage() for r in records)
    assert len(records) >= 2 and JOB in text and "success" in text and "fail" in text
    assert "AgentDev" not in text and "wrong-Pa55" not in text


# --- lists --------------------------------------------------------------------------------------------------------

def test_forbidden_paths_exist_and_cover_the_invariants():
    paths = {item["path"] for item in pf.FORBIDDEN}
    for path in paths:
        assert (REPO_ROOT / path).exists(), path
    for must in ("backend/agentdev/utils/human_prompt.py", "backend/tests/test_no_model_api_keys.py",
                 "backend/tests/test_workflow_assistant.py", "backend/agentdev/api/services/workflow_lab.py",
                 "backend/agentdev/api/services/platform_fix.py"):
        assert must in paths


def test_info_lists_steps_gates_and_forbidden(monkeypatch):
    info = pf.info()
    assert info["enabled"] is True
    assert info["forbidden"] == pf.FORBIDDEN and info["gates"] == pf.GATES
    assert any("worktree" in step["text"] for step in info["steps"])
    monkeypatch.setenv("AGENTDEV_PLATFORM_FIX", "0")
    assert pf.info()["enabled"] is False


# --- prepare ------------------------------------------------------------------------------------------------------

def test_prepare_creates_branch_worktree_and_brief_without_touching_the_checkout(repo):
    head = _git(repo, "rev-parse", "HEAD")
    branch_before = _git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    result = pf.prepare(JOB, REPORT, "wf.yaml")
    worktree = Path(result["worktree"])
    assert result["branch"] == "platform-fix/abcdef01"
    assert worktree == repo.parent / "proj-platform-fix-abcdef01"
    brief = Path(result["brief_file"]).read_text(encoding="utf-8")
    assert REPORT in brief and "wf.yaml" in brief
    assert "backend/agentdev/utils/human_prompt.py" in brief and "uv run pytest -q" in brief
    assert "Do not merge" in brief
    assert _git(worktree, "rev-parse", "--abbrev-ref", "HEAD") == "platform-fix/abcdef01"
    assert _git(worktree, "rev-parse", "HEAD") == head
    # the original checkout: same HEAD, same branch, no new or changed files, no commit
    assert _git(repo, "rev-parse", "HEAD") == head
    assert _git(repo, "rev-parse", "--abbrev-ref", "HEAD") == branch_before
    assert _git(repo, "status", "--porcelain") == ""
    assert not (repo / "PLATFORM_FIX.md").exists()
    assert _git(worktree, "log", "--oneline").count("\n") == 0
    assert result["actions"] and result["next_steps"]


def test_prepare_twice_is_already_prepared(repo):
    first = pf.prepare(JOB, REPORT, "wf.yaml")
    with pytest.raises(pf.PlatformFixError) as err:
        pf.prepare(JOB, REPORT, "wf.yaml")
    assert (err.value.code, err.value.status_code) == ("already_prepared", 409)
    assert err.value.params["worktree"] == first["worktree"]


def test_prepare_refuses_an_empty_report(repo):
    with pytest.raises(pf.PlatformFixError) as err:
        pf.prepare(JOB, "   ", "wf.yaml")
    assert (err.value.code, err.value.status_code) == ("no_platform_report", 409)


@pytest.mark.parametrize("bad", ["../../etc", "abc", "ABCDEF0123", "abcdef01/..", "abcdef01\\x"])
def test_prepare_rejects_unsafe_job_ids(repo, bad):
    with pytest.raises(pf.PlatformFixError) as err:
        pf.prepare(bad, REPORT, "wf.yaml")
    assert err.value.code == "bad_job_id"


def test_prepare_without_git_is_git_unavailable(repo, monkeypatch):
    monkeypatch.setattr(pf.shutil, "which", lambda name: None)
    with pytest.raises(pf.PlatformFixError) as err:
        pf.prepare(JOB, REPORT, "wf.yaml")
    assert (err.value.code, err.value.status_code) == ("git_unavailable", 409)


# --- routes -------------------------------------------------------------------------------------------------------

@pytest.fixture()
def client(monkeypatch):
    jobs = {JOB: {"id": JOB, "workflow": "wf.yaml", "platform_report": REPORT},
            "0000000000aa": {"id": "0000000000aa", "workflow": "wf.yaml", "platform_report": ""}}

    class Runner:
        def get(self, job_id):
            data = jobs.get(job_id)
            return None if data is None else SimpleNamespace(to_dict=lambda: data)

    monkeypatch.setattr(lab_route, "get_lab_runner", lambda: Runner())
    app = FastAPI()
    app.include_router(lab_route.router)
    return TestClient(app)


def _post(client, job=JOB, **body):
    return client.post(f"/api/lab/jobs/{job}/platform-fix", json=body)


def test_route_info(client):
    body = client.get("/api/lab/platform-fix/info").json()
    assert set(body) == {"enabled", "forbidden", "gates", "steps"}


def test_route_requires_confirm(client, repo):
    res = _post(client, password="AgentDev", confirm=False)
    assert res.status_code == 400 and res.json()["detail"]["code"] == "confirm_required"


def test_route_bad_password_then_lockout(client, repo):
    res = _post(client, password="x", confirm=True)
    assert res.status_code == 403 and res.json()["detail"]["code"] == "bad_password"
    for _ in range(4):
        _post(client, password="x", confirm=True)
    res = _post(client, password="AgentDev", confirm=True)
    assert res.status_code == 429 and res.json()["detail"]["code"] == "too_many_attempts"


def test_route_unknown_job_and_no_report(client, repo):
    assert _post(client, job="ffffffffffff", password="AgentDev", confirm=True).status_code == 404
    res = _post(client, job="0000000000aa", password="AgentDev", confirm=True)
    assert res.status_code == 409 and res.json()["detail"]["code"] == "no_platform_report"


def test_route_disabled(client, repo, monkeypatch):
    monkeypatch.setenv("AGENTDEV_PLATFORM_FIX", "0")
    res = _post(client, password="AgentDev", confirm=True)
    assert res.status_code == 403 and res.json()["detail"]["code"] == "disabled"


def test_route_prepares_then_conflicts(client, repo):
    res = _post(client, password="AgentDev", confirm=True)
    assert res.status_code == 200
    assert set(res.json()) == {"branch", "worktree", "brief_file", "actions", "next_steps"}
    again = _post(client, password="AgentDev", confirm=True)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "already_prepared"
