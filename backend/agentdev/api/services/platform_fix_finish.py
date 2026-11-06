"""Finish a platform fix: list the ``platform-fix/*`` worktrees, verify them, then commit + merge into main or discard.

``platform_fix.prepare`` creates the worktree; a developer edits it. This module:

1. lists every worktree on a ``platform-fix/<job id>`` branch at the path ``prepare`` uses, with what changed against
   the merge-base with ``main`` and which FORBIDDEN files were touched;
2. runs the verify gates in the background (forbidden files, backend ``uv sync`` + ``pytest``, frontend
   ``npm ci``/test/lint/build/i18n only when ``frontend/`` changed). Every child is a list-args process without a
   shell, registered with the process registry and killed as a tree on cancel / timeout / shutdown;
3. after an explicit confirm + the platform-fix password, and only when nothing blocks it (a passed verify on the
   current code, no forbidden file, a clean ``main`` checkout), commits the worktree, merges the branch into main
   with ``--no-ff``, removes the worktree and deletes the branch. It never pushes.

See ``docs/adr/0009-platform-fix-loop.md``.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from agentdev.api.services import platform_fix as pf
from agentdev.api.services.platform_fix import BRIEF_FILE, FORBIDDEN, JOB_ID_RE, PlatformFixError
from agentdev.connections.cli_auth import kill_process_tree, new_process_group_kwargs
from agentdev.paths import STORAGE_DIR
from agentdev.utils.process_registry import get_registry
from agentdev.utils.redact import redact_secrets

logger = logging.getLogger("agentdev.platform_fix")

MAIN_BRANCH = "main"
BRANCH_PREFIX = "platform-fix/"
TIMEOUT_ENV = "AGENTDEV_PLATFORM_FIX_TEST_TIMEOUT"
DEFAULT_TIMEOUT_S = 1800
TAIL_LINES = 40
TAIL_CHARS = 4000
REPORT_TAIL_LINES = 15
MAX_MESSAGE_CHARS = 5000
STATE_DIR: Path = Path(STORAGE_DIR) / "platform_fixes"

# Gate commands (list args, no shell). Tests replace them with fast fake commands.
COMMANDS: Dict[str, List[str]] = {
    "backend_sync": ["uv", "sync", "--locked"],  # --locked: verifying must not rewrite uv.lock
    "backend_tests": ["uv", "run", "pytest", "-q"],
    "frontend_install": ["npm", "ci"],
    "frontend_tests": ["npm", "test"],
    "frontend_lint": ["npm", "run", "lint"],
    "frontend_build": ["npm", "run", "build"],
    "frontend_i18n": ["node", "scripts/check-i18n.mjs"],
}
# (code, folder inside the worktree, gate it depends on, runs only when frontend/ changed)
GATE_PLAN: List[Tuple[str, str, Optional[str], bool]] = [
    ("forbidden_untouched", "", None, False),
    ("backend_sync", "backend", None, False),
    ("backend_tests", "backend", "backend_sync", False),
    ("frontend_install", "frontend", None, True),
    ("frontend_tests", "frontend", "frontend_install", True),
    ("frontend_lint", "frontend", "frontend_install", True),
    ("frontend_build", "frontend", "frontend_install", True),
    ("frontend_i18n", "frontend", "frontend_install", True),
]
# Merge refuses on the first of these that applies, in this order.
MERGE_BLOCKERS = ("verify_required", "verify_stale", "forbidden_touched", "brief_committed", "ai_attribution",
                  "main_dirty",
                  "not_on_main", "nothing_to_merge")
_OK_GATE = ("passed", "skipped")
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
# AI attribution a commit on main must not carry. Kept narrow: AgentDev has a "claude" CLI provider, so a subject
# such as "fix(claude provider): ..." or a human co-author is fine; only these lines and identities are not.
_ATTRIBUTION_RE = re.compile(
    r"co-authored-by:.*\b(?:claude|anthropic)\b|generated with \[?claude code|\U0001F916", re.IGNORECASE)
_AI_IDENTITY_RE = re.compile(r"\b(?:claude|anthropic)\b", re.IGNORECASE)

_BLOCKER_TEXT = {
    "verify_required": "Chưa có lần kiểm tra đạt cho code hiện tại",
    "verify_stale": "Code đã đổi sau lần kiểm tra đạt cuối",
    "forbidden_touched": "Có tệp cấm bị sửa",
    "brief_committed": f"{BRIEF_FILE} đã bị commit vào nhánh",
    "ai_attribution": "Có commit ghi Claude/Anthropic là tác giả hoặc đồng tác giả",
    "main_dirty": "Thư mục AgentDev chính có thay đổi chưa commit",
    "not_on_main": f"Thư mục AgentDev chính không ở nhánh {MAIN_BRANCH}",
    "nothing_to_merge": "Chưa có thay đổi nào để merge",
}
_FIX_TEXT = {
    "verify_required": "Bấm **Kiểm tra** để chạy test; nếu có bước lỗi, sửa trong worktree rồi kiểm tra lại.",
    "verify_stale": "Code đã đổi sau lần kiểm tra cuối: chạy **Kiểm tra** lại.",
    "forbidden_touched": ("Hoàn tác các tệp cấm trong worktree (`git checkout main -- <tệp>`); nếu bản sửa thật sự "
                          "cần đổi chúng, dừng lại và hỏi người duyệt."),
    "brief_committed": f"Bỏ {BRIEF_FILE} khỏi nhánh (`git rm --cached {BRIEF_FILE}` rồi commit).",
    "ai_attribution": ("Sửa lại các commit đó trong worktree (`git commit --amend` cho commit cuối, `git rebase -i` "
                       "cho commit cũ hơn): bỏ dòng Co-Authored-By/Claude/🤖 và đặt tác giả theo git config "
                       "(`git commit --amend --reset-author`)."),
    "main_dirty": "Commit hoặc stash các thay đổi đang dở ở thư mục AgentDev chính.",
    "not_on_main": f"Chuyển thư mục AgentDev chính về nhánh `{MAIN_BRANCH}` (`git switch {MAIN_BRANCH}`).",
    "nothing_to_merge": "Sửa code trong worktree trước, hoặc bấm **Bỏ bản sửa** nếu không cần nữa.",
}
_STATUS_VI = {"running": "đang chạy", "passed": "đạt", "failed": "lỗi", "cancelled": "đã huỷ", "timeout": "quá giờ",
              "skipped": "bỏ qua", "pending": "chờ"}


@dataclass
class _Run:
    thread: threading.Thread
    cancel: threading.Event
    proc: Optional[subprocess.Popen] = None


_op_lock = threading.Lock()  # verify start, merge, discard (outer)
_state_lock = threading.Lock()  # verify state in memory + on disk (inner; the worker thread takes only this one)
_states: Dict[str, Dict[str, Any]] = {}
_running: Dict[str, _Run] = {}


def run_id(fix_id: str) -> str:
    return f"platform-fix-{fix_id}"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _timeout_s() -> int:
    try:
        return max(1, int(os.environ.get(TIMEOUT_ENV, "") or DEFAULT_TIMEOUT_S))
    except ValueError:
        return DEFAULT_TIMEOUT_S


def _check_id(fix_id: str) -> None:
    if not isinstance(fix_id, str) or not JOB_ID_RE.match(fix_id):
        raise PlatformFixError("not_found", "Platform fix not found", 404)


def _norm_rel(path: str) -> str:
    return path.lower() if os.name == "nt" else path


def _norm_abs(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _split_z(out: str) -> List[str]:
    return [p for p in out.split("\0") if p]


def _git_ok(args: List[str], cwd: Path, timeout: int = pf.GIT_TIMEOUT_S) -> str:
    result = pf._git(args, cwd, timeout=timeout)
    if result.returncode != 0:
        raise PlatformFixError("git_failed", f"git {args[0]} failed",
                               params={"stderr": redact_secrets(result.stderr.strip()[-500:])})
    return result.stdout


# --- state --------------------------------------------------------------------------------------------------------

def _state_path(fix_id: str) -> Path:
    return Path(STATE_DIR) / f"{fix_id}.json"


def _save_locked(fix_id: str) -> None:
    state = _states.get(fix_id)
    if state is None:
        return
    folder = Path(STATE_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(folder), prefix=f".{fix_id}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, _state_path(fix_id))
    except OSError:
        logger.warning("platform_fix state not saved fix=%s", fix_id, exc_info=True)
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _load_locked(fix_id: str) -> Dict[str, Any]:
    if fix_id in _states:
        return _states[fix_id]
    state: Dict[str, Any] = {"id": fix_id, "verify": None}
    try:
        data = json.loads(_state_path(fix_id).read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("verify"), dict):
            state["verify"] = data["verify"]
    except (OSError, ValueError):
        pass
    _states[fix_id] = state
    verify = state["verify"]
    run = _running.get(fix_id)
    if verify and verify.get("status") == "running" and not (run and run.thread.is_alive()):
        # The server restarted during a verify: its processes are gone, so the verify did not finish.
        verify["status"] = "cancelled"
        verify["finished_at"] = verify.get("finished_at") or _now()
        for gate in verify.get("gates", []):
            if gate.get("status") in ("running", "pending"):
                gate["status"] = "cancelled"
        _save_locked(fix_id)
    return state


def _verify_snapshot(fix_id: str) -> Optional[Dict[str, Any]]:
    with _state_lock:
        verify = _load_locked(fix_id)["verify"]
        return json.loads(json.dumps(verify)) if verify else None


def _delete_state(fix_id: str) -> None:
    with _state_lock:
        _states.pop(fix_id, None)
        try:
            _state_path(fix_id).unlink()
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning("platform_fix state not deleted fix=%s", fix_id, exc_info=True)


def _set_gate(fix_id: str, code: str, **fields: Any) -> None:
    with _state_lock:
        verify = _load_locked(fix_id)["verify"]
        for gate in verify["gates"]:
            if gate["code"] == code:
                gate.update(fields)
        _save_locked(fix_id)


# --- inspect ------------------------------------------------------------------------------------------------------

def _worktrees(root: Path) -> List[Tuple[str, Path]]:
    """``(id, path)`` for every worktree on a ``platform-fix/<id>`` branch at the path ``prepare`` creates."""
    out = _git_ok(["worktree", "list", "--porcelain"], root)
    found: List[Tuple[str, Path]] = []
    for block in re.split(r"\n\s*\n", out.replace("\r\n", "\n")):
        path, branch = None, None
        for line in block.splitlines():
            if line.startswith("worktree "):
                path = line[len("worktree "):]
            elif line.startswith("branch "):
                branch = line[len("branch "):]
        prefix = f"refs/heads/{BRANCH_PREFIX}"
        if not path or not branch or not branch.startswith(prefix):
            continue
        fix_id = branch[len(prefix):]
        if not JOB_ID_RE.match(fix_id):
            continue
        expected = root.parent / f"{root.name}-platform-fix-{fix_id}"
        candidate = Path(path)
        if not candidate.is_dir() or _norm_abs(candidate) != _norm_abs(expected):
            continue
        found.append((fix_id, candidate.resolve()))
    return sorted(found)


def _find(fix_id: str) -> Tuple[Path, Path]:
    _check_id(fix_id)
    root = pf.repo_root()
    for found_id, path in _worktrees(root):
        if found_id == fix_id:
            return root, path
    raise PlatformFixError("not_found", "Platform fix not found", 404)


def _fingerprint(wt: Path, head: str, untracked: List[str]) -> str:
    digest = hashlib.sha256()
    digest.update(head.encode())
    diff = pf._git(["diff", "--binary", "HEAD", "--", ".", f":(exclude){BRIEF_FILE}"], wt, binary=True)
    digest.update(b"\0" + (diff.stdout or b"") + b"\0")
    for rel in sorted(untracked):
        digest.update(rel.encode("utf-8") + b"\0")
        target = wt / rel
        try:
            if target.is_file() and not target.is_symlink():
                digest.update(hashlib.sha256(target.read_bytes()).digest())
            elif target.is_symlink():
                digest.update(os.readlink(target).encode("utf-8", "replace"))
        except OSError:
            digest.update(b"?")
    return digest.hexdigest()


def _attributed_commits(wt: Path, base_sha: str) -> List[str]:
    """Short shas of branch commits whose author/committer name or email or message names Claude/Anthropic."""
    out = _git_ok(["log", "--format=%h%x00%an%n%ae%n%cn%n%ce%n%B%x01", f"{base_sha}..HEAD"], wt)
    found: List[str] = []
    for entry in out.split("\x01"):
        sha, _, rest = entry.strip().partition("\x00")
        lines = rest.split("\n")
        identity, body = lines[:4], lines[4:]  # author name/email, committer name/email, then the message
        if sha and (any(_AI_IDENTITY_RE.search(x) for x in identity)
                    or any(_ATTRIBUTION_RE.search(x) for x in body)):
            found.append(sha)
    return found


def _inspect(root: Path, fix_id: str, wt: Path) -> Dict[str, Any]:
    """The item shown in the UI plus ``_fingerprint`` (internal)."""
    head = _git_ok(["rev-parse", "HEAD"], wt).strip()
    base = pf._git(["merge-base", f"refs/heads/{MAIN_BRANCH}", "HEAD"], wt)
    if base.returncode != 0:
        raise PlatformFixError("no_main", f"No merge-base with {MAIN_BRANCH}", 409, {"branch": MAIN_BRANCH})
    base_sha = base.stdout.strip()
    ahead = int(_git_ok(["rev-list", "--count", f"{base_sha}..HEAD"], wt).strip() or 0)
    committed = _split_z(_git_ok(["diff", "--name-only", "--no-renames", "-z", base_sha, "HEAD"], wt))
    uncommitted = _split_z(_git_ok(["diff", "--name-only", "--no-renames", "-z", "HEAD"], wt))
    untracked = [p for p in _split_z(_git_ok(["ls-files", "--others", "--exclude-standard", "-z"], wt))
                 if p != BRIEF_FILE]
    dirty = sorted(set(p for p in uncommitted + untracked if p != BRIEF_FILE))
    changed = sorted(set(p for p in committed + uncommitted + untracked if p != BRIEF_FILE))
    forbidden = {_norm_rel(item["path"]) for item in FORBIDDEN}
    touched = [p for p in changed if _norm_rel(p) in forbidden]
    fingerprint = _fingerprint(wt, head, untracked)
    verify = _verify_snapshot(fix_id)

    blockers: List[str] = []
    if not verify or verify.get("status") != "passed":
        blockers.append("verify_required")
    elif verify.get("fingerprint") != fingerprint:
        blockers.append("verify_stale")
    if touched:
        blockers.append("forbidden_touched")
    if BRIEF_FILE in committed:
        blockers.append("brief_committed")
    attributed = _attributed_commits(wt, base_sha) if ahead else []
    if attributed:
        blockers.append("ai_attribution")
    if _git_ok(["status", "--porcelain", "--untracked-files=no"], root).strip():
        blockers.append("main_dirty")
    current = pf._git(["symbolic-ref", "--quiet", "--short", "HEAD"], root)
    if current.returncode != 0 or current.stdout.strip() != MAIN_BRANCH:
        blockers.append("not_on_main")
    if ahead == 0 and not dirty:
        blockers.append("nothing_to_merge")
    shortstat = pf._git(["diff", "--shortstat", base_sha, "--", ".", f":(exclude){BRIEF_FILE}"], wt)
    return {
        "id": fix_id,
        "branch": f"{BRANCH_PREFIX}{fix_id}",
        "worktree": str(wt),
        "head": head,
        "base": base_sha,
        "ahead": ahead,
        "dirty_files": len(dirty),
        "changed_files": changed,
        "frontend_changed": any(p.startswith("frontend/") for p in changed),
        "forbidden_touched": touched,
        "ai_attribution_commits": attributed,
        "verify": verify,
        "mergeable": not blockers,
        "blockers": blockers,
        "_fingerprint": fingerprint,
        "_shortstat": shortstat.stdout.strip() if shortstat.returncode == 0 else "",
    }


def _public(item: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in item.items() if not k.startswith("_")}


def list_fixes() -> Dict[str, Any]:
    root = pf.repo_root()
    return {"items": [_public(_inspect(root, fix_id, wt)) for fix_id, wt in _worktrees(root)]}


def get(fix_id: str) -> Dict[str, Any]:
    root, wt = _find(fix_id)
    item = _inspect(root, fix_id, wt)
    return {**_public(item), "report": report(item)}


# --- report -------------------------------------------------------------------------------------------------------

def _summary_line(item: Dict[str, Any]) -> str:
    return f"sửa nền tảng từ Lab job {item['id']}: {len(item['changed_files'])} tệp thay đổi"


def report(item: Dict[str, Any]) -> str:
    """Short markdown, Vietnamese first: done / checks / still failing / how to handle / merge blockers."""
    files = item["changed_files"]
    shown = ", ".join(f"`{p}`" for p in files[:20]) + (f" và {len(files) - 20} tệp khác" if len(files) > 20 else "")
    verify = item["verify"]
    lines = [_summary_line(item)[0].upper() + _summary_line(item)[1:] + ".", "", "## Đã làm", "",
             f"- Nhánh `{item['branch']}`: {item['ahead']} commit, {item['dirty_files']} tệp chưa commit."]
    if item.get("_shortstat"):
        lines.append(f"- Diff so với main: {item['_shortstat']}.")
    lines.append(f"- Tệp: {shown}." if files else "- Chưa có tệp nào thay đổi.")
    lines += ["", "## Kiểm tra", ""]
    if not verify:
        lines.append("- Chưa chạy kiểm tra.")
    else:
        lines.append(f"- Tổng: {_STATUS_VI.get(verify.get('status'), verify.get('status'))}"
                     f" (bắt đầu {verify.get('started_at') or '-'}).")
        for gate in verify.get("gates", []):
            summary = f": {gate['summary']}" if gate.get("summary") else ""
            lines.append(f"- `{gate['code']}`: {_STATUS_VI.get(gate['status'], gate['status'])}{summary}")
    lines += ["", "## Còn lỗi", ""]
    failing = [g for g in (verify or {}).get("gates", []) if g.get("status") in ("failed", "timeout")]
    for gate in failing:
        tail = "\n".join((gate.get("tail") or "").splitlines()[-REPORT_TAIL_LINES:])[-1500:]
        lines.append(f"- `{gate['code']}` ({_STATUS_VI.get(gate['status'], gate['status'])}): {gate.get('summary', '')}")
        if tail:
            fence = pf._fence_for(tail)
            lines += [f"{fence}text", tail, fence]
    if item["forbidden_touched"]:
        lines.append("- Tệp cấm bị sửa: " + ", ".join(f"`{p}`" for p in item["forbidden_touched"]))
    if not failing and not item["forbidden_touched"]:
        lines.append("- Không có.")
    lines += ["", "## Cách xử lý", ""]
    if failing:
        lines.append(f"- Xem các dòng cuối ở trên, sửa trong worktree `{item['worktree']}`, rồi chạy **Kiểm tra** lại.")
    for code in item["blockers"]:
        if not (failing and code == "verify_required"):
            lines.append(f"- {_FIX_TEXT[code]}")
    if not item["blockers"]:
        lines.append("- Sẵn sàng: bấm **Commit + merge vào main** (cần mật khẩu). Sau đó khởi động lại server; "
                     "tự push khi muốn (không bao giờ push tự động).")
    lines += ["", "## Chặn merge", ""]
    lines += [f"- `{code}`: {_BLOCKER_TEXT[code]}"
              + (f" ({', '.join(item['ai_attribution_commits'])})" if code == "ai_attribution" else "")
              for code in item["blockers"]] or ["- Không có."]
    return "\n".join(lines) + "\n"


# --- verify -------------------------------------------------------------------------------------------------------

def _tail(raw: bytes) -> Tuple[str, str]:
    text = _ANSI_RE.sub("", raw.decode("utf-8", errors="replace")).replace("\r\n", "\n")
    lines = [line.rstrip() for line in text.splitlines()]
    tail = redact_secrets("\n".join(lines[-TAIL_LINES:])[-TAIL_CHARS:])
    summary = next((line.strip() for line in reversed(lines) if line.strip()), "")
    return tail, redact_secrets(summary[:300])


def _display(argv: Optional[List[str]]) -> str:
    if not argv:
        return ""
    return redact_secrets(" ".join([Path(argv[0]).name, *argv[1:]]))[:300]


def _child_env() -> Dict[str, str]:
    env = pf.clean_env()
    for key in ("VIRTUAL_ENV", pf.PASSWORD_HASH_ENV):
        env.pop(key, None)
    env["CI"] = "1"  # npm / vitest: non-interactive, no watch mode
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _run_command(fix_id: str, argv: List[str], cwd: Path, run: _Run) -> Tuple[str, str, str]:
    """Run one gate command; return ``(status, summary, tail)``. The tree is killed on cancel / timeout."""
    exe = shutil.which(argv[0])
    if not exe:
        return "failed", f"command not found: {argv[0]}", ""
    if not cwd.is_dir():
        return "failed", f"folder not found: {cwd.name}", ""
    registry = get_registry()
    rid = run_id(fix_id)
    limit = _timeout_s()
    started = time.monotonic()
    with tempfile.TemporaryFile() as sink:
        try:
            proc = subprocess.Popen([exe, *argv[1:]], cwd=str(cwd), env=_child_env(), stdin=subprocess.DEVNULL,
                                    stdout=sink, stderr=subprocess.STDOUT, shell=False, **new_process_group_kwargs())
        except OSError as exc:
            return "failed", f"cannot start {argv[0]}: {type(exc).__name__}", ""
        registry.register(rid, proc, cwd)
        run.proc = proc
        status = ""
        try:
            while True:
                try:
                    proc.wait(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    pass
                if run.cancel.is_set():
                    status = "cancelled"
                elif time.monotonic() - started >= limit:
                    status = "timeout"
                if status:
                    kill_process_tree(proc)
                    break
        finally:
            registry.kill_process(rid, proc)  # the whole tree, also orphans left by a finished command
            run.proc = None
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        sink.seek(0)
        tail, summary = _tail(sink.read())
    if not status:
        status = "passed" if proc.returncode == 0 else "failed"
    if status == "timeout":
        summary = f"timed out after {limit}s"
    elif status == "failed" and not summary:
        summary = f"exit code {proc.returncode}"
    return status, summary, tail


def _worker(fix_id: str, wt: Path, touched: List[str], run: _Run) -> None:
    final = "failed"
    try:
        results: Dict[str, str] = {}
        for code, folder, needs, _frontend_only in GATE_PLAN:
            current = next(g for g in _verify_snapshot(fix_id)["gates"] if g["code"] == code)
            if current["status"] == "skipped":
                results[code] = "skipped"
                continue
            if run.cancel.is_set():
                results[code] = "cancelled"
                _set_gate(fix_id, code, status="cancelled")
                continue
            if needs and results.get(needs) != "passed":
                results[code] = "skipped"
                _set_gate(fix_id, code, status="skipped", summary=f"{needs} did not pass")
                continue
            _set_gate(fix_id, code, status="running")
            if code == "forbidden_untouched":
                status = "failed" if touched else "passed"
                summary = ("forbidden files changed: " + ", ".join(touched)) if touched else "no forbidden file changed"
                tail = ""
            else:
                status, summary, tail = _run_command(fix_id, COMMANDS[code], wt / folder, run)
            results[code] = status
            _set_gate(fix_id, code, status=status, summary=summary, tail=tail)
            logger.info("platform_fix gate fix=%s gate=%s status=%s", fix_id, code, status)
        if run.cancel.is_set():
            final = "cancelled"
        elif all(results.get(code) in _OK_GATE for code, *_ in GATE_PLAN):
            final = "passed"
    except Exception:  # noqa: BLE001 - a broken verify is a failed verify, never a passed one
        logger.exception("platform_fix verify crashed fix=%s", fix_id)
    finally:
        with _state_lock:
            verify = _load_locked(fix_id)["verify"]
            if verify is not None:
                verify["status"] = final
                verify["finished_at"] = _now()
                for gate in verify["gates"]:
                    if gate["status"] in ("running", "pending"):
                        gate["status"] = "cancelled" if final == "cancelled" else "skipped"
                _save_locked(fix_id)
            if _running.get(fix_id) is run:
                del _running[fix_id]
        get_registry().kill_run(run_id(fix_id))
        logger.info("platform_fix verify fix=%s result=%s", fix_id, final)


def start_verify(fix_id: str) -> Dict[str, Any]:
    with _op_lock:
        root, wt = _find(fix_id)
        existing = _running.get(fix_id)
        if existing is not None and existing.thread.is_alive():
            raise PlatformFixError("verify_running", "A verify is already running for this fix")
        item = _inspect(root, fix_id, wt)
        gates = []
        for code, _folder, _needs, frontend_only in GATE_PLAN:
            skipped = frontend_only and not item["frontend_changed"]
            gates.append({"code": code, "status": "skipped" if skipped else "pending",
                          "summary": "frontend/ not changed" if skipped else "", "tail": "",
                          "command": _display(COMMANDS.get(code))})
        verify = {"status": "running", "fingerprint": item["_fingerprint"], "started_at": _now(), "finished_at": None,
                  "frontend_changed": item["frontend_changed"], "gates": gates}
        run = _Run(thread=None, cancel=threading.Event())  # type: ignore[arg-type]
        run.thread = threading.Thread(target=_worker, args=(fix_id, wt, list(item["forbidden_touched"]), run),
                                      name=f"platform-fix-verify-{fix_id[:12]}", daemon=True)
        with _state_lock:
            _load_locked(fix_id)["verify"] = verify
            _save_locked(fix_id)
            _running[fix_id] = run
        run.thread.start()
    logger.info("platform_fix verify started fix=%s frontend=%s", fix_id, item["frontend_changed"])
    return {"verify": _verify_snapshot(fix_id)}


def _stop(fix_id: str, wait_s: float = 0.0) -> bool:
    run = _running.get(fix_id)
    if run is None or not run.thread.is_alive():
        return False
    run.cancel.set()
    get_registry().kill_run(run_id(fix_id))
    proc = run.proc
    if proc is not None and proc.poll() is None:
        kill_process_tree(proc)
    if wait_s:
        run.thread.join(timeout=wait_s)
    return True


def cancel(fix_id: str) -> Dict[str, Any]:
    _check_id(fix_id)
    if not _stop(fix_id):
        raise PlatformFixError("verify_not_running", "No verify is running for this fix")
    logger.info("platform_fix verify cancel fix=%s", fix_id)
    return {"verify": _verify_snapshot(fix_id)}


def shutdown() -> None:
    """Server shutdown: cancel every running verify (its process trees are killed)."""
    for fix_id in list(_running):
        _stop(fix_id, wait_s=10.0)


# --- merge / discard ----------------------------------------------------------------------------------------------

def _commit_message(message: Optional[str], item: Dict[str, Any]) -> str:
    text = str(message or "").replace("\r\n", "\n")[:MAX_MESSAGE_CHARS]
    text = "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)
    kept = [line.rstrip() for line in text.split("\n") if not _ATTRIBUTION_RE.search(line)]
    while kept and not kept[-1]:
        kept.pop()
    while kept and not kept[0]:
        kept.pop(0)
    if not kept:
        kept = [f"fix(platform): {_summary_line(item)}"]
    return "\n".join(kept) + "\n"


def _remove(root: Path, wt: Path, branch: str, force_delete: bool) -> List[Dict[str, Any]]:
    actions: List[Dict[str, Any]] = []
    get_registry().kill_for_folders([wt])
    removed = pf._git(["worktree", "remove", "--force", str(wt)], root, timeout=300)
    if removed.returncode != 0 and wt.exists():
        shutil.rmtree(wt, ignore_errors=True)  # e.g. a long path git could not delete; the path is ours
        pf._git(["worktree", "prune"], root)
    if wt.exists():
        actions.append({"code": "cleanup_failed", "params": {"path": str(wt)}})
    else:
        actions.append({"code": "removed_worktree", "params": {"path": str(wt)}})
    deleted = pf._git(["branch", "-D" if force_delete else "-d", branch], root)
    if deleted.returncode == 0:
        actions.append({"code": "deleted_branch", "params": {"branch": branch}})
    else:
        actions.append({"code": "branch_kept", "params": {"branch": branch,
                                                         "stderr": redact_secrets(deleted.stderr.strip()[-300:])}})
    return actions


def merge(fix_id: str, message: Optional[str] = None) -> Dict[str, Any]:
    with _op_lock:
        root, wt = _find(fix_id)
        item = _inspect(root, fix_id, wt)
        for code in MERGE_BLOCKERS:
            if code in item["blockers"]:
                logger.warning("platform_fix merge fix=%s result=blocked code=%s", fix_id, code)
                params: Dict[str, Any] = {"blockers": item["blockers"]}
                if code == "forbidden_touched":
                    params["files"] = item["forbidden_touched"]
                if code == "ai_attribution":
                    params["commits"] = item["ai_attribution_commits"]
                raise PlatformFixError(code, _BLOCKER_TEXT[code], 409, params)
        branch = item["branch"]
        actions: List[Dict[str, Any]] = []
        commit_sha: Optional[str] = None
        if item["dirty_files"]:
            text = _commit_message(message, item)
            _git_ok([*pf._filter_overrides(wt), "add", "-A"], wt, timeout=300)
            pf._git(["reset", "-q", "--", BRIEF_FILE], wt)
            committed = pf._git(["commit", "-q", "-m", text], wt, timeout=300)
            if committed.returncode != 0:
                pf._git(["reset", "-q"], wt)
                logger.error("platform_fix merge fix=%s result=commit_failed", fix_id)
                raise PlatformFixError("commit_failed", "git commit failed", 409,
                                       {"stderr": redact_secrets(committed.stderr.strip()[-500:])})
            commit_sha = _git_ok(["rev-parse", "HEAD"], wt).strip()
            actions.append({"code": "committed", "params": {"commit": commit_sha, "branch": branch,
                                                            "subject": text.split("\n", 1)[0]}})
        merged = pf._git([*pf._filter_overrides(root), "merge", "--no-ff", "--no-edit", f"refs/heads/{branch}"],
                         root, timeout=300)
        if merged.returncode != 0:
            conflicts = sorted(set(_split_z(pf._git(["diff", "--name-only", "--diff-filter=U", "-z"], root).stdout)))
            if pf._git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], root).returncode == 0:
                pf._git(["merge", "--abort"], root)
            if commit_sha:
                pf._git(["reset", "-q", "--mixed", "HEAD~1"], wt)  # back to the uncommitted state
            logger.warning("platform_fix merge fix=%s result=%s", fix_id,
                           "merge_conflict" if conflicts else "merge_failed")
            if conflicts:
                raise PlatformFixError("merge_conflict", "The branch conflicts with main; nothing was changed", 409,
                                       {"files": conflicts})
            raise PlatformFixError("merge_failed", "git merge failed; nothing was changed", 409,
                                   {"stderr": redact_secrets(merged.stderr.strip()[-500:])})
        merge_sha = _git_ok(["rev-parse", "HEAD"], root).strip()
        actions.append({"code": "merged", "params": {"branch": branch, "into": MAIN_BRANCH, "commit": merge_sha}})
        actions += _remove(root, wt, branch, force_delete=False)
        _delete_state(fix_id)
    logger.info("platform_fix merge fix=%s result=success merge=%s", fix_id, merge_sha)
    next_steps = [{"code": "restart_server", "params": {}},
                  {"code": "push_when_ready", "params": {"branch": MAIN_BRANCH}}]
    if any(a["code"] in ("cleanup_failed", "branch_kept") for a in actions):
        next_steps.append({"code": "manual_cleanup", "params": {"path": str(wt), "branch": branch}})
    return {"commit": commit_sha, "merge_commit": merge_sha, "files": item["changed_files"],
            "actions": actions, "next_steps": next_steps}


def discard(fix_id: str) -> Dict[str, Any]:
    with _op_lock:
        root, wt = _find(fix_id)
        _stop(fix_id, wait_s=15.0)
        actions = _remove(root, wt, f"{BRANCH_PREFIX}{fix_id}", force_delete=True)
        _delete_state(fix_id)
    logger.info("platform_fix discard fix=%s result=%s", fix_id, ",".join(a["code"] for a in actions))
    return {"actions": actions}
