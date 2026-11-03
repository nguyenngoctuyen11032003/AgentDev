"""Team lead orchestration: a lead agent (CTO / PM / CEO) delegates work to member agents.

The user only talks to the lead. The lead decides at run time who to call, how often and in
what order through the ``delegate_task`` tool (one member) or ``delegate_parallel`` (several
independent tasks at once), asks the user through ``ask_user`` when a decision is theirs, and
finally answers the user itself. Members are ordinary agent nodes of
the same workflow; they run through the graph's delegate runner so every view (office, tasks,
overview) still sees their NODE_START / NODE_END events, tagged with ``delegated_by``.
"""

from __future__ import annotations

import contextvars
import os
import re
import threading
from concurrent.futures import FIRST_COMPLETED, CancelledError, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Set, Tuple

from agentdev.entity.messages import Message, MessageRole
from agentdev.entity.tool_spec import ToolSpec
from agentdev.utils.exceptions import WorkflowCancelledError

TEAM_TOOL_SOURCE = "agent_team_internal"
DELEGATE_TOOL = "delegate_task"
DELEGATE_PARALLEL_TOOL = "delegate_parallel"
ASK_USER_TOOL = "ask_user"
# Offered to the top-level lead when its team has ``plan_approval``: hands a plan to the user and
# ends the lead's turn in code (see AgentNodeExecutor._handle_tool_calls), so no team work starts
# before the user approves.
SUBMIT_PLAN_TOOL = "submit_plan"
# ``global_state`` key set when the lead submitted a plan: {"node", "summary", "plan"}.
PLAN_PENDING_KEY = "plan_pending"
# WebSocket message type sent to the session when a plan is submitted.
PLAN_PROPOSED_EVENT = "plan_proposed"
# Refusal for team work requested after (or together with) a submitted plan in the same reply.
PLAN_GATE_REFUSAL = (
    "Not run: you submitted a plan in this turn. Team work starts only after the user approves the plan "
    "(their next message)."
)
# A member's report as the lead sees it; the full text stays in the team state (``log`` / ``history``).
MAX_MEMBER_RESULT_CHARS = 4_000
# The one earlier report repeated in a member's brief.
MAX_HISTORY_CHARS = 1_000
# Member runs allowed in one run across ALL leads (top lead + sub-leads), so nested teams cannot
# multiply their own limits (20 x 25 x 10). Overridable per run (``global_state``) or by env var.
DEFAULT_MAX_MEMBER_RUNS = 40
MAX_MEMBER_RUNS_KEY = "team_max_member_runs"
MAX_MEMBER_RUNS_ENV = "AGENTDEV_TEAM_MAX_MEMBER_RUNS"
# How often a parallel delegation checks the cancel event while waiting for its members.
CANCEL_POLL_SECONDS = 0.2
MAX_DELEGATION_DEPTH = 3

# Workers start their answer with this when only the user can decide something.
DECISION_MARKER = "DECISION NEEDED:"
# A member whose model call failed answers with this (see AgentNodeExecutor.execute).
MODEL_ERROR_PREFIX = "MODEL ERROR:"
# Start of the header that introduces the user's newest message in a follow-up run's input
# (conversation_turns.NEW_MESSAGE_HEADER starts with it).
NEW_MESSAGE_MARKER = "[The user's NEW message"

# Digest of the delegations of one run, kept with the conversation turn for later turns.
MAX_DIGEST_ENTRIES = 8
MAX_DIGEST_TASK_CHARS = 300
MAX_DIGEST_REPORT_CHARS = 1_200
# Reports of a member from earlier turns of the conversation repeated in its brief.
MAX_EARLIER_TURN_REPORTS = 2

DelegateRunner = Callable[[str, List[Message], str], List[Message]]

# ``global_state`` key holding the session's earlier turns (list of turn dicts), set by the run's caller.
CONVERSATION_TURNS_KEY = "conversation_turns"
# ``kind`` of the delegation entries ``user_exchanges`` appends after the user exchanges.
DELEGATION_KIND = "delegation"

# Nesting depth of the current delegation chain (lead -> member that is itself a lead -> ...).
# A context variable rather than a shared counter: parallel members each run in a worker thread
# with a copy of the caller's context, so siblings never add to each other's depth.
_DELEGATION_DEPTH: contextvars.ContextVar[int] = contextvars.ContextVar("agentdev_delegation_depth", default=0)


@dataclass
class TeamMember:
    node_id: str
    title: str
    summary: str
    # Members this member leads in turn (a sub-lead such as a PM), so the top lead can route named work.
    manages: tuple = ()
    # Skills ticked on the member (e.g. a frontend skill), so the lead routes work to the right specialist.
    skills: tuple = ()


