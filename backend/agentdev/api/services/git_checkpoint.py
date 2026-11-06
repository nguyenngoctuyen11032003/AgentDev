"""Git checkpoints: undo what a run edited in a git workspace, without touching the user's own work.

See docs/adr/0005-git-checkpoints.md. Everything here uses git plumbing against a temporary index, so HEAD, branches,
the real index and the working tree are only ever changed by an explicit undo, and an undo only restores files that
still hold exactly what the run left (a file the user edited afterwards is reported, never overwritten).

``*_at`` functions take the workspace folder and a run key; the session wrappers resolve the folder like the
"Sản phẩm" routes do. ``begin_turn`` / ``end_turn`` never raise: a failed snapshot must not fail a run.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Any

from agentdev.api.services import session_outputs
from agentdev.api.services.lab_outputs import LabOutputsError
from agentdev.utils.workspace_paths import is_link

logger = logging.getLogger(__name__)

FLAG = "AGENTDEV_GIT_CHECKPOINT"
REF_ROOT = "refs/agentdev"
GIT_TIMEOUT_S = 30
SNAPSHOT_TIMEOUT_S = 120  # `git add -A` over a big untracked tree
MAX_FILES = 200
MAX_DIFF_FILES = 60
MAX_DIFF_CHARS = 20_000
PATH_CHUNK = 80  # paths per git call (Windows command line limit)
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_SAFE_KEY = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


class GitUnavailable(Exception):
    """A git call failed; ``str()`` is a short reason for the UI."""


def enabled() -> bool:
    return os.environ.get(FLAG, "1").strip().lower() not in {"0", "false", "no", "off"}


# ----------------------------------------------------------------------------------------------- git plumbing


def _env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"}}
    env.update(
        GIT_OPTIONAL_LOCKS="0",
        GIT_TERMINAL_PROMPT="0",
        GIT_AUTHOR_NAME="AgentDev",
        GIT_AUTHOR_EMAIL="agentdev@localhost",
        GIT_COMMITTER_NAME="AgentDev",
        GIT_COMMITTER_EMAIL="agentdev@localhost",
    )
    env.update(extra or {})
    return env


def _git(root: Path, *args: str, env: dict[str, str] | None = None, stdin: bytes | None = None,
         timeout: float = GIT_TIMEOUT_S, ok: tuple[int, ...] = (0,)) -> bytes:
    cmd = ["git", "-c", "core.quotepath=off", "-c", "core.longpaths=true", "-c", "core.fsmonitor=false",
           "--literal-pathspecs", *args]
    try:
        done = subprocess.run(cmd, cwd=str(root), input=stdin, capture_output=True, timeout=timeout,
                              env=_env(env), creationflags=_NO_WINDOW, shell=False)
    except FileNotFoundError as exc:
        raise GitUnavailable("git is not installed or not on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitUnavailable(f"git {args[0]} timed out") from exc
    except OSError as exc:
        raise GitUnavailable(str(exc)) from exc
    if done.returncode not in ok:
        tail = done.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
        raise GitUnavailable(f"git {args[0]} failed: {tail[0][:200]}")
    return done.stdout


def _text(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")


def _lock_for(root: Path) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(str(root), threading.Lock())


def _is_repo_root(root: Path) -> bool:
    """True when ``root`` itself is the top of a git work tree (not a folder inside a bigger repo)."""
    if not root.is_dir() or is_link(root):
        return False
    try:
        top = _text(_git(root, "rev-parse", "--show-toplevel")).strip()
    except GitUnavailable:
        return False
    if not top:
        return False
    return os.path.normcase(os.path.realpath(top)) == os.path.normcase(os.path.realpath(root))


def _git_dir(root: Path) -> Path:
    out = _text(_git(root, "rev-parse", "--absolute-git-dir")).strip()
    return Path(out)


def safe_key(key: str) -> str:
    """A ref-safe form of a run key (session ids are UUIDs; anything else is sanitized + hashed)."""
    if _SAFE_KEY.match(key or ""):
        return key
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", key or "")[:48].strip("_") or "run"
    return f"{cleaned}-{hashlib.sha1((key or '').encode('utf-8', 'replace')).hexdigest()[:8]}"


def _prefix(key: str) -> str:
    return f"{REF_ROOT}/run-{safe_key(key)}/"


def _latest_turn(root: Path, key: str) -> int:
    out = _text(_git(root, "for-each-ref", "--format=%(refname)", _prefix(key).rstrip("/") + "/"))
    best = 0
    prefix = _prefix(key)
    for line in out.splitlines():
        tail = line.strip()[len(prefix):]
        if tail.isdigit():
            best = max(best, int(tail))
    return best


def _ref_commit(root: Path, ref: str) -> str | None:
    raw = _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}", ok=(0, 1))
    return _text(raw).strip() or None


def _capture(root: Path, message: str) -> str:
    """Commit (hash) holding the whole work tree as it is now. Real index and work tree are untouched."""
    scratch = Path(tempfile.mkdtemp(prefix="agentdev-idx-"))
    try:
        index = scratch / "index"
        real = _git_dir(root) / "index"
        if real.is_file():
            # The stat cache makes `add -A` skip unchanged files. copy2 keeps the index's mtime: git re-reads
            # entries as new as the index ("racy git"), and a newer copy would hide a same-size edit made in that tick.
            shutil.copy2(real, index)
        env = {"GIT_INDEX_FILE": str(index)}
        _git(root, "add", "-A", env=env, timeout=SNAPSHOT_TIMEOUT_S)
        tree = _text(_git(root, "write-tree", env=env)).strip()
        return _text(_git(root, "commit-tree", tree, "-m", message, env=env)).strip()
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _guard(root: Path) -> dict[str, Any] | None:
    """The no-op status when checkpoints do not apply to ``root``, else None."""
    if not enabled():
        return {"status": "disabled"}
    if not _is_repo_root(root):
        return {"status": "not_git"}
    return None


# ----------------------------------------------------------------------------------------- turn start / end


def begin_turn_at(root: Path | str, key: str) -> dict[str, Any]:
    root = Path(root)
    try:
        root = root.resolve()
        blocked = _guard(root)
        if blocked:
            return blocked
        with _lock_for(root):
            turn = _latest_turn(root, key) + 1
            commit = _capture(root, f"agentdev checkpoint before turn {turn}")
            ref = f"{_prefix(key)}{turn}"
            _git(root, "update-ref", ref, commit)
        return {"status": "ok", "turn": turn, "ref": ref}
    except (GitUnavailable, OSError) as exc:
        logger.warning("git checkpoint (begin) skipped: %s", exc)
        return {"status": "error", "message": str(exc)}


def end_turn_at(root: Path | str, key: str, turn: int | None = None) -> dict[str, Any]:
    """Record what the run left (once per turn), so a later user edit can be told apart from the run's own."""
    root = Path(root)
    try:
        root = root.resolve()
        blocked = _guard(root)
        if blocked:
            return blocked
        with _lock_for(root):
            turn = turn or _latest_turn(root, key)
            if not turn:
                return {"status": "no_checkpoint"}
            after = f"{_prefix(key)}{turn}-after"
            if _ref_commit(root, after) is None:
                _git(root, "update-ref", after, _capture(root, f"agentdev checkpoint after turn {turn}"))
        return {"status": "ok", "turn": turn}
    except (GitUnavailable, OSError) as exc:
        logger.warning("git checkpoint (end) skipped: %s", exc)
        return {"status": "error", "message": str(exc)}


