"""Saved conversations of the workflow assistant, one JSON file per session.

A session belongs to one workflow (``workflow`` is its bare name, no ``.yaml``) or to "new workflow"
(``workflow`` None). The browser owns the message shape (replies, proposal cards and their state,
local notices) and saves the whole session after each change; this module only stores, lists and
deletes it, so a reload or another day can continue the same chat with its context.

Files live in ``STORAGE_DIR/assistant_sessions/<id>.json`` and are written atomically.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentdev.paths import STORAGE_DIR

SESSIONS_DIR = STORAGE_DIR / "assistant_sessions"
MAX_SESSION_BYTES = 4_000_000  # proposals carry whole YAML files; this is far above a long chat
MAX_SESSIONS_PER_LIST = 200
TITLE_LIMIT = 120

_ID_RE = re.compile(r"\A[A-Za-z0-9_-]{8,64}\Z")
# Same alphabet as workflow file names (validate_workflow_filename), without the extension.
_WORKFLOW_RE = re.compile(r"\A[A-Za-z0-9._-]{1,128}\Z")
_lock = threading.Lock()


class SessionError(Exception):
    """Bad id / payload (``code`` "bad_request") or missing session (``code`` "not_found")."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _dir() -> Path:
    return Path(SESSIONS_DIR)


def check_id(session_id: str) -> str:
    if not isinstance(session_id, str) or not _ID_RE.match(session_id):
        raise SessionError("bad_request", "Invalid session id")
    return session_id


def normalise_workflow(workflow: Optional[str]) -> Optional[str]:
    """Bare workflow name (``x.yaml`` -> ``x``), None for "new workflow"; raises on anything unsafe."""
    if workflow is None or workflow == "":
        return None
    name = str(workflow)
    if name.lower().endswith(".yaml"):
        name = name[:-5]
    elif name.lower().endswith(".yml"):
        name = name[:-4]
    if not _WORKFLOW_RE.match(name) or name in (".", ".."):
        raise SessionError("bad_request", "Invalid workflow name")
    return name


def _path(session_id: str) -> Path:
    return _dir() / f"{check_id(session_id)}.json"


def _read(path: Path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _summary(data: dict) -> dict:
    messages = data.get("messages") if isinstance(data.get("messages"), list) else []
    return {
        "id": data.get("id"),
        "workflow": data.get("workflow"),
        "title": data.get("title") or "",
        "created_at": data.get("created_at"),
        "updated_at": data.get("updated_at"),
        "message_count": sum(1 for m in messages if isinstance(m, dict) and m.get("role") in ("user", "assistant")),
        "vendor": data.get("vendor"),
        "model": data.get("model"),
    }


def list_sessions(workflow: Optional[str] = None, *, all_workflows: bool = False) -> List[dict]:
    """Summaries, newest first. ``workflow`` None lists the "new workflow" sessions unless
    ``all_workflows``."""
    wanted = normalise_workflow(workflow)
    folder = _dir()
    if not folder.is_dir():
        return []
    items = []
    for path in folder.glob("*.json"):
        data = _read(path)
        if data is None or data.get("id") != path.stem:
            continue
        if not all_workflows and data.get("workflow") != wanted:
            continue
        items.append(_summary(data))
    items.sort(key=lambda s: s.get("updated_at") or 0, reverse=True)
    return items[:MAX_SESSIONS_PER_LIST]


def get_session(session_id: str) -> dict:
    data = _read(_path(session_id))
    if data is None:
        raise SessionError("not_found", "Session not found")
    return data


def _clean_title(title: Any) -> str:
    text = " ".join(str(title or "").split())
    return text[:TITLE_LIMIT]


def save_session(session_id: str, *, workflow: Optional[str], title: Any, messages: Any,
                 pending_message_id: Optional[str] = None, vendor: Optional[str] = None,
                 model: Optional[str] = None) -> dict:
    """Create or replace the session; keeps ``created_at``. Returns its summary."""
    path = _path(session_id)
    if not isinstance(messages, list):
        raise SessionError("bad_request", "messages must be a list")
    now = time.time()
    with _lock:
        old = _read(path) or {}
        data = {
            "id": session_id,
            "workflow": normalise_workflow(workflow),
            "title": _clean_title(title) or old.get("title") or "",
            "created_at": old.get("created_at") or now,
            "updated_at": now,
            "vendor": str(vendor)[:40] if vendor else None,
            "model": str(model)[:120] if model else None,
            "pending_message_id": str(pending_message_id)[:64] if pending_message_id else None,
            "messages": messages,
        }
        text = json.dumps(data, ensure_ascii=False)
        if len(text.encode("utf-8")) > MAX_SESSION_BYTES:
            raise SessionError("bad_request", "The session is too large to save")
        folder = _dir()
        folder.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(text)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    return _summary(data)


def delete_session(session_id: str) -> bool:
    path = _path(session_id)
    with _lock:
        try:
            path.unlink()
        except FileNotFoundError:
            return False
    return True
