"""Session persistence primitives for workflow runs."""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from threading import Event
from typing import Any, Dict, List, Optional

from agentdev.api.services.artifact_events import ArtifactEventQueue
from agentdev.api.services.session_history import SessionHistoryStore, make_title


class SessionBusyError(RuntimeError):
    """A run is live in this session; its session object must not be replaced."""


# Older turns are never shown to a follow-up run, so there is no point keeping them
MAX_STORED_TURNS = 50


class SessionStatus(Enum):
    """Lifecycle states for a workflow session."""

    IDLE = "idle"
    RUNNING = "running"
    WAITING_FOR_INPUT = "waiting_for_input"
    # Cancel requested; the run is still winding down. CANCELLED once it really ended.
    CANCELLING = "cancelling"
    COMPLETED = "completed"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class WorkflowSession:
    """Mutable record describing a workflow session."""

    session_id: str
    yaml_file: str
    task_prompt: str
    task_attachments: list[str] = field(default_factory=list)
    title: str = ""
    # Project folders added to this session: {name, attachment_id, project_id, workspace_path, file_count}
    projects: list = field(default_factory=list)
    status: SessionStatus = SessionStatus.IDLE
    created_at: float = field(default_factory=lambda: time.time())
    updated_at: float = field(default_factory=lambda: time.time())

    # Execution metadata
    executor: Optional[Any] = None
    graph: Optional[Any] = None
    current_node_id: Optional[str] = None
    # Set synchronously when a launch is accepted, before the first await, so a second
    # launch can't slip in before ``executor`` exists. Cleared when the run ends.
    starting: bool = False

    # Human input tracking
    waiting_for_input: bool = False
    input_promise: Optional[Any] = None
    pending_input_data: Optional[Dict[str, Any]] = None
    human_input_future: Optional[Any] = None
    human_input_value: Optional[str] = None

    # Results + errors
    results: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None

    # Artifact streaming
    artifact_queue: ArtifactEventQueue = field(default_factory=ArtifactEventQueue)

    # Cancellation tracking
    cancel_event: Event = field(default_factory=Event)
    cancel_reason: Optional[str] = None

    # Message buffer for reconnection replay
    message_buffer: list = field(default_factory=list)

    # Finished turns of this conversation ({user, answer, attachments}); a follow-up
    # run in the same session hands them to its start node.
    turns: list = field(default_factory=list)

    # True once a run of this session changed files (an ``artifact_created`` message was recorded).
    files_changed: bool = False

    MAX_BUFFER_SIZE: int = 1000

    def append_message(self, message: Dict[str, Any]) -> None:
        if len(self.message_buffer) >= self.MAX_BUFFER_SIZE:
            # Evict the oldest message that is not what the user typed: a replay of a
            # long conversation must still show the message that started each turn.
            index = next(
                (i for i, item in enumerate(self.message_buffer) if not _is_pinned(item)),
                0,
            )
            self.message_buffer.pop(index)
        self.message_buffer.append(message)


def _is_pinned(message: Any) -> bool:
    return isinstance(message, dict) and message.get("type") == "user_message"


def _changes_files(message: Any) -> bool:
    """An ``artifact_created`` message that reports at least one changed file."""
    if not isinstance(message, dict) or message.get("type") != "artifact_created":
        return False
    data = message.get("data")
    return isinstance(data, dict) and bool(data.get("events"))


_LIVE_STATUSES = (SessionStatus.RUNNING, SessionStatus.WAITING_FOR_INPUT, SessionStatus.CANCELLING)


def awaiting_plan(session: WorkflowSession) -> bool:
    """The latest turn is a plan the user has not answered yet (cleared once the next turn starts)."""
    # By status, not by executor: the plan turn is saved while its run is still being wrapped up.
    if session.status in _LIVE_STATUSES:
        return False
    # A run started after the plan (approval) that was stopped or interrupted: not waiting any more
    if session.status in (SessionStatus.CANCELLED, SessionStatus.ERROR):
        return False
    turns = session.turns
    return bool(turns) and isinstance(turns[-1], dict) and turns[-1].get("kind") == "plan"


def has_work(session: WorkflowSession) -> bool:
    """Some turn delegated work to team members, or a run changed files."""
    return session.files_changed or any(isinstance(t, dict) and t.get("team") for t in session.turns)