@dataclass
class TeamState:
    """Per-run bookkeeping shared by all leads (kept in ``context.global_state``).

    Thread-safe: parallel delegations read and write it from worker threads.
    """

    history: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    running: Set[str] = field(default_factory=set)
    # Questions leads asked the user during this run and the answers ({"question", "answer"}),
    # kept so the next turn of the conversation still knows what the user decided.
    exchanges: List[Dict[str, str]] = field(default_factory=list)
    # Every delegation of this run in order ({"member", "task", "report"}), for the turn digest.
    log: List[Dict[str, str]] = field(default_factory=list)
    # Members' tasks and reports from earlier turns of the conversation (seeded from the turns).
    earlier: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    # Language of the user's newest message ("Vietnamese", "English", "Chinese", "Japanese", "Korean");
    # "" when unknown.
    user_language: str = ""
    # The newest user message as the lead saw it (``set_user_language``), for the small-talk fast path.
    user_message: str = ""
    # Shared member-run budget of the whole run (all leads together).
    max_member_runs: int = DEFAULT_MAX_MEMBER_RUNS
    member_runs: int = 0
    # The run's cancel event (threading.Event), when the caller provides one.
    cancel_event: Any = field(default=None, repr=False, compare=False)
    # Returns the run's account switches after a usage limit ({exhausted connection: replacement}).
    account_switches: Optional[Callable[[], Dict[str, str]]] = field(default=None, repr=False, compare=False)
    lock: Any = field(default_factory=threading.RLock, repr=False, compare=False)

    @property
    def depth(self) -> int:
        """Delegation depth of the calling chain (per call chain, not per run)."""
        return _DELEGATION_DEPTH.get()

    def add_exchange(self, question: str, answer: str) -> None:
        with self.lock:
            self.exchanges.append({"question": question, "answer": answer})

    def add_report(self, member: str, task: str, report: str) -> None:
        with self.lock:
            self.history.setdefault(member, []).append({"task": task, "report": report})
            self.log.append({"member": member, "task": task, "report": report})

    def recent(self, member: str, count: int = 2) -> List[Dict[str, str]]:
        with self.lock:
            return list(self.history.get(member) or [])[-count:]

    def earlier_reports(self, member: str, count: int = MAX_EARLIER_TURN_REPORTS) -> List[Dict[str, str]]:
        with self.lock:
            return list(self.earlier.get(member) or [])[-count:]

    def set_user_language(self, text: str) -> None:
        """Set the language from ``text``; a too short / ambiguous text keeps the current language."""
        with self.lock:
            self.user_message = (text or "").strip()
        language = detect_language(text)
        if language:
            with self.lock:
                self.user_language = language

    def log_failure(self, member: str, task: str, reason: str) -> None:
        """Record a delegation that produced no report (in ``log`` for the digest, not in ``history``)."""
        with self.lock:
            self.log.append({"member": member, "task": task, "report": f"[failed] {reason}"})

    def reserve_member_runs(self, count: int) -> None:
        """Count ``count`` member runs against the run-wide budget, all or nothing."""
        with self.lock:
            left = self.max_member_runs - self.member_runs
            if left <= 0 or count > left:
                raise ValueError(
                    f"Team budget exhausted: this run already used {self.member_runs} of its "
                    f"{self.max_member_runs} member runs (shared by all leads)"
                    + (f"; {count} more were requested but only {left} remain" if left > 0 else "")
                    + ". Do not delegate any more: finish with what you have and report the current status, "
                    "including what is still open."
                )
            self.member_runs += count

    def refund_member_runs(self, count: int) -> None:
        with self.lock:
            self.member_runs = max(0, self.member_runs - count)

    def member_runs_left(self) -> int:
        with self.lock:
            return self.max_member_runs - self.member_runs

    def is_cancelled(self) -> bool:
        event = self.cancel_event
        return bool(event is not None and event.is_set())

    def seed_earlier_turns(self, turns: Any) -> None:
        """Remember what each member did in earlier turns (the ``team`` digest of each turn)."""
        if not isinstance(turns, list):
            return
        with self.lock:
            for turn in turns:
                entries = turn.get("team") if isinstance(turn, Mapping) else None
                for entry in entries if isinstance(entries, list) else []:
                    if isinstance(entry, Mapping) and entry.get("member"):
                        self.earlier.setdefault(str(entry["member"]), []).append(
                            {"task": str(entry.get("task") or ""), "report": str(entry.get("report") or "")}
                        )

    def claim(self, member: str) -> bool:
        """Mark a member busy; False when it is already running (a node's state is not reentrant)."""
        with self.lock:
            if member in self.running:
                return False
            self.running.add(member)
            return True

    def release(self, member: str) -> None:
        with self.lock:
            self.running.discard(member)


@contextmanager
def _nested_delegation() -> Iterator[None]:
    token = _DELEGATION_DEPTH.set(_DELEGATION_DEPTH.get() + 1)
    try:
        yield
    finally:
        _DELEGATION_DEPTH.reset(token)


