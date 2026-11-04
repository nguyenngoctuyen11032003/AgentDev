"""Messages the user sends while a run is going (interjections), and the run's live progress.

Two small pieces of per-run state live in ``context.global_state``:

* ``RunProgress`` - which nodes are running / done and for how long, fed by the graph executor.
  A status question ("why so slow?") is answered from it instantly, without touching the team.
* ``RunInbox`` - the user's notes that are meant for the team. The lead agent takes them before its
  next model call (``take_for_lead``); running members see them read-only (``take_for_member``).

Nothing here interrupts a running model call: a note is picked up at the next safe point.
"""

from __future__ import annotations

import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Set, Tuple

from agentdev.runtime.node.agent.team import TeamState, detect_language

INBOX_KEY = "_run_inbox"
PROGRESS_KEY = "_run_progress"

KIND_STATUS = "status"
KIND_DIRECTIVE = "directive"

MAX_NOTE_CHARS = 4000
SLOW_NODE_SECONDS = 180


# ----------------------------------------------------------------------------- classification

def _fold(text: str) -> str:
    """Lower-case, no diacritics (also d-stroke): lets 'sao làm lâu vậy' and 'sao lam lau vay' match alike."""
    decomposed = unicodedata.normalize("NFD", (text or "").lower().replace("đ", "d"))
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


# A status question is short and asks about time / progress / state, not about the product itself.
_STATUS_PATTERNS = [re.compile(p) for p in (
    r"\b(sao|tai sao|sao ma)\b.*\b(lau|cham)\b",
    r"\blau (vay|the|qua|that)\b",
    r"\b(bao lau|con lau|may phut|bao giờ|bao gio)\b",
    r"\btien do\b",
    r"\b(dang|đang) lam (gi|j|toi dau|den dau)\b",
    r"\bdang lam gi\b",
    r"\b(lam|chay|xong) (toi|den) dau\b",
    r"\b(xong|hoan thanh|done) chua\b",
    r"\bchua xong\b",
    r"\bcap nhat (tinh hinh|tien do|trang thai)\b",
    r"\btinh hinh (the nao|sao|ra sao)\b",
    r"\b(how long|taking (so )?long|why (so )?slow|still (working|running)|any (progress|update))\b",
    r"\b(status|progress)\b( update| report)?\??$",
    r"\bwhat('?s| is| are) (you|the team|everyone|going on)\b.*\b(doing|status|progress)\b",
    r"\b(are you|is it|is this) (done|finished|stuck)\b",
    r"\bhow('?s| is) it going\b",
)] + [re.compile(p) for p in ("进度", "多久", "好了吗", "完成了吗", "还没", "怎么这么慢", "在做什么")]

_MAX_STATUS_WORDS = 14


def classify_note(text: str) -> str:
    """``status`` for a short question about progress, otherwise ``directive`` (new info, a request, a complaint)."""
    raw = (text or "").strip()
    if not raw:
        return KIND_DIRECTIVE
    folded = _fold(raw)
    if len(folded.split()) > _MAX_STATUS_WORDS and not any(ord(c) > 0x2E80 for c in raw):
        return KIND_DIRECTIVE
    for pattern in _STATUS_PATTERNS:
        if pattern.search(folded) or pattern.search(raw):
            return KIND_STATUS
    return KIND_DIRECTIVE


# ----------------------------------------------------------------------------- progress

@dataclass
class NodeProgress:
    node_id: str
    started_at: float
    delegated_by: str = ""
    ended_at: Optional[float] = None
    failed: bool = False

    @property
    def running(self) -> bool:
        return self.ended_at is None


