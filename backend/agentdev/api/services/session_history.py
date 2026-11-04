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
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

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
# Progress of the latest run (finished nodes, notes), used to resume an interrupted run
CHECKPOINT_FILE = "checkpoint.json"
TITLE_MAX_CHARS = 80
# An open replay-log handle that has not been written to for this long is closed (see _stream_for)
STREAM_IDLE_SECONDS = 5.0
MAX_OPEN_STREAMS = 16
# Written once the greeting-title backfill has scanned the folder (see retitle_small_talk_sessions)
RETITLE_MARKER = ".retitled_small_talk_v1"


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
        # Open append handles of messages.jsonl by session id -> (handle, last used). A run writes
        # hundreds of messages; reopening the file for each one costs far more than the write itself.
        self._streams: Dict[str, Tuple[Any, float]] = {}
        # list_meta cache: session folder -> ((meta stat, review stat), item). The sidebar lists every
        # session often; re-parsing unchanged JSON files each time is wasted work.
        self._meta_cache: Dict[str, Tuple[tuple, Dict[str, Any]]] = {}

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
        try:
            validate_path_component(session_id, field="session_id")
        except ValidationError:
            return
        line = encoded.replace("\n", " ") + "\n"
        try:
            with self._lock:
                handle = self._stream_for(session_id)
                if handle is None:
                    return
                handle.write(line)
                handle.flush()  # visible to other readers at once; no per-message open/close
        except (OSError, ValueError) as exc:
            self._drop_stream(session_id)
            self.logger.warning("Failed to append session message %s: %s", session_id, exc)

    def _stream_for(self, session_id: str):
        """The open append handle of a session's replay log (caller holds the lock); None if unusable."""
        now = time.monotonic()
        for other, (handle, used) in list(self._streams.items()):
            if other != session_id and now - used > STREAM_IDLE_SECONDS:
                self._close_quietly(handle)
                del self._streams[other]
        entry = self._streams.get(session_id)
        if entry is not None and entry[0].closed:
            entry = None
        if entry is None:
            path = self._dir(session_id, create=True)
            if path is None:
                return None
            while len(self._streams) >= MAX_OPEN_STREAMS:
                oldest = min(self._streams, key=lambda key: self._streams[key][1])
                self._close_quietly(self._streams.pop(oldest)[0])
            entry = (open(path / MESSAGES_FILE, "a", encoding="utf-8"), now)
        self._streams[session_id] = (entry[0], now)
        return entry[0]

    @staticmethod
    def _close_quietly(handle) -> None:
        try:
            handle.close()
        except OSError:
            pass

    def _drop_stream(self, session_id: str) -> None:
        with self._lock:
            entry = self._streams.pop(session_id, None)
        if entry is not None:
            self._close_quietly(entry[0])

    def close_stream(self, session_id: str) -> None:
        """Release the replay-log handle of a session whose run ended (reopened on the next message)."""
        self._drop_stream(session_id)

    def rewrite_messages(self, session_id: str, messages: List[Dict[str, Any]]) -> None:
        """Replace the replay log with ``messages`` (drops what the in-memory buffer already evicted)."""
        path = self._dir(session_id)
        if path is None or not path.is_dir():
            return
        tmp = path / (MESSAGES_FILE + ".tmp")
        try:
            body = "".join(json.dumps(m, ensure_ascii=False, default=str).replace("\n", " ") + "\n" for m in messages)
            with self._lock:
                entry = self._streams.pop(session_id, None)
                if entry is not None:
                    self._close_quietly(entry[0])
                tmp.write_text(body, encoding="utf-8")
                os.replace(tmp, path / MESSAGES_FILE)
        except (OSError, TypeError, ValueError) as exc:
            self.logger.warning("Failed to compact session messages %s: %s", session_id, exc)

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

    def save_checkpoint(self, session_id: str, checkpoint: Dict[str, Any]) -> None:
        path = self._dir(session_id, create=True)
        if path is None:
            return
        tmp = path / (CHECKPOINT_FILE + ".tmp")
        try:
            with self._lock:
                tmp.write_text(json.dumps(checkpoint, ensure_ascii=False, default=str), encoding="utf-8")
                os.replace(tmp, path / CHECKPOINT_FILE)
        except (OSError, TypeError, ValueError) as exc:
            self.logger.warning("Failed to save checkpoint %s: %s", session_id, exc)

    def load_checkpoint(self, session_id: str) -> Optional[Dict[str, Any]]:
        path = self._dir(session_id)
        return self._read_json(path / CHECKPOINT_FILE) if path else None

    def delete(self, session_id: str) -> bool:
        path = self._dir(session_id)
        if path is None or not path.is_dir():
            return False
        with self._lock:
            entry = self._streams.pop(session_id, None)
            if entry is not None:
                self._close_quietly(entry[0])
            shutil.rmtree(path, ignore_errors=True)
        self._meta_cache.pop(session_id, None)
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

    @staticmethod
    def _stat_key(path: Path) -> Optional[Tuple[int, int]]:
        try:
            stat = path.stat()
        except OSError:
            return None
        return (stat.st_mtime_ns, stat.st_size)

    def list_meta(self) -> List[Dict[str, Any]]:
        if not self.root.is_dir():
            return []
        items = []
        seen = set()
        for child in self.root.iterdir():
            if not child.is_dir() or is_link(child):
                continue
            key = (self._stat_key(child / META_FILE), self._stat_key(child / REVIEW_FILE))
            if key[0] is None:
                continue
            seen.add(child.name)
            cached = self._meta_cache.get(child.name)
            if cached is not None and cached[0] == key:
                item = cached[1]
            else:
                meta = self._read_json(child / META_FILE)
                if not meta or meta.get("session_id") != child.name:
                    self._meta_cache.pop(child.name, None)
                    continue
                review = self._read_json(child / REVIEW_FILE)
                item = {**meta, "review": review} if review else meta
                self._meta_cache[child.name] = (key, item)
            items.append(dict(item))  # callers add fields to what they get
        for stale in [name for name in self._meta_cache if name not in seen]:
            del self._meta_cache[stale]
        items.sort(key=lambda item: item.get("updated_at") or 0, reverse=True)
        return items

    # ------------------------------------------------------------------ one-time fixes
    def retitle_small_talk_sessions(self, is_small_talk: Callable[[str], bool]) -> Dict[str, str]:
        """Re-title sessions saved before follow-ups replaced a greeting title ("chào bạn").

        For each saved session titled by small talk (and never renamed by the user), the
        first later user message that is a real request becomes the title, by the same
        ``make_title`` rule as a live run. Runs once per storage folder: a marker file is
        written when the scan finishes. Only ``title`` in meta.json is ever changed.
        Returns ``{session_id: new_title}`` for the sessions it changed.
        """
        if not self.root.is_dir() or (self.root / RETITLE_MARKER).exists():
            return {}
        changed: Dict[str, str] = {}
        for child in self.root.iterdir():
            try:
                if not child.is_dir() or is_link(child):
                    continue
                title = self._retitle_one(child, is_small_talk)
                if title:
                    changed[child.name] = title
            except Exception as exc:  # one odd folder must not stop the rest
                self.logger.warning("Skipped re-titling session %s: %s", child.name, exc)
        try:
            (self.root / RETITLE_MARKER).write_text(json.dumps({"retitled": len(changed)}), encoding="utf-8")
        except OSError as exc:
            self.logger.warning("Failed to write re-title marker: %s", exc)
        if changed:
            self.logger.info("Re-titled %d session(s) that opened with small talk", len(changed))
        return changed

    def _retitle_one(self, path: Path, is_small_talk: Callable[[str], bool]) -> Optional[str]:
        meta = self._read_json(path / META_FILE)
        if not meta or meta.get("session_id") != path.name or meta.get("title_custom"):
            return None
        if not is_small_talk(meta.get("title") or ""):
            return None
        new_title = next(
            (t for t in (make_title(text) for text in self._user_texts(path)) if t and not is_small_talk(t)),
            None,
        )
        if not new_title:
            return None
        target = path / META_FILE
        tmp = path / (META_FILE + ".tmp")
        with self._lock:
            current = self._read_json(target)
            # Re-check under the lock: a live write or a rename may have landed meanwhile
            if not current or current.get("title_custom") or current.get("title") != meta.get("title"):
                return None
            tmp.write_text(json.dumps({**current, "title": new_title}, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, target)
        return new_title

    def _user_texts(self, path: Path) -> List[str]:
        """What the user typed, in order: from the replay log, else from the saved turns."""
        texts: List[str] = []
        try:
            with open(path / MESSAGES_FILE, encoding="utf-8") as handle:
                for line in handle:
                    try:
                        message = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(message, dict) and message.get("type") == "user_message":
                        data = message.get("data")
                        text = data.get("text") if isinstance(data, dict) else None
                        if isinstance(text, str):
                            texts.append(text)
        except OSError:
            pass
        if texts:
            return texts
        data = self._read_json(path / TURNS_FILE) or {}
        turns = data.get("turns")
        if not isinstance(turns, list):
            return []
        return [t["user"] for t in turns if isinstance(t, dict) and isinstance(t.get("user"), str)]

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
