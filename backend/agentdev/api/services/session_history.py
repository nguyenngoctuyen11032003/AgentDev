"""On-disk history of workflow sessions so a run survives page reloads and server restarts.

Layout (one directory per session under ``storage/sessions``)::

    <session_id>/
        meta.json        summary shown in the session sidebar
        messages.jsonl   every buffered WebSocket message, one JSON object per line

The in-memory ``WorkflowSessionStore`` stays the source of truth while a run is
alive; this store only mirrors it so the run can be listed and replayed later.
"""

import json
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentdev.paths import STORAGE_DIR
from agentdev.utils.exceptions import ValidationError
from agentdev.utils.workspace_paths import validate_path_component
from agentdev.utils.workspace_paths import is_link

SESSIONS_DIR: Path = STORAGE_DIR / "sessions"

META_FILE = "meta.json"
MESSAGES_FILE = "messages.jsonl"
# The user's verdict on the delivered work; kept apart so meta rewrites never drop it
REVIEW_FILE = "review.json"
# Finished conversation turns (user message + final answer), fed to follow-up runs
TURNS_FILE = "turns.json"
TITLE_MAX_CHARS = 80


def make_title(task_prompt: Optional[str], fallback: str = "") -> str:
    """First non-empty line of the prompt, shortened for the sidebar."""
    for line in (task_prompt or "").splitlines():
        line = line.strip()
        if line:
            return line if len(line) <= TITLE_MAX_CHARS else line[: TITLE_MAX_CHARS - 1].rstrip() + "…"
    return fallback


class SessionHistoryStore:
    def __init__(self, root: Optional[Path] = None) -> None:
        # Read the module attribute at call time so tests can redirect it.
        self.root = Path(root) if root is not None else SESSIONS_DIR
        self._lock = threading.Lock()
        self.logger = logging.getLogger(__name__)

    # ------------------------------------------------------------------ paths
    def _dir(self, session_id: str, *, create: bool = False) -> Optional[Path]:
        try:
            validate_path_component(session_id, field="session_id")
        except ValidationError:
            return None
        path = self.root / session_id
        if is_link(path):
            return None
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    # ------------------------------------------------------------------ writes
    def save_meta(self, meta: Dict[str, Any]) -> None:
        path = self._dir(meta.get("session_id", ""), create=True)
        if path is None:
            return
        target = path / META_FILE
        tmp = path / (META_FILE + ".tmp")
        try:
            with self._lock:
                previous = self._read_json(target) or {}
                # A title the user typed in the sidebar wins over the generated one.
                if previous.get("title_custom"):
                    meta = {**meta, "title": previous.get("title"), "title_custom": True}
                tmp.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, target)
        except OSError as exc:
            self.logger.warning("Failed to save session meta %s: %s", meta.get("session_id"), exc)

    def append_message(self, session_id: str, encoded: str) -> None:
        path = self._dir(session_id, create=True)
        if path is None:
            return
        try:
            with self._lock, open(path / MESSAGES_FILE, "a", encoding="utf-8") as handle:
                handle.write(encoded.replace("\n", " ") + "\n")
        except OSError as exc:
            self.logger.warning("Failed to append session message %s: %s", session_id, exc)

    def rename(self, session_id: str, title: str) -> Optional[Dict[str, Any]]:
        path = self._dir(session_id)
        if path is None:
            return None
        with self._lock:
            meta = self._read_json(path / META_FILE)
            if meta is None:
                return None
            meta["title"] = title
            meta["title_custom"] = True
            (path / META_FILE).write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
            return meta

    def save_review(self, session_id: str, review: Dict[str, Any]) -> bool:
        path = self._dir(session_id)
        if path is None or not (path / META_FILE).is_file():
            return False
        tmp = path / (REVIEW_FILE + ".tmp")
        try:
            with self._lock:
                tmp.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, path / REVIEW_FILE)
        except OSError as exc:
            self.logger.warning("Failed to save review %s: %s", session_id, exc)
            return False
        return True

    def get_review(self, session_id: str) -> Optional[Dict[str, Any]]:
        path = self._dir(session_id)
        return self._read_json(path / REVIEW_FILE) if path else None

    def save_turns(self, session_id: str, turns: List[Dict[str, Any]]) -> None:
        path = self._dir(session_id, create=True)
        if path is None:
            return
        tmp = path / (TURNS_FILE + ".tmp")
        try:
            with self._lock:
                tmp.write_text(json.dumps({"turns": turns}, ensure_ascii=False), encoding="utf-8")
                os.replace(tmp, path / TURNS_FILE)
        except OSError as exc:
            self.logger.warning("Failed to save turns %s: %s", session_id, exc)

    def load_turns(self, session_id: str) -> List[Dict[str, Any]]:
        path = self._dir(session_id)
        data = self._read_json(path / TURNS_FILE) if path else None
        turns = (data or {}).get("turns")
        return [t for t in turns if isinstance(t, dict)] if isinstance(turns, list) else []

    def delete(self, session_id: str) -> bool:
        path = self._dir(session_id)
        if path is None or not path.is_dir():
            return False
        with self._lock:
            shutil.rmtree(path, ignore_errors=True)
        return True

    # ------------------------------------------------------------------ reads
    @staticmethod
    def _read_json(path: Path) -> Optional[Dict[str, Any]]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def get_meta(self, session_id: str) -> Optional[Dict[str, Any]]:
        path = self._dir(session_id)
        return self._read_json(path / META_FILE) if path else None

    def has(self, session_id: str) -> bool:
        return self.get_meta(session_id) is not None

    def list_meta(self) -> List[Dict[str, Any]]:
        if not self.root.is_dir():
            return []
        items = []
        for child in self.root.iterdir():
            if child.is_dir() and not is_link(child):
                meta = self._read_json(child / META_FILE)
                if meta and meta.get("session_id") == child.name:
                    review = self._read_json(child / REVIEW_FILE)
                    items.append({**meta, "review": review} if review else meta)
        items.sort(key=lambda item: item.get("updated_at") or 0, reverse=True)
        return items

    def load_messages(self, session_id: str, limit: int) -> List[Dict[str, Any]]:
        path = self._dir(session_id)
        if path is None:
            return []
        messages: List[Dict[str, Any]] = []
        try:
            with open(path / MESSAGES_FILE, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(message, dict):
                        messages.append(message)
        except OSError:
            return []
        return messages[-limit:] if limit else messages