# ---------------------------------------------------------------------------------------------- changes / undo

_CHANGE = {"A": "added", "M": "modified", "D": "deleted", "T": "modified"}


def _chunks(items: list[str]) -> list[list[str]]:
    return [items[i:i + PATH_CHUNK] for i in range(0, len(items), PATH_CHUNK)]


def _blobs(root: Path, commit: str, paths: list[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for chunk in _chunks(paths):
        raw = _git(root, "ls-tree", "-r", "-z", commit, "--", *chunk)
        for entry in raw.split(b"\0"):
            if not entry:
                continue
            meta, _, name = entry.partition(b"\t")
            parts = meta.split()
            if len(parts) == 3:
                found[_text(name)] = _text(parts[2])
    return found


def _current_hash(root: Path, rel: str) -> str | None:
    target = root / rel
    if is_link(target) or not target.is_file():
        return None if not target.exists() and not is_link(target) else "!not-a-regular-file"
    try:
        return _text(_git(root, "hash-object", "--", rel)).strip() or None
    except GitUnavailable:
        return "!unreadable"


def _settled(root: Path, key: str, turn: int) -> tuple[str, str]:
    before = _ref_commit(root, f"{_prefix(key)}{turn}")
    after = _ref_commit(root, f"{_prefix(key)}{turn}-after")
    if before is None:
        raise GitUnavailable("checkpoint ref is missing")
    if after is None:  # the run ended without recording it (server restart / crash): capture what is there now
        after = _capture(root, f"agentdev checkpoint after turn {turn}")
        _git(root, "update-ref", f"{_prefix(key)}{turn}-after", after)
    return before, after


def _classify(root: Path, before: str, after: str) -> tuple[list[dict[str, Any]], int]:
    raw = _git(root, "diff-tree", "-r", "-z", "--no-renames", "--name-status", before, after)
    tokens = [t for t in raw.split(b"\0")]
    changed: list[tuple[str, str]] = []
    i = 0
    while i + 1 < len(tokens):
        code, name = _text(tokens[i]).strip(), _text(tokens[i + 1])
        if code and name:
            changed.append((name, _CHANGE.get(code[0], "modified")))
        i += 2
    changed.sort()
    total = len(changed)
    changed = changed[:MAX_FILES]
    names = [n for n, _ in changed]
    b_blobs, a_blobs = _blobs(root, before, names), _blobs(root, after, names)
    files = []
    for name, change in changed:
        cur, a, b = _current_hash(root, name), a_blobs.get(name), b_blobs.get(name)
        state = "pending" if cur == a else "reverted" if cur == b else "conflict"
        files.append({"path": name, "change": change, "state": state})
    return files, total


def _diff(root: Path, before: str, after: str, rel: str) -> dict[str, Any]:
    try:
        text = _text(_git(root, "diff", "--no-color", "--no-ext-diff", "--no-renames", "-U3", before, after, "--", rel))
    except GitUnavailable:
        return {"diff": "", "binary": False, "truncated": False}
    if text.startswith("Binary files") or "\nBinary files" in text[:400]:
        return {"diff": "", "binary": True, "truncated": False}
    at = text.find("@@")
    text = text[at:] if at >= 0 else text
    truncated = len(text) > MAX_DIFF_CHARS
    return {"diff": text[:MAX_DIFF_CHARS], "binary": False, "truncated": truncated}


def changes_at(root: Path | str, key: str, *, running: bool = False) -> dict[str, Any]:
    root = Path(root)
    try:
        root = root.resolve()
        blocked = _guard(root)
        if blocked:
            return {**blocked, "files": []}
        with _lock_for(root):
            turn = _latest_turn(root, key)
            if not turn:
                return {"status": "no_checkpoint", "files": []}
            if running and _ref_commit(root, f"{_prefix(key)}{turn}-after") is None:
                return {"status": "running", "turn": turn, "files": []}
            before, after = _settled(root, key, turn)
            files, total = _classify(root, before, after)
            for index, entry in enumerate(files):
                if index < MAX_DIFF_FILES:
                    entry.update(_diff(root, before, after, entry["path"]))
                else:
                    entry.update(diff="", binary=False, truncated=True)
        counts = {s: sum(1 for f in files if f["state"] == s) for s in ("pending", "conflict", "reverted")}
        return {"status": "ok", "turn": turn, "files": files, "total": total, "truncated": total > len(files),
                "counts": counts}
    except (GitUnavailable, OSError) as exc:
        return {"status": "error", "message": str(exc), "files": []}


def _inside(root: Path, rel: str) -> Path:
    """``root/rel`` once checked: relative, no traversal, no link on the way."""
    if not rel or "\0" in rel or rel.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", rel):
        raise LabOutputsError(400, "Invalid path", code="git_checkpoint_bad_path")
    parts = re.split(r"[\\/]+", rel)
    if any(p in {"", ".", ".."} for p in parts) or parts[0].lower() == ".git":
        raise LabOutputsError(400, "Invalid path", code="git_checkpoint_bad_path")
    current = root
    for part in parts[:-1]:
        current = current / part
        if is_link(current):
            raise LabOutputsError(400, "Invalid path", code="git_checkpoint_bad_path")
    target = current / parts[-1]
    if not target.resolve(strict=False).is_relative_to(root):
        raise LabOutputsError(400, "Invalid path", code="git_checkpoint_bad_path")
    return target


def _prune_empty_parents(root: Path, target: Path) -> None:
    parent = target.parent
    while parent != root and root in parent.parents:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def undo_at(root: Path | str, key: str, *, paths: list[str] | None = None, running: bool = False) -> dict[str, Any]:
    root = Path(root).resolve()
    if paths is not None:
        for p in paths:
            _inside(root, str(p))  # traversal is rejected before anything else
    blocked = _guard(root)
    if blocked:
        raise LabOutputsError(409, "Git checkpoints are not available for this folder", code=f"git_checkpoint_{blocked['status']}")
    if running:
        raise LabOutputsError(409, "The run is still going; undo after it ends", code="git_checkpoint_running")
    restored: list[str] = []
    removed: list[str] = []
    conflicts: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    try:
        with _lock_for(root):
            turn = _latest_turn(root, key)
            if not turn:
                raise LabOutputsError(404, "No checkpoint for this run", code="git_checkpoint_none")
            before, after = _settled(root, key, turn)
            files, _total = _classify(root, before, after)
            known = {f["path"]: f for f in files}
            wanted = list(known) if paths is None else list(dict.fromkeys(str(p).replace("\\", "/") for p in paths))
            for p in wanted:
                if p not in known:
                    raise LabOutputsError(400, "That file was not changed by this run", code="git_checkpoint_bad_path")
            scratch = Path(tempfile.mkdtemp(prefix="agentdev-idx-"))
            try:
                env = {"GIT_INDEX_FILE": str(scratch / "index")}
                _git(root, "read-tree", before, env=env)
                for p in sorted(wanted):
                    entry = known[p]
                    if entry["state"] == "conflict":
                        conflicts.append({"path": p, "reason": "modified_after_run"})
                        continue
                    if entry["state"] == "reverted":
                        continue
                    try:
                        target = _inside(root, p)
                        if entry["change"] == "added":
                            target.unlink(missing_ok=True)
                            _prune_empty_parents(root, target)
                            removed.append(p)
                        else:
                            _git(root, "checkout-index", "-f", "--", p, env=env)
                            restored.append(p)
                    except (OSError, GitUnavailable, LabOutputsError) as exc:
                        errors.append({"path": p, "message": str(exc)[:200]})
            finally:
                shutil.rmtree(scratch, ignore_errors=True)
    except GitUnavailable as exc:
        raise LabOutputsError(500, str(exc), code="git_checkpoint_failed") from exc
    return {"status": "ok", "turn": turn, "restored": restored, "removed": removed, "conflicts": conflicts,
            "errors": errors}


def keep_branch_at(root: Path | str, key: str, *, running: bool = False) -> dict[str, Any]:
    """Branch ``agentdev/run-<key>`` at what the run left (no checkout; HEAD stays where it is)."""
    root = Path(root).resolve()
    blocked = _guard(root)
    if blocked:
        raise LabOutputsError(409, "Git checkpoints are not available for this folder", code=f"git_checkpoint_{blocked['status']}")
    if running:
        raise LabOutputsError(409, "The run is still going; keep it after it ends", code="git_checkpoint_running")
    try:
        with _lock_for(root):
            turn = _latest_turn(root, key)
            if not turn:
                raise LabOutputsError(404, "No checkpoint for this run", code="git_checkpoint_none")
            _before, after = _settled(root, key, turn)
            base = f"agentdev/run-{safe_key(key)}"
            for attempt in range(1, 100):
                name = base if attempt == 1 else f"{base}-{attempt}"
                if _ref_commit(root, f"refs/heads/{name}") is None:
                    _git(root, "branch", name, after)
                    return {"status": "ok", "turn": turn, "branch": name, "commit": after}
            raise LabOutputsError(409, "Too many branches for this run", code="git_checkpoint_failed")
    except GitUnavailable as exc:
        raise LabOutputsError(500, str(exc), code="git_checkpoint_failed") from exc


# ------------------------------------------------------------------------------------------ session wrappers


def run_in_progress_for(session_id: str) -> bool:
    session = None
    with contextlib.suppress(Exception):
        session = session_outputs.session_lookup(session_id)
    return session is not None and (getattr(session, "executor", None) is not None
                                    or bool(getattr(session, "starting", False)))


def _root(session_id: str) -> Path:
    return session_outputs.output_location(session_id)["root"]


def begin_turn(session_id: str) -> dict[str, Any]:
    try:
        return begin_turn_at(_root(session_id), session_id)
    except Exception as exc:  # noqa: BLE001 - a checkpoint must never fail a run
        logger.warning("git checkpoint (begin) skipped: %s", exc)
        return {"status": "error", "message": str(exc)}


def end_turn(session_id: str, turn: int | None = None) -> dict[str, Any]:
    try:
        return end_turn_at(_root(session_id), session_id, turn)
    except Exception as exc:  # noqa: BLE001
        logger.warning("git checkpoint (end) skipped: %s", exc)
        return {"status": "error", "message": str(exc)}


def changes(session_id: str) -> dict[str, Any]:
    return changes_at(_root(session_id), session_id, running=run_in_progress_for(session_id))


def undo(session_id: str, paths: list[str] | None = None) -> dict[str, Any]:
    return undo_at(_root(session_id), session_id, paths=paths, running=run_in_progress_for(session_id))


def keep_branch(session_id: str) -> dict[str, Any]:
    return keep_branch_at(_root(session_id), session_id, running=run_in_progress_for(session_id))