class RunProgress:
    """Thread-safe record of which nodes ran, are running, and how long they took."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.RLock()
        self.started_at = clock()
        self._nodes: Dict[str, NodeProgress] = {}
        self._order: List[str] = []

    def start(self, node_id: str, delegated_by: str = "") -> None:
        with self._lock:
            self._nodes[node_id] = NodeProgress(node_id, self._clock(), delegated_by or "")
            if node_id in self._order:
                self._order.remove(node_id)
            self._order.append(node_id)

    def finish(self, node_id: str, failed: bool = False) -> None:
        with self._lock:
            node = self._nodes.get(node_id)
            if node is not None and node.running:
                node.ended_at = self._clock()
                node.failed = failed

    def snapshot(self) -> Dict[str, Any]:
        now = self._clock()
        with self._lock:
            nodes = [self._nodes[n] for n in self._order]
        running = [
            {"node": n.node_id, "seconds": max(0, int(now - n.started_at)), "delegated_by": n.delegated_by}
            for n in nodes if n.running
        ]
        done = [
            {"node": n.node_id, "seconds": max(0, int((n.ended_at or now) - n.started_at)), "failed": n.failed,
             "delegated_by": n.delegated_by}
            for n in nodes if not n.running
        ]
        return {"elapsed": max(0, int(now - self.started_at)), "running": running, "done": done}


def get_run_progress(global_state: Dict[str, Any]) -> RunProgress:
    progress = global_state.get(PROGRESS_KEY)
    if not isinstance(progress, RunProgress):
        progress = RunProgress()
        global_state[PROGRESS_KEY] = progress
    return progress


# ----------------------------------------------------------------------------- inbox

@dataclass
class Note:
    id: str
    text: str
    at: float
    kind: str = KIND_DIRECTIVE
    lead_took: bool = False
    seen_by: Set[str] = field(default_factory=set)


class RunInbox:
    """The user's mid-run notes for the team."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._notes: List[Note] = []
        # Called as ``on_event(message_dict)`` (from any thread) when a note reaches the lead.
        self.on_event: Optional[Callable[[Dict[str, Any]], None]] = None

    def post(self, text: str, note_id: str = "", kind: str = KIND_DIRECTIVE) -> Note:
        clean = (text or "").strip()[:MAX_NOTE_CHARS]
        with self._lock:
            note = Note(id=note_id or f"note-{len(self._notes) + 1}", text=clean, at=time.time(), kind=kind)
            self._notes.append(note)
        return note

    def pending(self) -> List[Note]:
        """Notes the lead has not taken yet."""
        with self._lock:
            return [n for n in self._notes if not n.lead_took]

    def has_pending(self) -> bool:
        with self._lock:
            return any(not n.lead_took for n in self._notes)

    def take_for_lead(self, node_id: str) -> List[Note]:
        with self._lock:
            taken = [n for n in self._notes if not n.lead_took]
            for note in taken:
                note.lead_took = True
                note.seen_by.add(node_id)
        callback = self.on_event
        if callback is not None:
            for note in taken:
                try:
                    callback({"type": "interject_applied", "data": {"note_id": note.id, "node": node_id}})
                except Exception:  # a failed notification must not break the agent's turn
                    pass
        return taken

    def take_for_member(self, node_id: str) -> List[Note]:
        """Notes a running member has not seen yet (it never consumes them: the lead still gets them)."""
        with self._lock:
            fresh = [n for n in self._notes if node_id not in n.seen_by]
            for note in fresh:
                note.seen_by.add(node_id)
        return fresh


def get_run_inbox(global_state: Dict[str, Any]) -> RunInbox:
    inbox = global_state.get(INBOX_KEY)
    if not isinstance(inbox, RunInbox):
        inbox = RunInbox()
        global_state[INBOX_KEY] = inbox
    return inbox


def lead_injection(notes: List[Note]) -> str:
    """The user message the lead sees at its next model call."""
    body = "\n".join(f"- {n.text}" for n in notes)
    return (
        "[The user wrote this while you and your team were working. It is NOT a new task from scratch.]\n"
        f"{body}\n\n"
        "Take it into account now: if it adds or changes requirements, adjust your plan and give the affected "
        "members follow-up work; if it points out a problem, have it checked and fixed; if it is a question, "
        "answer it from what the team has actually done so far. Do not redo work that is already correct. "
        "Reply in the user's language and say in one or two sentences what you will do about it."
    )


def member_injection(notes: List[Note]) -> str:
    """The read-only heads-up a running member sees."""
    body = "\n".join(f"- {n.text}" for n in notes)
    return (
        "[Note from the user, sent while you were working (relayed by your lead)]\n"
        f"{body}\n\n"
        "Apply it only if it concerns your current task; otherwise ignore it and keep going. "
        "Do not change your scope on your own: mention anything else in your report to your lead."
    )


# ----------------------------------------------------------------------------- status reply

def _duration(seconds: int, lang: str) -> str:
    minutes, secs = divmod(max(0, int(seconds)), 60)
    if lang == "Vietnamese":
        return f"{minutes} phút {secs} giây" if minutes else f"{secs} giây"
    if lang == "Chinese":
        return f"{minutes}分{secs}秒" if minutes else f"{secs}秒"
    return f"{minutes}m {secs}s" if minutes else f"{secs}s"


