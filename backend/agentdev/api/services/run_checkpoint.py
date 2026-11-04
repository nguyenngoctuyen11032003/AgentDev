"""Checkpoint of a run, so an interrupted session can be continued instead of restarted.

A run can stop before it finishes: the user pressed stop, the server restarted, the model hit a
quota or timeout. While a run is live, a ``RunCheckpointRecorder`` keeps a small JSON checkpoint
up to date (finished nodes with their output, nodes still running, the latest analysis notes, the
lead's delegation reports and questions) and saves it next to the session. When the user then
sends "continue" (or any other message), ``build_resume_note`` turns the checkpoint into a block
of text put in front of the new message, so the lead picks the work up where it stopped.

The Claude/Codex CLI sessions are not reused across runs: they belong to one agent call and are
discarded when it is interrupted. The checkpoint is the durable memory instead.
"""

import re
import threading
import time
import unicodedata
from typing import Any, Callable, Dict, List, Optional

from agentdev.runtime.node.agent.team import clip_middle

STATE_RUNNING = "running"
STATE_INTERRUPTED = "interrupted"
STATE_COMPLETED = "completed"

MAX_NODES = 40
MAX_NODE_OUTPUT_CHARS = 1_500
MAX_NOTES = 6
MAX_NOTE_CHARS = 1_200
MAX_PROMPT_CHARS = 3_000
MAX_NOTE_SAVE_INTERVAL = 2.0  # seconds between saves caused by model-call notes
MAX_RESUME_CHARS = 9_000
MAX_REASON_CHARS = 300
MAX_TEAM_ENTRIES = 8
MAX_TEAM_TASK_CHARS = 250
MAX_TEAM_REPORT_CHARS = 900