class WorkflowSessionStore:
    """In-memory registry that tracks workflow session metadata.

    When a history store is given, every session and buffered message is also
    mirrored to disk so it can be listed and replayed after a server restart.
    """

    def __init__(self, history: Optional[SessionHistoryStore] = None) -> None:
        self._sessions: Dict[str, WorkflowSession] = {}
        self.history = history
        self.logger = logging.getLogger(__name__)
        self._titles_backfilled = False

    @staticmethod
    def _meta(session: WorkflowSession) -> Dict[str, Any]:
        return {
            "session_id": session.session_id,
            "yaml_file": session.yaml_file,
            "title": session.title,
            "status": session.status.value,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "current_node_id": session.current_node_id,
            "error_message": session.error_message,
            "message_count": len(session.message_buffer),
            "projects": list(session.projects),
            "awaiting_plan": awaiting_plan(session),
            "has_work": has_work(session),
        }

    def _persist(self, session: WorkflowSession) -> None:
        if self.history is not None:
            self.history.save_meta(self._meta(session))

    def record_message(self, session_id: str, message: Dict[str, Any], encoded: str) -> None:
        """Buffer a message for replay (and mirror it to disk when history is enabled)."""
        session = self._sessions.get(session_id)
        if not session:
            return
        session.append_message(message)
        session.updated_at = time.time()
        if self.history is not None:
            self.history.append_message(session_id, encoded)
        if not session.files_changed and _changes_files(message):
            session.files_changed = True
            self._persist(session)

    def restore_session(self, session_id: str) -> Optional[WorkflowSession]:
        """Load a session that only exists on disk (e.g. after a server restart)."""
        if session_id in self._sessions:
            return self._sessions[session_id]
        if self.history is None:
            return None
        meta = self.history.get_meta(session_id)
        if not meta:
            return None
        try:
            status = SessionStatus(meta.get("status"))
        except ValueError:
            status = SessionStatus.ERROR
        error_message = meta.get("error_message")
        # The executor of an unfinished run died with the previous process.
        # A draft (IDLE: projects added, never launched) simply stays a draft.
        interrupted = status in (SessionStatus.RUNNING, SessionStatus.WAITING_FOR_INPUT, SessionStatus.CANCELLING)
        if interrupted:
            status = SessionStatus.CANCELLED
            error_message = "Interrupted by a server restart"
        session = WorkflowSession(
            session_id=session_id,
            yaml_file=meta.get("yaml_file") or "",
            task_prompt="",
            title=meta.get("title") or "",
            status=status,
            created_at=meta.get("created_at") or time.time(),
            updated_at=meta.get("updated_at") or time.time(),
            current_node_id=meta.get("current_node_id"),
            error_message=error_message,
            projects=list(meta.get("projects") or []),
        )
        # Load everything and apply the same eviction as live, so turn-start user messages survive.
        for message in self.history.load_messages(session_id, 0):
            session.append_message(message)
            session.files_changed = session.files_changed or _changes_files(message)
        session.turns = self.history.load_turns(session_id)
        self._sessions[session_id] = session
        if interrupted:
            self._persist(session)
        self.logger.info("Restored session %s from history", session_id)
        return session

    def list_summaries(self) -> List[Dict[str, Any]]:
        """Every known session, newest first; live sessions override their saved copy."""
        merged: Dict[str, Dict[str, Any]] = {}
        self._backfill_small_talk_titles()
        if self.history is not None:
            for meta in self.history.list_meta():
                merged[meta["session_id"]] = meta
        for session in self._sessions.values():
            saved = merged.get(session.session_id, {})
            live = self._meta(session)
            if saved.get("title_custom"):
                live["title"] = saved.get("title")
            merged[session.session_id] = {**saved, **live}
        for item in merged.values():  # sessions saved before these fields existed
            item.setdefault("awaiting_plan", False)
            item.setdefault("has_work", False)
            # Older saved meta can keep a plan flag after the run was stopped or failed
            if item.get("status") in (SessionStatus.CANCELLED.value, SessionStatus.ERROR.value):
                item["awaiting_plan"] = False
        return sorted(merged.values(), key=lambda item: item.get("updated_at") or 0, reverse=True)

    def _backfill_small_talk_titles(self) -> None:
        """Once per process (and once per storage folder, via a marker): re-title sessions
        saved before ``_retitle_after_small_talk`` existed."""
        if self._titles_backfilled or self.history is None:
            return
        self._titles_backfilled = True
        from agentdev.runtime.node.agent.team import is_small_talk

        try:
            changed = self.history.retitle_small_talk_sessions(is_small_talk)
        except Exception as exc:  # a broken storage folder must not break the sidebar
            self.logger.warning("Re-titling saved sessions failed: %s", exc)
            return
        for session_id, title in changed.items():
            session = self._sessions.get(session_id)
            if session is not None and is_small_talk(session.title):
                session.title = title

    def delete_session(self, session_id: str) -> bool:
        removed = self._sessions.pop(session_id, None) is not None
        if self.history is not None:
            removed = self.history.delete(session_id) or removed
        return removed

    def create_session(
        self,
        *,
        yaml_file: str,
        task_prompt: str,
        session_id: str,
        attachments: Optional[list[str]] = None,
        title_hint: Optional[str] = None,
    ) -> WorkflowSession:
        session = WorkflowSession(
            session_id=session_id,
            yaml_file=yaml_file,
            task_prompt=task_prompt,
            task_attachments=list(attachments or []),
            # An attachments-only first message is titled by its file names, not the workflow file.
            title=make_title(task_prompt or title_hint or "", fallback=yaml_file),
        )
        draft = self._sessions.get(session_id)
        if draft is not None and (draft.executor is not None or draft.starting):
            raise SessionBusyError(f"Session {session_id} has a run in progress")
        if draft is not None:
            # Launching a draft keeps the projects and history gathered before the launch
            session.projects = list(draft.projects)
            session.created_at = draft.created_at
            session.message_buffer = list(draft.message_buffer)
            session.turns = list(draft.turns)
            session.files_changed = draft.files_changed
            if draft.turns and draft.title and not self._retitle_after_small_talk(draft, session.title):
                # A follow-up message keeps the conversation's title
                session.title = draft.title
        self._sessions[session_id] = session
        self._persist(session)
        self.logger.info("Created session %s for workflow %s", session_id, yaml_file)
        return session

    def _retitle_after_small_talk(self, draft: WorkflowSession, new_title: str) -> bool:
        """The conversation opened with a greeting ("chào bạn"): title it by the first real request.

        Only while the title still is that greeting, the user never renamed the session, and
        the new message is itself a request (not one more greeting or a thank-you).
        """
        # Lazy: the runtime package is heavy and only this check needs it
        from agentdev.runtime.node.agent.team import is_small_talk

        if not is_small_talk(draft.title) or not new_title or is_small_talk(new_title):
            return False
        if self.history is not None and (self.history.get_meta(draft.session_id) or {}).get("title_custom"):
            return False
        return True

    def register_project(self, session_id: str, yaml_file: Optional[str], project: Dict[str, Any]) -> WorkflowSession:
        """Attach an uploaded project folder; creates a draft session so it is listed right away."""
        session = self._sessions.get(session_id)
        if session is None:
            session = WorkflowSession(
                session_id=session_id,
                yaml_file=yaml_file or "",
                task_prompt="",
                title=make_title(project.get("name"), fallback=yaml_file or ""),
            )
            self._sessions[session_id] = session
        elif yaml_file and not session.yaml_file:
            session.yaml_file = yaml_file
        if not any(item.get("attachment_id") == project.get("attachment_id") for item in session.projects):
            session.projects.append(project)
        session.updated_at = time.time()
        self._persist(session)
        return session

    def touch(self, session: WorkflowSession) -> None:
        """Save a changed session (e.g. a draft that switched workflow)."""
        session.updated_at = time.time()
        self._persist(session)

    def add_turn(self, session_id: str, turn: Dict[str, Any]) -> None:
        """Remember a finished turn (in memory and on disk) for later follow-ups."""
        session = self._sessions.get(session_id)
        if not session:
            return
        session.turns.append(turn)
        del session.turns[:-MAX_STORED_TURNS]
        if self.history is not None:
            self.history.save_turns(session_id, list(session.turns))
        self._persist(session)  # awaiting_plan / has_work follow the turns

    def get_session(self, session_id: str) -> Optional[WorkflowSession]:
        return self._sessions.get(session_id)

    def has_session(self, session_id: str) -> bool:
        return session_id in self._sessions

    def update_session_status(self, session_id: str, status: SessionStatus, **kwargs: Any) -> None:
        session = self._sessions.get(session_id)
        if not session:
            return
        session.status = status
        session.updated_at = time.time()
        for key, value in kwargs.items():
            if hasattr(session, key):
                setattr(session, key, value)
        self._persist(session)
        self.logger.info("Updated session %s status to %s", session_id, status.value)

    def set_session_error(self, session_id: str, error_message: str) -> None:
        self.update_session_status(session_id, SessionStatus.ERROR, error_message=error_message)

    def complete_session(self, session_id: str, results: Dict[str, Any]) -> None:
        self.update_session_status(session_id, SessionStatus.COMPLETED, results=results)

    def pop_session(self, session_id: str) -> Optional[WorkflowSession]:
        return self._sessions.pop(session_id, None)

    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        return {
            "session_id": session.session_id,
            "yaml_file": session.yaml_file,
            "status": session.status.value,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "current_node_id": session.current_node_id,
            "waiting_for_input": session.waiting_for_input,
            "error_message": session.error_message,
        }

    def list_sessions(self) -> Dict[str, Dict[str, Any]]:
        return {session_id: self.get_session_info(session_id) for session_id in self._sessions.keys()}

    def get_artifact_queue(self, session_id: str) -> Optional[ArtifactEventQueue]:
        session = self._sessions.get(session_id)
        return session.artifact_queue if session else None

    def get_session_snapshot(self, session_id: str) -> Optional[Dict[str, Any]]:
        session = self._sessions.get(session_id)
        if not session:
            return None
        return {
            "session_id": session.session_id,
            "yaml_file": session.yaml_file,
            "title": session.title,
            "task_prompt": session.task_prompt,
            "status": session.status.value,
            "current_node_id": session.current_node_id,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "waiting_for_input": session.waiting_for_input,
            "error_message": session.error_message,
            "message_count": len(session.message_buffer),
            "projects": list(session.projects),
            "awaiting_plan": awaiting_plan(session),
            "has_work": has_work(session),
        }