def _task_line(text: str, limit: int = 90) -> str:
    line = " ".join(str(text or "").split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


_TEXTS: Dict[str, Dict[str, str]] = {
    "Vietnamese": {
        "head": "{lead} báo cáo tiến độ: đội đã chạy {elapsed}.",
        "running": "Đang làm",
        "done": "Đã xong",
        "none_running": "Hiện chưa có agent nào đang chạy.",
        "waiting": "Đội đang chờ bạn trả lời một câu hỏi.",
        "slow": "{node} đã chạy {time}, hơi lâu hơn thường lệ; đội vẫn đang làm và mình không dừng lượt chạy.",
        "delegated": "Việc đã giao",
        "failed": "lỗi",
        "ok": "xong",
        "inbox": "Còn {n} ghi chú của bạn đang chờ được áp dụng.",
        "ack": "Đã nhận ghi chú của bạn, mình chuyển cho {lead} và sẽ áp dụng ở bước kế tiếp, không dừng việc đang chạy.",
        "now": "Hiện tại",
        "idle": "đội đang chuẩn bị",
    },
    "English": {
        "head": "{lead} status: the team has been running for {elapsed}.",
        "running": "Working now",
        "done": "Done",
        "none_running": "No agent is running right now.",
        "waiting": "The team is waiting for your answer to a question.",
        "slow": "{node} has been running for {time}, a bit longer than usual; the team is still working and the run is not stopped.",
        "delegated": "Delegated work",
        "failed": "failed",
        "ok": "done",
        "inbox": "{n} of your notes are still waiting to be applied.",
        "ack": "Got your note. I passed it to {lead}; it is applied at the next step and nothing that is running is interrupted.",
        "now": "Right now",
        "idle": "the team is getting ready",
    },
    "Chinese": {
        "head": "{lead} 进度汇报：团队已运行 {elapsed}。",
        "running": "正在进行",
        "done": "已完成",
        "none_running": "目前没有正在运行的 agent。",
        "waiting": "团队正在等待你回答一个问题。",
        "slow": "{node} 已运行 {time}，比平时久一些；团队仍在工作，运行没有被中断。",
        "delegated": "已分派的工作",
        "failed": "失败",
        "ok": "完成",
        "inbox": "你还有 {n} 条备注等待应用。",
        "ack": "已收到你的备注，已转交给 {lead}，将在下一步应用，不会打断正在进行的工作。",
        "now": "当前",
        "idle": "团队正在准备",
    },
}


def _texts(lang: str) -> Dict[str, str]:
    return _TEXTS.get(lang) or _TEXTS["English"]


def pick_language(text: str, hint: str = "") -> str:
    """Language of the reply: the note's own, else the UI locale ``hint`` (vi/en/zh), else English."""
    detected = detect_language(text)
    if detected in _TEXTS:
        return detected
    code = (hint or "").lower()[:2]
    return {"vi": "Vietnamese", "zh": "Chinese"}.get(code, "English")


def _member_log(global_state: Mapping[str, Any]) -> List[Dict[str, str]]:
    state = global_state.get("_team_state")
    if not isinstance(state, TeamState):
        return []
    with state.lock:
        return [dict(item) for item in state.log]


def build_status(global_state: Mapping[str, Any], *, lead: str, lang: str, waiting: bool = False,
                 brief: bool = False, pending_notes: int = 0) -> str:
    """Plain-text status from the run's real progress (no model call).

    ``brief`` is the one-liner appended to an acknowledgement; otherwise the full report.
    """
    t = _texts(lang)
    progress = global_state.get(PROGRESS_KEY)
    snap = progress.snapshot() if isinstance(progress, RunProgress) else {"elapsed": 0, "running": [], "done": []}
    running = snap["running"]
    done = snap["done"]

    running_text = ", ".join(f"{r['node']} ({_duration(r['seconds'], lang)})" for r in running)
    if brief:
        if running_text:
            return f"{t['now']}: {running_text}."
        return f"{t['now']}: {t['idle'] if not done else t['none_running']}"

    lines = [t["head"].format(lead=lead or "Lead", elapsed=_duration(snap["elapsed"], lang))]
    lines.append(f"- {t['running']}: {running_text}" if running_text else f"- {t['none_running']}")
    if done:
        names = ", ".join(
            f"{d['node']} ({_duration(d['seconds'], lang)}{', ' + t['failed'] if d['failed'] else ''})" for d in done
        )
        lines.append(f"- {t['done']}: {names}")
    work = _member_log(global_state)
    if work:
        lines.append(f"- {t['delegated']}:")
        for entry in work[-6:]:
            report = str(entry.get("report") or "")
            mark = t["failed"] if report.startswith("[failed") else t["ok"]
            lines.append(f"  - {entry.get('member', '')}: {_task_line(entry.get('task', ''))} ({mark})")
    slow = max(running, key=lambda r: r["seconds"], default=None)
    if slow is not None and slow["seconds"] >= SLOW_NODE_SECONDS:
        lines.append(t["slow"].format(node=slow["node"], time=_duration(slow["seconds"], lang)))
    if waiting:
        lines.append(t["waiting"])
    if pending_notes:
        lines.append(t["inbox"].format(n=pending_notes))
    return "\n".join(lines)


def build_ack(global_state: Mapping[str, Any], *, lead: str, lang: str, waiting: bool = False) -> str:
    t = _texts(lang)
    parts = [t["ack"].format(lead=lead or "Lead"), build_status(global_state, lead=lead, lang=lang, brief=True)]
    if waiting:
        parts.append(t["waiting"])
    return " ".join(parts)


def route_note(text: str, global_state: Dict[str, Any], *, note_id: str, lead: str, locale: str = "",
               waiting: bool = False) -> Tuple[str, str, Optional[Note]]:
    """Handle one note: returns ``(kind, reply_text, note)``; ``note`` is None for a pure status question."""
    kind = classify_note(text)
    lang = pick_language(text, locale)
    if kind == KIND_STATUS:
        inbox = global_state.get(INBOX_KEY)
        pending = len(inbox.pending()) if isinstance(inbox, RunInbox) else 0
        return kind, build_status(global_state, lead=lead, lang=lang, waiting=waiting, pending_notes=pending), None
    note = get_run_inbox(global_state).post(text, note_id=note_id, kind=kind)
    return kind, build_ack(global_state, lead=lead, lang=lang, waiting=waiting), note