def new_checkpoint(
    prompt: str,
    attachments: Optional[List[Any]] = None,
    previous: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """A checkpoint for a run that is starting.

    ``previous``: the interrupted checkpoint this run continues. Its finished nodes are carried over
    (``carried``), so a run interrupted twice still remembers what the first one did.
    """
    now = time.time()
    nodes: Dict[str, Any] = {}
    original = prompt
    if previous:
        for node_id, info in (previous.get("nodes") or {}).items():
            if isinstance(info, dict) and info.get("status") == "done":
                nodes[node_id] = {**info, "carried": True}
        # A resumed run keeps the request that started the work: "continue" says nothing by itself.
        original = previous.get("original_prompt") or previous.get("prompt") or prompt
    return {
        "version": 1,
        "state": STATE_RUNNING,
        "reason": "",
        "prompt": clip_middle(prompt or "", MAX_PROMPT_CHARS),
        "original_prompt": clip_middle(original or "", MAX_PROMPT_CHARS),
        "attachments": [str(a) for a in (attachments or [])][:20],
        "started_at": now,
        "updated_at": now,
        "nodes": nodes,
        "notes": list((previous or {}).get("notes") or [])[-MAX_NOTES:] if previous else [],
        "team": list((previous or {}).get("team") or []) if previous else [],
        "exchanges": list((previous or {}).get("exchanges") or []) if previous else [],
    }


def is_interrupted(checkpoint: Optional[Dict[str, Any]]) -> bool:
    return isinstance(checkpoint, dict) and checkpoint.get("state") == STATE_INTERRUPTED


class RunCheckpointRecorder:
    """Keeps a run's checkpoint up to date from its log events (thread-safe: nodes run in parallel)."""

    def __init__(
        self,
        checkpoint: Dict[str, Any],
        save: Callable[[Dict[str, Any]], None],
        team_source: Optional[Callable[[], Dict[str, List[Dict[str, str]]]]] = None,
    ) -> None:
        self.checkpoint = checkpoint
        self._save = save
        self._team_source = team_source
        self._lock = threading.Lock()
        self._last_note_save = 0.0

    def on_log(self, entry: Dict[str, Any]) -> None:
        """Feed one log entry (``LogEntry.to_dict()``); never raises (history is best effort)."""
        try:
            self._on_log(entry)
        except Exception:  # noqa: BLE001 - a broken checkpoint must not break the run
            pass

    def _on_log(self, entry: Dict[str, Any]) -> None:
        event = str(getattr(entry.get("event_type"), "value", entry.get("event_type")) or "")
        node_id = entry.get("node_id")
        details = entry.get("details") or {}
        if event not in ("NODE_START", "NODE_END", "MODEL_CALL") or not node_id:
            return
        with self._lock:
            cp = self.checkpoint
            nodes = cp["nodes"]
            if event == "NODE_START":
                nodes[node_id] = {"status": "running", "started_at": time.time()}
            elif event == "NODE_END":
                output = details.get("output")
                nodes[node_id] = {
                    "status": "done",
                    "output": clip_middle(str(output or ""), MAX_NODE_OUTPUT_CHARS),
                    "finished_at": time.time(),
                }
            else:
                text = details.get("output")
                if details.get("stage") != "after" or not isinstance(text, str) or not text.strip():
                    return
                notes = cp["notes"]
                notes.append({"node": node_id, "text": clip_middle(text.strip(), MAX_NOTE_CHARS)})
                del notes[:-MAX_NOTES]
                if time.time() - self._last_note_save < MAX_NOTE_SAVE_INTERVAL:
                    return
                self._last_note_save = time.time()
            while len(nodes) > MAX_NODES:
                nodes.pop(next(iter(nodes)))
            self._snapshot_team_locked()
            cp["updated_at"] = time.time()
            self._save(cp)

    def _snapshot_team_locked(self) -> None:
        if self._team_source is None:
            return
        try:
            team = self._team_source()
        except Exception:  # noqa: BLE001
            return
        if team.get("team"):
            self.checkpoint["team"] = team["team"]
        if team.get("exchanges"):
            self.checkpoint["exchanges"] = team["exchanges"]

    def finish(self, state: str, reason: str = "") -> Dict[str, Any]:
        """Close the checkpoint: ``completed`` or ``interrupted`` (with why it stopped)."""
        with self._lock:
            cp = self.checkpoint
            self._snapshot_team_locked()
            cp["state"] = state
            cp["reason"] = clip_middle(reason or "", MAX_REASON_CHARS)
            cp["updated_at"] = time.time()
            if state == STATE_INTERRUPTED:
                # A node still "running" when the run stopped was cut off: it has to be redone.
                for info in cp["nodes"].values():
                    if info.get("status") == "running":
                        info["status"] = "interrupted"
            return cp


# ------------------------------------------------------------------ "continue" intent

_FILLERS = frozenset(
    "di nhe nha a ha voi ban oi nao thoi giup minh em anh please pls plz thanks thank you ok okay now then "
    "and just lai cho toi".split()
)
_RESUME_PHRASES = (
    "tiep tuc", "lam tiep", "tiep di", "chay tiep", "tiep nao", "tiep nhe", "van tiep tuc", "di tiep",
    "resume", "continue", "go on", "keep going", "carry on", "pick up where you left off", "keep at it",
    "继续", "接着", "接着做", "继续做",
)
_MAX_RESUME_WORDS = 12


def _fold(text: str) -> str:
    """Lower-case, no accents, no punctuation: "Tiếp tục!" -> "tiep tuc"."""
    text = (text or "").lower().replace("đ", "d")
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return re.sub(r"[\s!.?,~:;()*^_\-\"'`]+", " ", text).strip()


def is_resume_intent(text: Optional[str]) -> bool:
    """True when a message just asks to carry on ("tiếp tục làm", "làm tiếp đi", "continue", "go on")."""
    folded = _fold(text or "")
    if not folded:
        return False
    words = folded.split()
    if len(words) > _MAX_RESUME_WORDS:
        return False
    core = " ".join(w for w in words if w not in _FILLERS)
    for phrase in _RESUME_PHRASES:
        cjk = not phrase.isascii()  # Chinese has no spaces between words
        if core == phrase or core.startswith(phrase if cjk else phrase + " "):
            return True
    return False


# ------------------------------------------------------------------ resume context

RESUME_HEADER = (
    "[RESUME: the previous run of this conversation was interrupted before it finished{reason}. "
    "Below is what was already done. Continue from there: do NOT start over, do NOT repeat finished "
    "steps or delegate again a task that already has a report, reuse these results and do only what "
    "is still missing.]"
)
RESUME_REQUESTED = (
    "[The user asked you to continue. Pick the interrupted task up now and deliver it; do not ask what to "
    "continue. If the message below adds an instruction, apply it to the same task.]"
)
RESUME_NOT_REQUESTED = (
    "[The user's new message below takes priority. If it is about the interrupted task, build on the "
    "work above; otherwise answer it and treat the unfinished task as background.]"
)


RESUME_FROM_TURN = (
    "[RESUME: the last turn above was interrupted before it finished. Continue it from what it already "
    "produced: do NOT start over and do NOT repeat finished steps or delegations.]"
)


def build_turn_resume_note(turns: Optional[List[Any]]) -> str:
    """For a "continue" in a session with no checkpoint (saved before checkpoints existed):
    the stored turn that was stopped is the only record of the work."""
    last = turns[-1] if turns else None
    if isinstance(last, dict) and last.get("status") in ("cancelled", "error"):
        return f"{RESUME_FROM_TURN}\n{RESUME_REQUESTED}"
    return ""


def _clip(text: Any, limit: int) -> str:
    return clip_middle(str(text or "").strip(), limit)


def build_resume_note(
    checkpoint: Optional[Dict[str, Any]],
    *,
    resume_requested: bool,
    include_team: bool = True,
) -> str:
    """The text put before the user's new message when the session has an interrupted run (else "")."""
    if not is_interrupted(checkpoint):
        return ""
    cp: Dict[str, Any] = checkpoint  # type: ignore[assignment]
    reason = _clip(cp.get("reason"), MAX_REASON_CHARS)
    lines = [RESUME_HEADER.format(reason=f" ({reason})" if reason else "")]
    original = _clip(cp.get("original_prompt") or cp.get("prompt"), MAX_PROMPT_CHARS)
    if original:
        lines.append(f"Original request being worked on: {original}")

    nodes = cp.get("nodes") or {}
    done = [(nid, n) for nid, n in nodes.items() if isinstance(n, dict) and n.get("status") == "done"]
    cut = [nid for nid, n in nodes.items() if isinstance(n, dict) and n.get("status") in ("running", "interrupted")]
    if done:
        lines.append(f"Steps already finished ({len(done)}):")
        for nid, info in done[-MAX_NODES:]:
            output = _clip(info.get("output"), MAX_NODE_OUTPUT_CHARS)
            lines.append(f"- {nid}: {output or '(no output)'}")
    if cut:
        lines.append("Cut off while running (redo these, using the notes below): " + ", ".join(cut))

    team = [e for e in cp.get("team") or [] if isinstance(e, dict) and e.get("member")]
    if include_team and team:
        lines.append("Reports already received from team members (do not delegate these again):")
        for entry in team[-MAX_TEAM_ENTRIES:]:
            lines.append(f"- {entry['member']}: {_clip(entry.get('task'), MAX_TEAM_TASK_CHARS)}")
            lines.append(f"  Report: {_clip(entry.get('report'), MAX_TEAM_REPORT_CHARS) or '(none)'}")

    for ex in (cp.get("exchanges") or [])[-4:]:
        if isinstance(ex, dict) and (ex.get("question") or ex.get("answer")) and ex.get("kind") != "delegation":
            lines.append(f"You asked: {_clip(ex.get('question'), 600)}")
            lines.append(f"User replied: {_clip(ex.get('answer'), 300)}")

    notes = [n for n in cp.get("notes") or [] if isinstance(n, dict) and n.get("text")]
    if notes:
        lines.append("Latest analysis / intermediate conclusions (most recent last):")
        for note in notes[-MAX_NOTES:]:
            lines.append(f"- [{note.get('node') or '?'}] {_clip(note.get('text'), MAX_NOTE_CHARS)}")

    body = clip_middle("\n".join(lines), MAX_RESUME_CHARS, head_ratio=0.5)
    return f"{body}\n{RESUME_REQUESTED if resume_requested else RESUME_NOT_REQUESTED}"
