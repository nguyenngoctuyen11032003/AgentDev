"""Platform fix: prepare a separate git worktree + brief for a suspected AgentDev platform bug found by the Lab.

The running app never edits its own source: the Lab scores workflows with this very code, so a self-edit could
loosen a gate, the ``paid`` rule or the judge just to make a score pass. This module only:

1. checks an explicit confirm + a password (PBKDF2 hash, constant-time compare, lockout after repeated failures);
2. creates a NEW git worktree on a NEW branch next to the repository, from the current HEAD;
3. writes ``PLATFORM_FIX.md`` (the Lab's platform report, the FORBIDDEN files, the mandatory GATES) inside it.

It never touches the current checkout, never runs a model, never commits, pushes, merges or opens a PR.
See ``docs/adr/0009-platform-fix-loop.md``.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("agentdev.platform_fix")

# PBKDF2-HMAC-SHA256 of the default password. Only the hash lives in code; override with
# AGENTDEV_SOURCE_FIX_PASSWORD_HASH (same format, see ``hash_password``).
DEFAULT_PASSWORD_HASH = (
    "pbkdf2_sha256$240000$5087c0eb8371081451e98c0fefb5d4cc"
    "$a277ea13041f93f6fae9e2523c80a722d5b92ae373e6cba493aab93b39d8c817"
)
PASSWORD_HASH_ENV = "AGENTDEV_SOURCE_FIX_PASSWORD_HASH"
ENABLED_ENV = "AGENTDEV_PLATFORM_FIX"
MAX_FAILURES = 5
LOCK_SECONDS = 300.0
GIT_TIMEOUT_S = 60
MAX_REPORT_CHARS = 200_000
BRIEF_FILE = "PLATFORM_FIX.md"
# Lab job ids are uuid4 hex prefixes. Anything else is refused before it reaches a path or a git argument.
JOB_ID_RE = re.compile(r"^[0-9a-f]{8,64}$")

# Single source of truth: files a platform fix must NOT change (paths relative to the repository root).
# kind: gate | paid | silence | judge | invariant_test | self
FORBIDDEN: List[Dict[str, str]] = [
    {"path": "backend/agentdev/utils/human_prompt.py", "kind": "paid",
     "text": "AutoAnswerChannel and AUTO_SKIP_PAID: automatic answers never approve a paid gate"},
    {"path": "backend/agentdev/entity/configs/node/human.py", "kind": "paid",
     "text": "The `paid: true` flag of a human gate"},
    {"path": "backend/agentdev/runtime/node/executor/human_executor.py", "kind": "gate",
     "text": "Human gate execution (carries the paid flag)"},
    {"path": "backend/agentdev/api/services/prompt_channel.py", "kind": "silence",
     "text": "Human prompts in a run: a timeout is not an approval"},
    {"path": "backend/agentdev/api/services/session_execution.py", "kind": "silence",
     "text": "Waiting for human input and its timeout"},
    {"path": "backend/agentdev/utils/run_mode.py", "kind": "gate",
     "text": "Run modes: which questions and approvals are answered automatically"},
    {"path": "backend/agentdev/runtime/node/agent/verify_gate.py", "kind": "gate",
     "text": "Verification gate before a member's work is accepted"},
    {"path": "backend/agentdev/runtime/edge/conditions/base.py", "kind": "gate",
     "text": "Edge conditions fail closed (a broken condition never starts a paid step)"},
    {"path": "backend/agentdev/api/services/workflow_lab.py", "kind": "judge",
     "text": "Lab runner, judge and scoring"},
    {"path": "backend/agentdev/api/services/lab_diagnosis.py", "kind": "judge",
     "text": "Lab findings, layers and the platform report itself"},
    {"path": "backend/agentdev/api/services/platform_fix.py", "kind": "self",
     "text": "This password / confirm / forbidden-list logic"},
    {"path": "backend/agentdev/api/routes/lab.py", "kind": "self",
     "text": "Lab routes, including the platform-fix route"},
    {"path": "backend/tests/test_no_model_api_keys.py", "kind": "invariant_test",
     "text": "Invariant 1: models run on CLI account sign-in only"},
    {"path": "backend/tests/test_paid_gate_bypass.py", "kind": "invariant_test",
     "text": "Invariants 2-3: silence is not approval, paid gates never auto-approved"},
    {"path": "backend/tests/test_workflow_assistant.py", "kind": "invariant_test",
     "text": "Invariant 4: test_reference_is_compact"},
    {"path": "backend/tests/test_verify_gate.py", "kind": "invariant_test", "text": "Verification gate tests"},
    {"path": "backend/tests/test_plan_gate.py", "kind": "invariant_test", "text": "Plan gate tests"},
    {"path": "backend/tests/test_run_mode.py", "kind": "invariant_test", "text": "Run mode tests"},
    {"path": "backend/tests/test_edge_condition_events.py", "kind": "invariant_test",
     "text": "Fail-closed edge condition tests"},
    {"path": "backend/tests/test_lab_judge_savings.py", "kind": "invariant_test", "text": "Lab judge tests"},
    {"path": "backend/tests/test_platform_fix.py", "kind": "invariant_test", "text": "This feature's tests"},
]

# Checks that must pass before a reviewer merges the platform-fix branch. ``command`` is run by a person
# (or a developer agent) inside the worktree, never by this module.
GATES: List[Dict[str, str]] = [
    {"code": "forbidden_untouched", "command": "git diff --name-only main...HEAD",
     "text": "The diff against main lists none of the FORBIDDEN files"},
    {"code": "full_tests", "command": "cd backend && uv run pytest -q", "text": "All backend tests pass"},
    {"code": "invariant_tests",
     "command": ("cd backend && uv run pytest -q tests/test_no_model_api_keys.py tests/test_paid_gate_bypass.py "
                 "tests/test_workflow_assistant.py::test_reference_is_compact tests/test_verify_gate.py "
                 "tests/test_edge_condition_events.py"),
     "text": "Invariant tests pass, unchanged"},
    {"code": "regression_test", "command": "cd backend && uv run pytest -q tests/<new test>",
     "text": "A new regression test reproduces the bug (red before the fix, green after)"},
    {"code": "bench_engine", "command": "cd backend && uv run python -m scripts.bench_engine",
     "text": "Engine bench (fake model, free) shows no regression"},
    {"code": "lab_before_after", "command": "",
     "text": "Re-run the same Lab scenarios before and after the fix and compare the results"},
    {"code": "human_review", "command": "",
     "text": "A human reviewer reads the diff and merges it; nothing is merged automatically"},
]


class PlatformFixError(ValueError):
    """A refused platform-fix request: ``code`` is the stable id the UI translates."""

    def __init__(self, code: str, message: str, status_code: int = 409,
                 params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.params = dict(params or {})

    def http_detail(self) -> Dict[str, Any]:
        return {"message": str(self), "code": self.code, "params": self.params}


def enabled() -> bool:
    return os.environ.get(ENABLED_ENV, "1").strip().lower() not in ("0", "false", "no", "off")


# --- password -----------------------------------------------------------------------------------------------------

def hash_password(password: str, iterations: int = 240_000, salt: Optional[bytes] = None) -> str:
    """Hash string for ``AGENTDEV_SOURCE_FIX_PASSWORD_HASH``: ``pbkdf2_sha256$<iters>$<salt_hex>$<hash_hex>``."""
    salt = salt if salt is not None else os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def _verify(password: str, encoded: str) -> bool:
    try:
        scheme, iters, salt_hex, hash_hex = encoded.strip().split("$")
        iterations = int(iters)
        salt, expected = bytes.fromhex(salt_hex), bytes.fromhex(hash_hex)
    except (ValueError, AttributeError) as exc:
        raise PlatformFixError("password_misconfigured", "The source-fix password hash is malformed", 500) from exc
    if scheme != "pbkdf2_sha256" or not 1 <= iterations <= 10_000_000 or not salt or not expected:
        raise PlatformFixError("password_misconfigured", "The source-fix password hash is malformed", 500)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=len(expected))
    return hmac.compare_digest(actual, expected)


class PasswordGuard:
    """Password check with an in-memory lockout: ``max_failures`` wrong answers lock it for ``lock_seconds``."""

    def __init__(self, clock: Callable[[], float] = time.monotonic, max_failures: int = MAX_FAILURES,
                 lock_seconds: float = LOCK_SECONDS) -> None:
        self._clock = clock
        self._max = max_failures
        self._lock_seconds = lock_seconds
        self._failures = 0
        self._locked_until = 0.0
        self._mutex = threading.Lock()

    def check(self, password: str, job_id: str) -> None:
        """Return on success; raise ``too_many_attempts`` (429) or ``bad_password`` (403). Never logs the password."""
        with self._mutex:
            now = self._clock()
            if now < self._locked_until:
                wait = int(self._locked_until - now) + 1
                logger.warning("platform_fix attempt job=%s result=locked retry_after_s=%d", job_id, wait)
                raise PlatformFixError("too_many_attempts", "Too many wrong passwords; try again later", 429,
                                       {"retry_after_s": wait})
            if self._locked_until:
                self._locked_until, self._failures = 0.0, 0
            encoded = os.environ.get(PASSWORD_HASH_ENV, "").strip() or DEFAULT_PASSWORD_HASH
            try:
                ok = _verify(str(password or ""), encoded)
            except PlatformFixError:
                logger.error("platform_fix attempt job=%s result=fail reason=password_misconfigured", job_id)
                raise
            if ok:
                self._failures = 0
                logger.info("platform_fix attempt job=%s result=success", job_id)
                return
            self._failures += 1
            if self._failures >= self._max:
                self._locked_until = now + self._lock_seconds
            logger.warning("platform_fix attempt job=%s result=fail failures=%d", job_id, self._failures)
            raise PlatformFixError("bad_password", "Wrong password", 403,
                                   {"attempts_left": max(0, self._max - self._failures)})


_guard = PasswordGuard()


def check_password(password: str, job_id: str) -> None:
    _guard.check(password, job_id)


# --- info ---------------------------------------------------------------------------------------------------------

def steps() -> List[Dict[str, Any]]:
    """What pressing the button does, shown before the password is asked."""
    return [
        {"code": "create_branch", "text": "Create a new git branch platform-fix/<job id> from the current HEAD"},
        {"code": "create_worktree",
         "text": "Create a new git worktree folder <AgentDev folder>-platform-fix-<job id> next to the AgentDev folder"},
        {"code": "write_brief",
         "text": f"Write {BRIEF_FILE} in that worktree: the platform report, forbidden files and required checks"},
        {"code": "no_change", "text": "Nothing else: the running AgentDev checkout is not changed, no model is run, "
                                      "nothing is committed, pushed, merged or opened as a PR"},
    ]


def info() -> Dict[str, Any]:
    return {"enabled": enabled(), "forbidden": FORBIDDEN, "gates": GATES, "steps": steps()}


# --- prepare ------------------------------------------------------------------------------------------------------

def _git(args: List[str], cwd: Path, timeout: int = GIT_TIMEOUT_S) -> subprocess.CompletedProcess:
    exe = shutil.which("git")
    if not exe:
        raise PlatformFixError("git_unavailable", "git is not installed or not on PATH")
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        # No shell; repository hooks are disabled so creating the worktree runs no repository code.
        return subprocess.run([exe, "-c", f"core.hooksPath={os.devnull}", *args], cwd=str(cwd), env=env,
                              capture_output=True, text=True, timeout=timeout, shell=False, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PlatformFixError("git_unavailable", f"git failed: {type(exc).__name__}") from exc


def repo_root() -> Path:
    """Top of the AgentDev repository, found from the backend folder."""
    backend = Path(__file__).resolve().parents[3]
    result = _git(["rev-parse", "--show-toplevel"], backend)
    if result.returncode != 0 or not result.stdout.strip():
        raise PlatformFixError("git_unavailable", "The AgentDev folder is not a git repository")
    return Path(result.stdout.strip()).resolve()


def _brief(job_id: str, report: str, workflow: str, branch: str) -> str:
    forbidden = "\n".join(f"- `{item['path']}` ({item['kind']}): {item['text']}" for item in FORBIDDEN)
    gates = "\n".join(f"- [ ] {g['text']}" + (f": `{g['command']}`" if g["command"] else "") for g in GATES)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"# Platform fix for Lab job {job_id}\n\n"
        f"Prepared {stamp} on branch `{branch}`. Workflow: `{workflow or '-'}`.\n\n"
        "**Do not merge without the user's review.** Nothing here was committed, pushed or merged; "
        "no pull request was opened.\n\n"
        "## Platform report (from the Lab)\n\n"
        f"{report.strip()}\n\n"
        "## Forbidden files (must not change)\n\n"
        "These hold the gates, the `paid` rule, the silence/timeout-is-not-approval rule, the Lab judge and "
        "scoring, and the invariant tests. If the fix seems to need one of them, stop and ask the user.\n\n"
        f"{forbidden}\n\n"
        "## Required checks before merge\n\n"
        f"{gates}\n\n"
        "## Rules\n\n"
        "- Work only in this worktree; the running AgentDev checkout must not change.\n"
        "- Write a failing regression test first, then the smallest fix.\n"
        "- Models run on CLI account sign-in only; no paid steps in tests or benchmarks.\n"
        "- Do not commit, push, merge or open a PR without the user's approval.\n"
    )


_prepare_lock = threading.Lock()


def prepare(job_id: str, report_markdown: str, workflow: str = "") -> Dict[str, Any]:
    """Create branch ``platform-fix/<id8>`` + worktree ``<repo>-platform-fix-<id8>`` and write the brief there."""
    if not isinstance(job_id, str) or not JOB_ID_RE.match(job_id):
        raise PlatformFixError("bad_job_id", "Invalid Lab job id", 400)
    report = (report_markdown or "").strip()
    if not report:
        raise PlatformFixError("no_platform_report", "This Lab job has no platform report")
    report = report[:MAX_REPORT_CHARS]
    id8 = job_id[:8]
    branch = f"platform-fix/{id8}"
    with _prepare_lock:
        root = repo_root()
        worktree = (root.parent / f"{root.name}-platform-fix-{id8}").resolve()
        exists = _git(["rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"], root)
        if worktree.exists() or exists.returncode == 0:
            raise PlatformFixError("already_prepared", "A platform fix for this job was already prepared",
                                   params={"worktree": str(worktree), "branch": branch})
        head = _git(["rev-parse", "HEAD"], root)
        if head.returncode != 0:
            raise PlatformFixError("git_unavailable", "The repository has no commit to branch from")
        head_sha = head.stdout.strip()
        added = _git(["worktree", "add", "-b", branch, str(worktree), head_sha], root, timeout=300)
        if added.returncode != 0:
            logger.error("platform_fix worktree add failed job=%s rc=%s", job_id, added.returncode)
            raise PlatformFixError("git_unavailable", "git could not create the worktree",
                                   params={"stderr": added.stderr.strip()[-500:]})
        brief = worktree / BRIEF_FILE
        brief.write_text(_brief(job_id, report, workflow, branch), encoding="utf-8")
    logger.info("platform_fix prepared job=%s branch=%s worktree=%s", job_id, branch, worktree)
    return {
        "branch": branch,
        "worktree": str(worktree),
        "brief_file": str(brief),
        "actions": [
            {"code": "created_branch", "text": f"Created branch {branch} from {head_sha[:10]}",
             "params": {"branch": branch, "head": head_sha}},
            {"code": "created_worktree", "text": f"Created worktree {worktree}", "params": {"path": str(worktree)}},
            {"code": "wrote_brief", "text": f"Wrote {brief}", "params": {"path": str(brief)}},
            {"code": "no_change", "text": "Did not change the running checkout, run a model, commit, push or merge",
             "params": {}},
        ],
        "next_steps": [
            {"code": "open_worktree", "text": f"Open {worktree} and read {BRIEF_FILE}", "params": {"path": str(worktree)}},
            {"code": "fix_with_test", "text": "Write a failing regression test, then the fix (not in forbidden files)",
             "params": {}},
            {"code": "run_gates", "text": "Run every required check listed in the brief", "params": {}},
            {"code": "review_merge", "text": "Review the diff yourself and merge only if you agree", "params": {}},
            {"code": "cleanup", "text": f"Remove when done: git worktree remove {worktree} && git branch -D {branch}",
             "params": {"path": str(worktree), "branch": branch}},
        ],
    }