def _first_line(text: Optional[str], limit: int = 220) -> str:
    for line in (text or "").splitlines():
        line = line.strip().lstrip("#").strip()
        if line:
            return line if len(line) <= limit else line[: limit - 1] + "…"
    return ""


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    head = text[: limit // 2]
    tail = text[-limit // 2 :]
    return f"{head}\n\n[… {len(text) - limit} characters omitted …]\n\n{tail}"


def clip_middle(text: Optional[str], limit: int, head_ratio: float = 0.6) -> str:
    """At most ``limit`` chars of ``text``: its start (``head_ratio`` of the room) and its end."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    marker = f" […{len(text) - limit} chars omitted…] "
    room = max(limit - len(marker), 2)
    head = int(room * head_ratio)
    tail = room - head
    return text[:head].rstrip() + marker + (text[len(text) - tail:].lstrip() if tail > 0 else "")


# Letters only Vietnamese uses (besides the tone-marked ones in U+1EA0..U+1EF9).
_VIETNAMESE_LETTERS = set("ăâđêôơưĂÂĐÊÔƠƯàáảãạèéẻẽẹìíỉĩịòóỏõọùúủũụỳýỷỹỵÀÁÃÈÉÌÍÒÓÕÙÚÝ")
# Frequent Vietnamese words typed without diacritics ("toi muon lam web ban hang").
_VIETNAMESE_PLAIN_WORDS = frozenset(
    "toi ban khong ko dc duoc lam cho voi nhung cua la mot cac nay thi va de minh giup sua loi "
    "muon hang them xoa tao viet trang roi chua nao gi sao vay nhe nha oi anh em chi bao nhieu "
    "dang nhap xuat tim kiem cai dat chay xem hay nen phai neu khi trong ngoai tren duoi hon nua lai "
    "den tu ra vao biet hieu giao dien du tinh nang chuc".split()
)
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
# Below this many words an unaccented Latin text ("ok", "go ahead") says little about the language.
_MIN_LATIN_WORDS = 3
_VIETNAMESE_RATIO = 0.3


def _is_vietnamese_char(ch: str) -> bool:
    return 0x1EA0 <= ord(ch) <= 0x1EF9 or ch in _VIETNAMESE_LETTERS


def _is_cjk_char(ch: str) -> bool:
    code = ord(ch)
    return 0x3040 <= code <= 0x31FF or 0x3400 <= code <= 0x9FFF or 0xAC00 <= code <= 0xD7AF or 0xFF66 <= code <= 0xFF9D


def detect_language(text: Optional[str]) -> str:
    """Guess the language of ``text``: "Vietnamese", "English", "Chinese", "Japanese", "Korean" or "".

    "" means unknown: no letters, or a short unaccented text ("ok", "go ahead") that could be any
    Latin-script language. Vietnamese is recognised by the share of Vietnamese words (accented, or
    common words typed without diacritics), so one accented name in an English sentence stays English.
    """
    text = text or ""
    kana = hangul = han = 0
    for ch in text:
        code = ord(ch)
        if 0x3040 <= code <= 0x30FF or 0x31F0 <= code <= 0x31FF or 0xFF66 <= code <= 0xFF9D:
            kana += 1
        elif 0xAC00 <= code <= 0xD7AF or 0x1100 <= code <= 0x11FF or 0x3130 <= code <= 0x318F:
            hangul += 1
        elif 0x4E00 <= code <= 0x9FFF or 0x3400 <= code <= 0x4DBF:
            han += 1
    words = [w.lower() for w in _WORD_RE.findall(text) if not any(_is_cjk_char(c) for c in w)]
    cjk = kana + hangul + han
    # CJK text is dense: one character weighs about as much as a short Latin word.
    if cjk and cjk >= len(words):
        if hangul and hangul >= kana:
            return "Korean"
        if kana:
            return "Japanese"
        return "Chinese"
    if not words:
        return ""
    accented = sum(1 for w in words if any(_is_vietnamese_char(c) for c in w))
    plain = sum(1 for w in words if w in _VIETNAMESE_PLAIN_WORDS)
    if (accented + plain) / len(words) >= _VIETNAMESE_RATIO and (accented + plain) >= 2:
        return "Vietnamese"
    if accented and len(words) == 1:
        return "Vietnamese"
    if len(words) < _MIN_LATIN_WORDS and not accented:
        return ""
    return "English"


_EARLIER_USER_PREFIXES = ("User: ", "User replied: ")


def latest_user_message(text: Optional[str]) -> str:
    """The text to detect the user's language from: the newest message in a lead's input.

    In a follow-up run that is the part after the new-message header. When it is too short or
    ambiguous ("ok"), the user's latest earlier message with a clear language is returned instead
    (the previous turn's language is kept), never the whole transcript with the assistant's answers.
    """
    text = text or ""
    start = text.rfind(NEW_MESSAGE_MARKER)
    if start < 0:
        return text
    end = text.find("]", start)
    latest = text[end + 1:] if end >= 0 else text[start:]
    if detect_language(latest):
        return latest
    for line in reversed(text[:start].splitlines()):
        for prefix in _EARLIER_USER_PREFIXES:
            if line.startswith(prefix) and detect_language(line[len(prefix):]):
                return line[len(prefix):]
    return latest


# Whole messages that are only a greeting / thanks / goodbye: the lead answers them without its team.
_SMALL_TALK_PHRASES = frozenset(
    "hi|hello|hey|hiya|yo|good morning|good afternoon|good evening|thanks|thank you|thank you so much|"
    "thanks a lot|thx|ty|bye|goodbye|see you|chào|xin chào|chào bạn|chào anh|chào chị|chào em|hello bạn|"
    "hi bạn|chao|xin chao|chao ban|cảm ơn|cám ơn|cảm ơn bạn|cảm ơn nhé|cảm ơn nha|cảm ơn nhiều|cam on|"
    "cam on ban|thanks bạn|tạm biệt|bye bạn|tam biet|こんにちは|ありがとう|ありがとうございます|你好|谢谢|"
    "안녕하세요|감사합니다".split("|")
)
_SMALL_TALK_STRIP = re.compile(r"[\s!.?,~:;()*^_-]+|[\U0001F300-\U0001FAFF\u2600-\u27BF]+")


def is_small_talk(text: Optional[str]) -> bool:
    """True when ``text`` is only a greeting or thanks ("hi", "xin chào!", "cảm ơn nhé 🙏").

    Deliberately narrow: approvals ("ok", "làm đi"), questions and anything with a request in it
    return False, so they keep the full lead protocol and the team tools.
    """
    words = _SMALL_TALK_STRIP.sub(" ", (text or "").lower()).split()
    return 0 < len(words) <= 4 and " ".join(words) in _SMALL_TALK_PHRASES


def team_digest(state: Any) -> List[Dict[str, str]]:
    """The last delegations of a run, clipped: ``{"member", "task", "report"}`` per entry."""
    if not isinstance(state, TeamState):
        return []
    with state.lock:
        entries = list(state.log)[-MAX_DIGEST_ENTRIES:]
    return [
        {
            "member": entry["member"],
            "task": clip_middle(entry.get("task"), MAX_DIGEST_TASK_CHARS, head_ratio=1.0),
            "report": clip_middle(entry.get("report"), MAX_DIGEST_REPORT_CHARS),
        }
        for entry in entries
    ]


def resolve_members(lead_id: str, team_members: List[str], nodes: Mapping[str, Any]) -> List[TeamMember]:
    """Members listed in config, or every agent node without edges (staff nodes)."""
    if team_members:
        ids = [m for m in team_members if m != lead_id]
    else:
        ids = [
            node_id
            for node_id, node in nodes.items()
            if node_id != lead_id
            and getattr(node, "node_type", None) == "agent"
            and not getattr(node, "predecessors", None)
            and not getattr(node, "successors", None)
        ]
    members: List[TeamMember] = []
    for node_id in ids:
        node = nodes.get(node_id)
        if node is None or getattr(node, "node_type", None) != "agent":
            continue
        description = getattr(node, "description", None) or ""
        role = getattr(node, "role", None) or ""
        # Role and task description both shape what a member is good at: the lead routes on both.
        lines = dict.fromkeys(line for line in (_first_line(role, 120), _first_line(description, 160)) if line)
        members.append(
            TeamMember(
                node_id=node_id,
                title=node_id,
                summary=" | ".join(lines) or "General team member",
                manages=tuple(_sub_team(node_id, node, nodes)),
                skills=tuple(_member_skills(node)),
            )
        )
    return members


def _member_skills(node: Any) -> List[str]:
    """Names of the skills ticked on a member (empty when skills are off or every skill is allowed)."""
    skills = getattr(getattr(node, "config", None), "skills", None)
    if not skills or not getattr(skills, "enabled", False):
        return []
    return [name for name in (getattr(skills, "allow", None) or []) if isinstance(name, str) and name]


def _sub_team(node_id: str, node: Any, nodes: Mapping[str, Any]) -> List[str]:
    """Explicit members of a member that is itself a team lead (empty for ordinary members)."""
    config = getattr(node, "config", None)
    team = getattr(config, "team", None)
    if not team or not getattr(team, "enabled", False):
        return []
    return [m for m in (getattr(team, "members", None) or []) if m != node_id and m in nodes]


LEAD_PROTOCOL = """\
# You lead a team
The user is your client. They talk ONLY to you; your team members never talk to the user.

## First, classify the message (silently) and act on it
(a) Question, greeting or small talk, advice ("X vs Y?", "how does Z work?"), or anything you can answer well yourself (an explanation, a question about earlier work, a short review): answer it yourself, right away: no delegation, no plan (delegate only when the work needs a member's role or tools; otherwise answer directly). Keep it short (a greeting: 1-3 sentences).
(b) Bug fix or small, clear change (one function, a config, a text or style tweak): no plan, no approval round. Look at the relevant files if a project is attached, then delegate it directly to the right specialist (a bug: the fixer, with symptom, likely files and how to reproduce; then the tester verifies it, skipped only for a text or style tweak), or do it yourself if it needs no member.
(c) New project or significant new feature: see the plan rule below.
- "Can you build X?": say yes (or what is not possible) and propose a concrete default in a few lines (what you would build, key features, stack) so the user can just say "ok".
- Work on an existing project (attached files or a project folder): look at the relevant files with your read tools BEFORE planning or delegating, and base the plan and briefs on what is really there.
- Follow-up message: decisions, plans and answers in the earlier conversation still stand, and "What the team did" there lists your members' earlier work. If your last answer proposed a plan or asked a question and the user now approves ("ok", "đồng ý", "duyệt", "go ahead"…) or answers it, act on it immediately, with the changes they asked for — do not re-plan or ask for approval again. Never re-delegate work already done unless the user asks to redo or change it.

## How you work
1. Fill gaps with sensible, industry-standard defaults and state them as assumptions the user can change, instead of asking about each one. Questions you have before starting go at the end of your answer (with the plan, each with your recommended default). Use `ask_user` only for a genuine decision you cannot assume: the request itself can mean very different things and a wrong guess would waste the team's work, or a member needs a choice only the user can make. One short question with your recommended answer.
2. Decide yourself who does what, in which order, and how many times. Do not call members the task does not need (a one-line fix does not need the whole team). If the request or your brief names a specific person ("ask the QA Tester…"), that person does the work: delegate to them if they are on your team, otherwise to the member who leads them and say in the brief who must do it. Never do a named person's work yourself.
3. Delegate with `delegate_task`. Give each member a self-contained brief: goal, relevant context and earlier results, constraints (stack, files, conventions), and what to hand back. Members do not see this conversation. Scope the brief to what the user asked (plus normal quality); do not add requirements of your own, and judge results against the user's request, not extras.
{parallel_rule}4. Chain work through yourself: pass one member's result to the next (e.g. analysis → fix → test → acceptance review). If a review or test fails, send it back for a fix, at most {max_rounds} rounds, then report the situation to the user.
5. When a member's reply starts with "{marker}", only the user can decide: ask them with `ask_user` (the options and your recommendation), then continue.
6. Finish with ONE short report to the user: the outcome in the first line, then only what applies — what was done, result/checks (tests, QA), files, open issues or next step. Do not paste members' output.
Member reports reach you clipped to about {report_chars} characters (the full text is kept); if you need a detail that was cut, ask that member for exactly that detail.

## Rules
- The user's technology choices are binding. If one is clearly wrong for the goal, say so with reasons and a better option, and let the user decide — never silently switch.
- {plan_rule}
- Report only what members actually produced; if something failed (a member error, an account usage limit) or was not checked, say so plainly.
- No process narration ("I will now call…"), no internal tool, node or model names.
- You have at most {max_delegations} delegations for this request, and the whole team (sub-teams included) shares a budget of {max_member_runs} member runs per request; plan accordingly.
{language_rule}
## Your team
{roster}
"""

# The lead's whole team section for a message that is only a greeting or thanks (``is_small_talk``):
# no protocol, roster or team tools, so the reply is fast and cheap.
LEAD_SMALL_TALK = """\
# You lead a team
The user's message is a greeting or thanks. Reply yourself in 1-2 short sentences, in its language; no team work.
"""

PLAN_RULE_ON = (
    "Plan rule — only for (c) a NEW project or significant new feature, not approved yet: do not build anything, "
    "do not delegate and do not use `ask_user` for it. END YOUR TURN with a concise plan: write it in markdown — "
    "goal, scope, stack, the steps with which member does what, risks and open questions each with your "
    "recommended default — and call `submit_plan` with it instead of delegating. That ends your turn: the plan is "
    "shown to the user for approval and their next message continues from it. Skip the plan when the user already "
    "approved (now or earlier in the conversation) or said to go ahead (\"làm luôn\", \"just do it\", "
    "\"go ahead\"), and for small tasks, bug fixes and questions: those go straight to work."
)
PLAN_RULE_OFF = "Proceed without asking for plan approval; ask the user only for real decisions."

PARALLEL_RULE = (
    "   When several tasks are INDEPENDENT (no task needs another's result and they do not edit the same files), "
    "hand them out at once with `delegate_parallel` — up to {max_parallel} members work at the same time, each "
    "member at most once per call (e.g. backend API + frontend page + data pipeline against an agreed contract). "
    "Agree on shared interfaces first and put them in every brief. Dependent steps (build → test → review) stay "
    "sequential with `delegate_task`. Every task counts as one delegation.\n"
)

MEMBER_PROTOCOL = """\
# You are a member of a team
Your lead ({lead}) assigns you tasks. Do exactly the task in the brief, the way your role and task description define, applying every one of your skills that matches the task (load it first), and report back to the lead.
- Report: what you did, the result (files changed, findings, test results), and anything unresolved. Concise and factual; no greeting, no recap of the brief.
- Report only what you actually did and observed. Never claim a test passed or a file exists unless you ran or checked it; say "not run" / "not verified" otherwise.
- If you cannot continue without a decision only the user can make (scope, budget, a technology choice, conflicting requirements), start your reply with "{marker}" followed by the question, the options and your recommendation.
- If the brief conflicts with good practice, say so in your report instead of silently doing something else.
"""

SUB_LEAD_PROTOCOL = """# You are a sub-lead
Your lead ({lead}) assigns you a task; you run your own team ({team}) to get it done and report back to {lead}.
- Delegate the work to the right people on your team instead of doing it yourself, unless it is truly a one-line answer within your own role.
- If the brief names a specific person (e.g. "QA Tester"), that person must do it: delegate to them. Never do a named person's work yourself.
- Report: who did what, the result, and anything unresolved. Concise and factual; no greeting, no recap of the brief. Report only what was actually done.
- If only the user can decide something, start your reply with "{marker}" followed by the question, the options and your recommendation.
"""

# System prompt section of a team lead that is itself a member (e.g. a PM briefed by the CTO): it runs
# its own team but reports to the lead that assigned the work, never to the user.
SUB_LEAD_SYSTEM = """\
# You lead a sub-team
Another lead assigns you work and you report back to them. You never talk to the user: your reply goes to the lead who assigned the work.

## How you work
1. Decide who on your team does what, in which order, and how many times. Give each piece of work to the member whose role, description and skills match it (for example UI work to the member with frontend skills). Do not call members the task does not need. If the brief names a specific person, that person does the work: delegate to them if they are on your team, otherwise to the member who leads them. Never do a named person's work yourself; do it yourself only when it is a one-line answer within your own role.
2. Delegate with `delegate_task`. Give each member a self-contained brief: goal, relevant context and earlier results, constraints, and what to hand back. Members only see your brief.
{parallel_rule}3. Chain work through yourself (e.g. build → test → review). If a review or test fails, send it back for a fix, at most {max_rounds} rounds.
4. If something only the user can decide comes up (including a member reply that starts with "{marker}"), stop and start your reply with "{marker}" followed by the question, the options and your recommendation; your lead will ask the user.
5. Finish with ONE concise report to the lead who assigned the work: who did what, the result (files, checks), anything unresolved. Report only what members actually produced; no greeting, no recap of the brief.
- You have at most {max_delegations} delegations for this task.

## Your team
{roster}
"""

# Prepended to the system prompt of every agent that answers a person (not members briefed by a lead).
USER_RESPONSE_RULES = """\
# How you answer
- Language: reply in the language of the user's NEWEST message (Vietnamese → Vietnamese, also when typed without diacritics; English → English; 日本語 → 日本語; 中文 → 中文; 한국어 → 한국어), even though these instructions are in English. If that message is too short to tell ("ok"), keep the language of the conversation. Keep code, file names and technical terms as they are.
- Answer first: the first sentence answers the question or states the result; then only the detail that helps. A greeting or simple question gets a few sentences; "N points" gets exactly N points; "short" / "ngắn gọn" means under ~100 words.
- No filler: no preamble, no restating the question, no extra sections nobody asked for, no generic closing offers. Use bullets or short headings only when they help scanning.
- Be accurate: never invent facts, files, numbers or results. If you are unsure, say so briefly and how to check.
- Ask a clarifying question only when you cannot give a useful answer without it: one question, with your recommended default."""


class TeamDelegation:
    """Tools and prompt section for one lead's execution."""

    def __init__(
        self,
        *,
        lead_id: str,
        members: List[TeamMember],
        runner: DelegateRunner,
        prompt_service: Any,
        state: TeamState,
        max_delegations: int,
        max_review_rounds: int,
        plan_approval: bool,
        max_parallel: int = 1,
        delegated: bool = False,
        cancel_event: Any = None,
    ) -> None:
        self.lead_id = lead_id
        # The run's cancel event (e.g. ``context.cancel_event``); also stored on the shared state so
        # sub-leads created without it still see it.
        self.cancel_event = cancel_event
        if cancel_event is not None and state.cancel_event is None:
            state.cancel_event = cancel_event
        # True for a sub-lead: it reports to the lead that briefed it, so no user-facing protocol or ask_user.
        self.delegated = delegated
        self.members = members
        self.runner = runner
        self.prompt_service = prompt_service
        self.state = state
        self.max_delegations = max_delegations
        self.max_review_rounds = max_review_rounds
        self.plan_approval = plan_approval
        self.max_parallel = max(1, int(max_parallel or 1))
        self.delegations = 0
        # The plan submitted with ``submit_plan`` this turn ({"node", "summary", "plan"}); None until then.
        self.plan: Optional[Dict[str, str]] = None
        self._member_ids = {m.node_id for m in members}
        self._lock = threading.Lock()

    @property
    def plan_gate_enabled(self) -> bool:
        """Only the top-level lead (the one talking to the user) submits plans for approval."""
        return bool(self.plan_approval) and not self.delegated

    @property
    def plan_submitted(self) -> bool:
        return self.plan is not None

    @property
    def small_talk(self) -> bool:
        """The top lead got only a greeting / thanks: it answers alone, without team tools."""
        return not self.delegated and is_small_talk(self.state.user_message)

    @property
    def parallel_enabled(self) -> bool:
        return self.max_parallel > 1 and len(self.members) > 1

    # ---- prompt ----
    def system_prompt_section(self) -> str:
        if self.small_talk:
            return LEAD_SMALL_TALK
        roster = "\n".join(
            f"- `{m.node_id}`: {m.summary}"
            + (f" — skills: {', '.join(m.skills)}" if m.skills else "")
            + (f" — leads: {', '.join(m.manages)}" if m.manages else "")
            for m in self.members
        ) or "- (no members configured)"
        parallel_rule = PARALLEL_RULE.format(max_parallel=self.max_parallel) if self.parallel_enabled else ""
        if self.delegated:
            return SUB_LEAD_SYSTEM.format(
                parallel_rule=parallel_rule,
                max_rounds=self.max_review_rounds,
                marker=DECISION_MARKER,
                max_delegations=self.max_delegations,
                roster=roster,
            )
        language = self.state.user_language
        language_rule = (
            f"- The user writes in {language}: reply in {language}, answer directly, no filler.\n" if language else ""
        )
        return LEAD_PROTOCOL.format(
            max_rounds=self.max_review_rounds,
            marker=DECISION_MARKER,
            plan_rule=PLAN_RULE_ON if self.plan_approval else PLAN_RULE_OFF,
            parallel_rule=parallel_rule,
            max_delegations=self.max_delegations,
            max_member_runs=self.state.max_member_runs,
            report_chars=MAX_MEMBER_RESULT_CHARS,
            language_rule=language_rule,
            roster=roster,
        )

    # ---- tools ----
    def _member_property(self) -> Dict[str, Any]:
        return {
            "type": "string",
            "enum": [m.node_id for m in self.members],
            "description": "Node ID of the team member.",
        }

    def tool_specs(self) -> List[ToolSpec]:
        if self.small_talk:
            return []
        # The Scope line lets testers and reviewers size their effort (a static page needs no browser run)
        task_property = {
            "type": "string",
            "description": (
                "Self-contained brief: goal, context, constraints, expected output. First line `Scope: small` "
                "(one file, a static page, a small fix), `Scope: medium` or `Scope: large`."
            ),
        }
        specs = [] if self.delegated else [
            ToolSpec(
                name=ASK_USER_TOOL,
                description=(
                    "Ask the user (your client) a question in the middle of the work and wait for the answer: a "
                    "decision only they can make that you cannot assume. Not for plan approval (use submit_plan or "
                    "end your turn with the plan instead). Write it in the user's language."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "The question, with options and your recommendation when relevant."}
                    },
                    "required": ["question"],
                },
                metadata={"source": TEAM_TOOL_SOURCE},
            )
        ]
        if self.members:
            delegate_specs = [
                ToolSpec(
                    name=DELEGATE_TOOL,
                    description=(
                        "Assign a task to one team member and wait for their report. Members only see the brief you "
                        "write, so include all context they need."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {"member": self._member_property(), "task": task_property},
                        "required": ["member", "task"],
                    },
                    metadata={"source": TEAM_TOOL_SOURCE},
                )
            ]
            if self.parallel_enabled:
                delegate_specs.append(
                    ToolSpec(
                        name=DELEGATE_PARALLEL_TOOL,
                        description=(
                            "Assign INDEPENDENT tasks to several different team members at once and wait for all "
                            f"their reports (up to {self.max_parallel} run at the same time). Use only when no task "
                            "needs another task's result; each member may appear at most once per call. Each task "
                            "counts as one delegation. Members only see their own brief."
                        ),
                        parameters={
                            "type": "object",
                            "properties": {
                                "tasks": {
                                    "type": "array",
                                    "minItems": 2,
                                    "maxItems": len(self.members),
                                    "description": "One entry per member; they run concurrently.",
                                    "items": {
                                        "type": "object",
                                        "properties": {"member": self._member_property(), "task": task_property},
                                        "required": ["member", "task"],
                                    },
                                }
                            },
                            "required": ["tasks"],
                        },
                        metadata={"source": TEAM_TOOL_SOURCE},
                    )
                )
            specs = delegate_specs + specs
        if self.plan_gate_enabled:
            specs.append(
                ToolSpec(
                    name=SUBMIT_PLAN_TOOL,
                    description=(
                        "Present your plan for a NEW project or significant new feature to the user and wait for "
                        "their approval. Ends your turn right away: the plan becomes your answer and no team work "
                        "runs until the user approves. Not for bug fixes, small changes or questions, and not when "
                        "the user already approved or said to go ahead. Write it in the user's language."
                    ),
                    parameters={
                        "type": "object",
                        "properties": {
                            "plan": {
                                "type": "string",
                                "description": "The plan in markdown: goal, scope, stack, steps with which member does "
                                "what, risks and open questions with your recommended defaults.",
                            },
                            "summary": {"type": "string", "description": "One-line summary of the plan."},
                        },
                        "required": ["plan", "summary"],
                    },
                    metadata={"source": TEAM_TOOL_SOURCE},
                )
            )
        return specs

    def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        if tool_name == SUBMIT_PLAN_TOOL:
            return self._submit_plan(str(arguments.get("plan", "")).strip(), str(arguments.get("summary", "")).strip())
        if tool_name in (DELEGATE_TOOL, DELEGATE_PARALLEL_TOOL) and self.plan_submitted:
            raise ValueError(PLAN_GATE_REFUSAL)
        if tool_name == DELEGATE_TOOL:
            return self._delegate(str(arguments.get("member", "")).strip(), str(arguments.get("task", "")).strip())
        if tool_name == DELEGATE_PARALLEL_TOOL:
            return self._delegate_parallel(arguments.get("tasks"))
        if tool_name == ASK_USER_TOOL:
            return self._ask_user(str(arguments.get("question", "")).strip())
        raise ValueError(f"Unsupported team tool '{tool_name}'")

    # ---- delegation ----
    def _check_member(self, member: str, task: str) -> None:
        if member not in self._member_ids:
            raise ValueError(f"'{member}' is not on your team. Members: {sorted(self._member_ids)}")
        if not task:
            raise ValueError(f"task is required (member '{member}')")

    def _check_depth(self) -> None:
        if self.state.depth >= MAX_DELEGATION_DEPTH:
            raise ValueError("Delegation is nested too deeply; do this task yourself or report back.")

    def _cancelled(self) -> bool:
        event = self.cancel_event
        return bool(event is not None and event.is_set()) or self.state.is_cancelled()

    def _reserve(self, count: int) -> None:
        """Count ``count`` delegations against this lead's limit and the run-wide budget, all or nothing."""
        self._check_depth()
        with self._lock:
            left = self.max_delegations - self.delegations
            if left <= 0:
                raise ValueError(
                    f"Delegation limit ({self.max_delegations}) reached for this request. Report the current status to the user."
                )
            if count > left:
                raise ValueError(
                    f"Delegation limit: only {left} of {self.max_delegations} delegations left, but {count} tasks were "
                    "given. Send fewer tasks or report the current status to the user."
                )
            self.state.reserve_member_runs(count)  # raises when the run-wide budget is exhausted
            self.delegations += count

    def _refund(self, count: int) -> None:
        """Give back delegations whose member run crashed or was cancelled."""
        with self._lock:
            self.delegations = max(0, self.delegations - count)
        self.state.refund_member_runs(count)

    def _delegations_left(self) -> int:
        with self._lock:
            return self.max_delegations - self.delegations

    def _delegate(self, member: str, task: str) -> Dict[str, Any]:
        self._check_member(member, task)
        result = self._run_member(member, task)
        result["delegations_left"] = self._delegations_left()
        result["team_runs_left"] = self.state.member_runs_left()
        return result

    def _run_member(self, member: str, task: str) -> Dict[str, Any]:
        """Claim, reserve and run one member. Safe to call concurrently for different members."""
        self._check_depth()
        if not self.state.claim(member):
            raise ValueError(f"'{member}' is already working on another task right now; wait for its report first.")
        try:
            self._reserve(1)  # after the claim: a busy member never uses up a delegation
        except BaseException:
            self.state.release(member)
            raise
        return self._execute_member(member, task)

    def _execute_member(self, member: str, task: str) -> Dict[str, Any]:
        """Run a member already claimed and reserved; release it, and refund + log when it fails."""
        try:
            if self._cancelled():
                raise WorkflowCancelledError("Workflow execution cancelled")
            brief = self._compose_brief(member, task)
            switches_before = self._account_switches()
            with _nested_delegation():
                outputs = self.runner(
                    member, [Message(role=MessageRole.USER, content=brief, metadata={"source": self.lead_id})], self.lead_id
                )
        except WorkflowCancelledError:
            self._refund(1)
            self.state.log_failure(member, task, "cancelled")
            raise
        except Exception as exc:
            self._refund(1)
            self.state.log_failure(member, task, f"{exc.__class__.__name__}: {exc}")
            raise
        finally:
            self.state.release(member)

        outputs = [m for m in outputs or [] if m is not None]
        report = "\n\n".join(msg.text_content() for msg in outputs).strip() or "(no output)"
        account_note = self._account_note(switches_before)
        failed = next((m for m in outputs if (m.metadata or {}).get("model_error")), None)
        if failed is not None:
            reason = str((failed.metadata or {}).get("error") or report)
            self.state.add_report(member, task, f"[failed: model error] {reason}")
            failure = {
                "member": member,
                "error": f"model call failed ({reason}). The task was not done. Retry once, give it to another "
                "member, or tell the user it is blocked.",
                "needs_user_decision": False,
            }
            if account_note:
                failure["account_note"] = account_note
            return failure
        self.state.add_report(member, task, report)  # the full report stays in the team state
        result: Dict[str, Any] = {
            "member": member,
            "report": _truncate(report, MAX_MEMBER_RESULT_CHARS),
            "needs_user_decision": report.lstrip().upper().startswith(DECISION_MARKER),
        }
        if account_note:
            result["account_note"] = account_note
        if len(report) > MAX_MEMBER_RESULT_CHARS:
            result["note"] = (
                f"Report clipped to {MAX_MEMBER_RESULT_CHARS} of {len(report)} characters; the full text is kept. "
                f"If you need a detail that was cut, ask {member} for exactly that detail."
            )
        return result

    def _account_switches(self) -> Dict[str, str]:
        source = self.state.account_switches
        if source is None:
            return {}
        try:
            return dict(source() or {})
        except Exception:  # noqa: BLE001 - bookkeeping must never fail a delegation
            return {}

    def _account_note(self, before: Dict[str, str]) -> str:
        """A one-line note for the lead when an account hit its usage limit while the member worked."""
        new = [conn for key, conn in self._account_switches().items() if before.get(key) != conn]
        if not new:
            return ""
        try:
            from agentdev.runtime.node.agent.account_fallback import account_label

            names = sorted({account_label(conn) for conn in new})
        except Exception:  # noqa: BLE001 - labels are cosmetic
            names = sorted(set(new))
        return (
            f"An account reached its usage limit during this task; work continued on another account "
            f"({', '.join(names)}). Mention it to the user in one line."
        )

    def _parse_parallel_tasks(self, raw_tasks: Any) -> List[Tuple[str, str]]:
        if not isinstance(raw_tasks, list) or len(raw_tasks) < 2:
            raise ValueError("tasks must be a list of at least 2 {member, task} items; use delegate_task for a single task.")
        tasks: List[Tuple[str, str]] = []
        seen: Set[str] = set()
        for idx, item in enumerate(raw_tasks):
            if not isinstance(item, Mapping):
                raise ValueError(f"tasks[{idx}] must be an object with 'member' and 'task'")
            member = str(item.get("member", "")).strip()
            task = str(item.get("task", "")).strip()
            self._check_member(member, task)
            if member in seen:
                raise ValueError(
                    f"'{member}' appears more than once. A member can work on only one task at a time: merge its "
                    "tasks into one brief, or give it the next task after this call returns."
                )
            seen.add(member)
            tasks.append((member, task))
        return tasks

    def _delegate_parallel(self, raw_tasks: Any) -> Dict[str, Any]:
        if not self.parallel_enabled:
            raise ValueError("Parallel delegation is disabled for this team; use delegate_task.")
        tasks = self._parse_parallel_tasks(raw_tasks)
        self._check_depth()
        results: List[Optional[Dict[str, Any]]] = [None] * len(tasks)
        claimed: List[int] = []
        for idx, (member, _task) in enumerate(tasks):
            if self.state.claim(member):
                claimed.append(idx)
            else:
                results[idx] = {
                    "member": member,
                    "error": f"'{member}' is already working on another task right now; wait for its report first.",
                    "needs_user_decision": False,
                }
        if claimed:
            try:
                self._reserve(len(claimed))  # after the claims; all or nothing
            except BaseException:
                for idx in claimed:
                    self.state.release(tasks[idx][0])
                raise

        def run_one(member: str, task: str) -> Dict[str, Any]:
            try:
                return self._execute_member(member, task)
            except WorkflowCancelledError:
                raise
            except Exception as exc:  # one failure must not lose the other members' reports
                return {"member": member, "error": str(exc) or exc.__class__.__name__, "needs_user_decision": False}

        cancelled: Optional[WorkflowCancelledError] = None
        if claimed:
            pool = ThreadPoolExecutor(
                max_workers=min(self.max_parallel, len(claimed)), thread_name_prefix=f"team-{self.lead_id}"
            )
            try:
                # Each worker runs in a copy of this context: it inherits the current delegation depth and
                # only bumps its own copy, so sibling members do not count against each other's depth.
                index_of = {pool.submit(contextvars.copy_context().run, run_one, *tasks[idx]): idx for idx in claimed}
                pending = set(index_of)
                while pending:
                    done, pending = wait(pending, timeout=CANCEL_POLL_SECONDS, return_when=FIRST_COMPLETED)
                    for future in done:
                        idx = index_of[future]
                        try:
                            results[idx] = future.result()
                        except WorkflowCancelledError as exc:
                            cancelled = cancelled or exc
                        except CancelledError:
                            results[idx] = {"member": tasks[idx][0], "error": "cancelled", "needs_user_decision": False}
                    if cancelled is None and self._cancelled():
                        cancelled = WorkflowCancelledError("Workflow execution cancelled")
                    if cancelled is not None:
                        for future in pending:
                            if future.cancel():  # never started: free the member and its delegation
                                member, task = tasks[index_of[future]]
                                self.state.release(member)
                                self._refund(1)
                                self.state.log_failure(member, task, "cancelled")
                        break
            finally:
                # On cancel do not wait: running members stop on the cancel event themselves.
                pool.shutdown(wait=cancelled is None, cancel_futures=True)
        if cancelled is not None:
            raise cancelled

        final = [r for r in results if r is not None]
        return {
            "results": final,
            "failed": [r["member"] for r in final if "error" in r],
            "needs_user_decision": any(r.get("needs_user_decision") for r in final),
            "delegations_left": self._delegations_left(),
            "team_runs_left": self.state.member_runs_left(),
        }

    def _compose_brief(self, member: str, task: str) -> str:
        info = next((m for m in self.members if m.node_id == member), None)
        if info is not None and info.manages:
            # A sub-lead's system prompt already holds its protocol (SUB_LEAD_SYSTEM); do not repeat it.
            parts = [f"# Assigned by {self.lead_id}\nRun this with your team and report back to {self.lead_id}."]
        else:
            parts = [MEMBER_PROTOCOL.format(lead=self.lead_id, marker=DECISION_MARKER)]
        current = self.state.recent(member, MAX_DIGEST_ENTRIES)
        earlier = self.state.earlier_reports(member, MAX_DIGEST_ENTRIES)
        # One relevant earlier report (the latest of this request, else of an earlier message), clipped;
        # the member's other earlier tasks only as a one-line digest.
        relevant: Optional[Dict[str, str]] = None
        heading = ""
        others: List[Dict[str, str]] = []
        if current:
            relevant, others = current[-1], earlier + current[:-1]
            heading = "# Your last task and report for the current request"
        elif earlier:
            relevant, others = earlier[-1], earlier[:-1]
            heading = (
                "# Your last task and report from earlier messages of this conversation "
                "(context; files may have changed since)"
            )
        if relevant is not None:
            parts.append(
                f"{heading}\n## Task\n{clip_middle(relevant.get('task'), 400, head_ratio=1.0)}\n"
                f"## Your report\n{clip_middle(relevant.get('report'), MAX_HISTORY_CHARS)}"
            )
        if others:
            titles = "; ".join(_first_line(item.get("task"), 80) for item in others[-5:])
            parts.append(f"# Your other earlier tasks (titles only): {titles}")
        if self.state.user_language:
            parts.append(
                f"# Language\nWrite user-facing text and documents (UI text, docs, messages) in {self.state.user_language}. "
                "Keep code, identifiers and technical terms as they are."
            )
        parts.append(f"# Task from {self.lead_id}\n{task}")
        return "\n\n".join(parts)

    def _submit_plan(self, plan: str, summary: str) -> Dict[str, Any]:
        if not self.plan_gate_enabled:
            raise ValueError("submit_plan is not available here; continue the work or report back.")
        if not plan:
            raise ValueError("plan is required")
        with self._lock:
            self.plan = {"node": self.lead_id, "summary": summary or _first_line(plan, 160), "plan": plan}
        return {"status": "submitted", "note": "Your turn ends now; the user will approve or change the plan."}

    def _ask_user(self, question: str) -> Dict[str, Any]:
        if not question:
            raise ValueError("question is required")
        if self.delegated:
            raise ValueError(
                f"You do not talk to the user. Start your reply to your lead with \"{DECISION_MARKER}\" followed by "
                "the question, the options and your recommendation."
            )
        if self.prompt_service is None:
            raise RuntimeError("No user is attached to this run; continue with your best judgement and state the assumption.")
        result = self.prompt_service.request(
            self.lead_id,
            question,
            inputs=None,
            metadata={"node_type": "agent", "kind": "lead_question"},
        )
        answer = getattr(result, "text", None)
        if answer is None:
            answer = str(result.as_message_content()) if hasattr(result, "as_message_content") else str(result)
        self.state.add_exchange(question, str(answer))
        return {"answer": answer}


def _max_member_runs(global_state: Mapping[str, Any]) -> int:
    for value in (global_state.get(MAX_MEMBER_RUNS_KEY), os.environ.get(MAX_MEMBER_RUNS_ENV)):
        try:
            number = int(value) if value is not None and not isinstance(value, bool) else 0
        except (TypeError, ValueError):
            number = 0
        if number > 0:
            return number
    return DEFAULT_MAX_MEMBER_RUNS


def get_team_state(global_state: Dict[str, Any], cancel_event: Any = None) -> TeamState:
    state = global_state.get("_team_state")
    if not isinstance(state, TeamState):
        state = TeamState(max_member_runs=_max_member_runs(global_state))
        # Earlier turns of the conversation, when the run's caller provides them (see WebSocketGraphExecutor).
        state.seed_earlier_turns(global_state.get(CONVERSATION_TURNS_KEY))
        # account_fallback.FallbackState lives in the same global_state ("_account_fallback").
        state.account_switches = lambda: dict(getattr(global_state.get("_account_fallback"), "replacement", None) or {})
        global_state["_team_state"] = state
    if cancel_event is not None and state.cancel_event is None:
        state.cancel_event = cancel_event
    return state


def is_delegated_call() -> bool:
    """True while an agent runs as a member briefed by a lead (it reports to the lead, not a person)."""
    return _DELEGATION_DEPTH.get() > 0


def user_exchanges(global_state: Optional[Mapping[str, Any]]) -> List[Dict[str, str]]:
    """Questions leads asked the user during a run, with the answers (empty when none).

    Followed by the run's delegation digest as ``{"kind": "delegation", "member", "task", "report"}``
    entries: ``conversation_turns.make_turn`` files them under the turn's ``team`` key. This is how
    the digest reaches the stored turn through the existing ``make_turn(..., exchanges)`` call.
    """
    state = (global_state or {}).get("_team_state")
    if not isinstance(state, TeamState):
        return []
    with state.lock:
        exchanges = [dict(item) for item in state.exchanges]
    return exchanges + [{"kind": DELEGATION_KIND, **entry} for entry in team_digest(state)]


def team_digest_from_state(global_state: Optional[Mapping[str, Any]]) -> List[Dict[str, str]]:
    """The delegation digest of a run (``team_digest``) from its ``global_state``."""
    return team_digest((global_state or {}).get("_team_state"))
