"""Carry the earlier turns of a session into a follow-up run.

Every message the user sends after a run finished starts a brand-new graph run, so
agents begin with empty conversations. To keep a chat coherent, the start node of a
follow-up run receives a compact transcript of the previous turns of the same
session (what the user asked, the questions the lead asked during the turn with the
user's replies, what the team did, and the final answer they got), followed by the new
message. Members briefed by a team lead are not affected: the lead decides what to tell
them (their own earlier reports reach their brief through the team state).
"""

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from agentdev.runtime.node.agent.team import (
    DELEGATION_KIND,
    MAX_DIGEST_ENTRIES,
    clip_middle,
    has_go_ahead,
    is_plan_approval,
    is_small_talk,
)

MAX_TURNS = 4
MAX_TRANSCRIPT_CHARS = 9_000
MAX_USER_CHARS = 2_000
MAX_LATEST_USER_CHARS = 4_000
MAX_ANSWER_CHARS = 4_000
MAX_LATEST_ANSWER_CHARS = 8_000  # the answer the new message most likely refers to
MAX_EXCHANGES = 4
MAX_QUESTION_CHARS = 2_500  # questions the lead asked (often a whole plan)
MAX_REPLY_CHARS = 1_000
# "What the team did" is shown for the last TEAM_DIGEST_TURNS turns only.
TEAM_DIGEST_TURNS = 2
MAX_TEAM_CHARS_LATEST = 5_000
MAX_TEAM_CHARS_OLDER = 2_000
# Turns older than the last TEAM_DIGEST_TURNS are background only: their text is clipped harder so a
# long chat does not re-send most of its history (in tokens) with every new message.
MAX_OLD_USER_CHARS = 800
MAX_OLD_ANSWER_CHARS = 1_200
MAX_OLD_QUESTION_CHARS = 600
MAX_OLD_REPLY_CHARS = 300

# Pinned project brief: kept ahead of the transcript so the agreed scope survives long chats.
MAX_BRIEF_FIRST_CHARS = 1_500
MAX_BRIEF_PLAN_CHARS = 2_500
MAX_BRIEF_DECISIONS = 8
MAX_BRIEF_QUESTION_CHARS = 200
MAX_BRIEF_REPLY_CHARS = 350
MAX_BRIEF_CHARS = 6_000
# A short reply ("duyệt", "ok") approves the latest plan: it is sent whole up to this cap, outside the budget.
MAX_SHORT_PLAN_CHARS = 6_000
PLAN_PINNED_NOTE = "(the full plan is shown above under 'Plan the user is replying to')"
MAX_FILES_LISTED = 40

# History budget (brief + files + transcript) sent with a follow-up message, by kind of message.
# A short approval / "continue" / thanks refers to the latest turn: a long transcript is mostly
# re-sent tokens. A normal request gets the wider budget.
SHORT_TURN_HISTORY_CHARS = 3_000
NORMAL_TURN_HISTORY_CHARS = 9_000
# Shares of the budget the brief and the files list may take at most (the transcript gets the rest).
BRIEF_SHARE = 0.3
FILES_SHARE = 0.15
# A short turn shows the latest turn (and a clipped one before it); the brief covers the rest.
SHORT_TURN_MAX_TURNS = 2
MAX_CHAT_QUESTION_CHARS = 300
MAX_SHORT_RESUME_WORDS = 3
BRIEF_HEADER = (
    "[PROJECT BRIEF (pinned, always applies even if the turns below are omitted): the original request, the "
    "latest plan and the user's answers. Keep to this scope; do not redo what is done.]"
)
FILES_HEADER = (
    "[Files changed so far in this conversation. Read these files when you need them instead of "
    "regenerating or rewriting them from scratch.]"
)

HEADER = (
    "[Earlier in this conversation, oldest first. Context only: decisions, approvals and facts in it still "
    "apply; do not redo finished work unless asked.]"
)
NEW_MESSAGE_HEADER = (
    "[The user's NEW message: answer this one, in its language. If it approves or answers what you proposed "
    "or asked above, act on it without asking again.]"
)
# ``kind`` of a turn whose answer is a plan the lead submitted for approval (``submit_plan``).
PLAN_KIND = "plan"
# Put before the new message when the previous turn ended with a plan (``{reply}``: the user's message).
PLAN_REPLY_NOTE = (
    "[Reply to your plan] The user replied to your plan: {reply}. If this approves it (e.g. ok, đồng ý, duyệt, "
    "làm đi, go ahead), execute the plan now without re-asking; if it requests changes, revise and call "
    "submit_plan again. Delegating to your team is allowed in this turn."
)
STATUS_NOTES = {
    "cancelled": "(This turn was cancelled before it finished: the work may be incomplete.)",
    "error": "(This turn ended with an error before it finished: the work may be incomplete.)",
}


def _attachment_entry(item: Any) -> Any:
    """A stored attachment reference: a plain name, or ``{"name", "path"}`` when its path is known.

    Only references are kept, never file contents: a follow-up lead re-reads the file when it needs it.
    """
    if isinstance(item, dict):
        name = str(item.get("name") or "").strip()
        path = str(item.get("path") or "").strip()
        if not path:
            return name or None
        return {"name": name or path.replace("\\", "/").rsplit("/", 1)[-1], "path": path}
    return str(item).strip() if item else None


def attachment_refs(attachment_ids: Iterable[str], manifest: Optional[Dict[str, Any]]) -> List[Any]:
    """Attachment references for ``make_turn`` from an attachment manifest (id -> {"ref": {...}}).

    Keeps the stored file's path (``ref.local_path``) so a later turn can point the lead at the file.
    """
    refs: List[Any] = []
    for attachment_id in attachment_ids or []:
        ref = ((manifest or {}).get(attachment_id) or {}).get("ref") or {}
        name = str(ref.get("name") or attachment_id)
        path = str(ref.get("local_path") or "")
        refs.append({"name": name, "path": path} if path else name)
    return refs


def _render_attachments(attachments: List[Any]) -> str:
    rendered = []
    for item in attachments:
        entry = _attachment_entry(item)
        if isinstance(entry, dict):
            rendered.append(f"{entry['name']} (path: {entry['path']})")
        elif entry:
            rendered.append(entry)
    if not rendered:
        return ""
    return (
        f"(attached: {', '.join(rendered)}. Contents are not repeated here; re-read a file with your file "
        "tools if you need it.)"
    )


def _clip(text: str, limit: int) -> str:
    """Keep the start and the end of long text (60% / 40%) with an omission marker in between."""
    return clip_middle(text, limit)


def make_turn(
    user_text: Optional[str],
    answer: Optional[str],
    attachments: Iterable[str] = (),
    exchanges: Iterable[Dict[str, str]] = (),
    team: Optional[Iterable[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """One finished turn.

    ``exchanges``: questions asked to the user during the turn and the replies. Entries with
    ``kind == "delegation"`` (appended by ``team.user_exchanges``) are the run's delegation digest
    and go under ``team`` instead, unless ``team`` is given explicitly.
    """
    turn: Dict[str, Any] = {
        "user": (user_text or "").strip(),
        "answer": (answer or "").strip(),
        "attachments": [e for e in (_attachment_entry(a) for a in attachments or []) if e],
    }
    items = [e for e in exchanges or [] if isinstance(e, dict)]
    delegations = [e for e in items if e.get("kind") == DELEGATION_KIND]
    kept = [
        {"question": str(e.get("question") or "").strip(), "answer": str(e.get("answer") or "").strip()}
        for e in items
        if e.get("kind") != DELEGATION_KIND and (e.get("question") or e.get("answer"))
    ]
    if kept:
        turn["exchanges"] = kept[-MAX_EXCHANGES:]
    digest = [
        {
            "member": str(e.get("member") or "").strip(),
            "task": str(e.get("task") or "").strip(),
            "report": str(e.get("report") or "").strip(),
        }
        for e in (delegations if team is None else team) or []
        if isinstance(e, dict) and e.get("member")
    ]
    if digest:
        turn["team"] = digest[-MAX_DIGEST_ENTRIES:]
    return turn


def _render_team(entries: List[Any], budget: int) -> List[str]:
    entries = [e for e in entries if isinstance(e, dict) and e.get("member")][-MAX_DIGEST_ENTRIES:]
    if not entries:
        return []
    task_limit = 300 if budget >= MAX_TEAM_CHARS_LATEST else 150
    report_limit = max(200, min(1_200, budget // len(entries) - task_limit - 40))
    lines = ["What the team did:"]
    for entry in entries:
        lines.append(f"- {entry['member']}: {_clip(str(entry.get('task') or ''), task_limit)}")
        lines.append(f"  Report: {_clip(str(entry.get('report') or ''), report_limit) or '(none)'}")
    return [_clip("\n".join(lines), budget)]


def _render_turn(
    index: int,
    turn: Dict[str, Any],
    *,
    latest: bool = False,
    team_budget: int = 0,
    old: bool = False,
    answer_limit: Optional[int] = None,
) -> str:
    """One turn; ``old`` (before the last TEAM_DIGEST_TURNS turns) clips its texts harder."""
    user_limit = MAX_OLD_USER_CHARS if old else MAX_LATEST_USER_CHARS if latest else MAX_USER_CHARS
    question_limit = MAX_OLD_QUESTION_CHARS if old else MAX_QUESTION_CHARS
    reply_limit = MAX_OLD_REPLY_CHARS if old else MAX_REPLY_CHARS
    if answer_limit is None:
        answer_limit = MAX_OLD_ANSWER_CHARS if old else MAX_LATEST_ANSWER_CHARS if latest else MAX_ANSWER_CHARS
    user = _clip(str(turn.get("user") or ""), user_limit) or "(no text)"
    attached = _render_attachments(list(turn.get("attachments") or []))
    if attached:
        user += f"\n{attached}"
    lines = [f"--- Turn {index} ---", f"User: {user}"]
    for exchange in (turn.get("exchanges") or [])[-MAX_EXCHANGES:]:
        if not isinstance(exchange, dict):
            continue
        lines.append(f"You asked: {_clip(str(exchange.get('question') or ''), question_limit)}")
        lines.append(f"User replied: {_clip(str(exchange.get('answer') or ''), reply_limit)}")
    if team_budget > 0 and isinstance(turn.get("team"), list):
        lines.extend(_render_team(turn["team"], team_budget))
    note = STATUS_NOTES.get(str(turn.get("status") or "").strip().lower())
    if note:
        lines.append(note)
    answer = _clip(str(turn.get("answer") or ""), answer_limit)
    label = "You proposed this plan for approval" if is_plan_turn(turn) else "You answered"
    lines.append(f"{label}: {answer or '(no answer was produced)'}")
    return "\n".join(lines)


def build_transcript(
    turns: List[Dict[str, Any]],
    *,
    max_turns: int = MAX_TURNS,
    max_chars: int = MAX_TRANSCRIPT_CHARS,
) -> str:
    """Render the latest turns, dropping the oldest ones until the text fits ``max_chars``."""
    return _render_transcript(turns, max_turns=max_turns, max_chars=max_chars)[0]


def _render_transcript(
    turns: List[Dict[str, Any]],
    *,
    max_turns: int = MAX_TURNS,
    max_chars: int = MAX_TRANSCRIPT_CHARS,
    short: bool = False,
    pinned_plan: Optional[int] = None,
) -> Tuple[str, int]:
    """(transcript, index in ``turns`` of the oldest turn it shows; ``len(turns)`` when empty).

    ``short``: compact rendering for a short reply (approval, "continue"): the latest turn's answer
    and team digest get fixed shares of ``max_chars`` so the answer survives, older turns are clipped.
    """
    usable = [(i, t) for i, t in enumerate(turns or []) if isinstance(t, dict) and (t.get("user") or t.get("answer"))]
    if not usable:
        return "", len(turns or [])
    if pinned_plan is not None:  # ``pinned_plan``: index in ``turns`` of a plan rendered whole elsewhere
        usable = [(i, {**t, "answer": PLAN_PINNED_NOTE} if i == pinned_plan else t) for i, t in usable]
    last = len(usable) - 1
    first_index = max(len(usable) - max_turns, 0)

    def team_budget(n: int) -> int:
        if short:
            return int(max_chars * 0.15) if n == last else 0
        if n == last:
            return MAX_TEAM_CHARS_LATEST
        return MAX_TEAM_CHARS_OLDER if n > last - TEAM_DIGEST_TURNS else 0

    def answer_limit(n: int, turn: Dict[str, Any]) -> Optional[int]:
        if not short or n != last:
            return None
        # What a short reply answers: a plan gets most of the room
        return int(max_chars * (0.7 if is_plan_turn(turn) else 0.55))

    rendered = [
        _render_turn(
            n + 1,
            t,
            latest=n == last,
            team_budget=team_budget(n),
            old=n <= last - TEAM_DIGEST_TURNS or (short and n != last),
            answer_limit=answer_limit(n, t),
        )
        for n, (_, t) in enumerate(usable)
    ][first_index:]
    omitted = first_index
    while len(rendered) > 1 and sum(len(r) + 2 for r in rendered) > max_chars:
        rendered.pop(0)
        omitted += 1
    if len(rendered) == 1 and len(rendered[0]) > max_chars:
        # Only the latest turn is left and it is too long: render it compactly (questions clipped
        # hard, the answer and the team digest by share) so its answer is not cut out of the middle
        index, turn = usable[omitted]
        rendered[0] = _render_turn(
            omitted + 1,
            turn,
            latest=True,
            team_budget=int(max_chars * 0.15),
            old=True,
            answer_limit=int(max_chars * (0.7 if is_plan_turn(turn) else 0.55)),
        )
    body = "\n\n".join(rendered)
    if len(body) > max_chars:  # a single oversized turn: keep its start (the request) and end (the answer)
        body = clip_middle(body, max_chars, head_ratio=0.4)
    lines = [HEADER]
    if omitted:
        lines.append(f"({omitted} older turn(s) omitted)")
    lines.append(body)
    return "\n".join(lines), usable[omitted][0]


def build_project_brief(
    turns: List[Dict[str, Any]], *, visible_from: Optional[int] = None, max_chars: int = MAX_BRIEF_CHARS,
    include_plan: bool = True,
) -> str:
    """Deterministic brief of the whole session (no model call): first request, latest plan, user answers.

    It is the rolling summary of the turns the transcript no longer shows: with ``visible_from``
    (index in ``turns`` of the oldest turn the transcript shows), what those visible turns already
    say is left out, so nothing is sent twice.
    """
    cut = len(turns or []) if visible_from is None else visible_from
    usable = [(i, t) for i, t in enumerate(turns or []) if isinstance(t, dict)]
    parts: List[str] = []
    first = next(((i, str(t.get("user") or "").strip()) for i, t in usable if str(t.get("user") or "").strip()), None)
    if first and first[0] < cut:
        parts.append(f"Original request: {_clip(first[1], MAX_BRIEF_FIRST_CHARS)}")
    plan = _latest_plan(turns)
    if plan and plan[0] < cut and include_plan:
        parts.append(f"Latest plan submitted: {_clip(str(plan[1]['answer']).strip(), MAX_BRIEF_PLAN_CHARS)}")
    decisions: List[str] = []
    for index, t in usable:
        if index >= cut:
            continue
        for ex in t.get("exchanges") or []:
            if isinstance(ex, dict) and str(ex.get("answer") or "").strip():
                decisions.append(
                    f"- Q: {_clip(str(ex.get('question') or ''), MAX_BRIEF_QUESTION_CHARS)} "
                    f"A: {_clip(str(ex['answer']).strip(), MAX_BRIEF_REPLY_CHARS)}"
                )
    if decisions:
        parts.append("User's answers to your questions (confirmed decisions):")
        parts.extend(decisions[-MAX_BRIEF_DECISIONS:])
    if not parts:
        return ""
    return clip_middle("\n".join([BRIEF_HEADER] + parts), min(max_chars, MAX_BRIEF_CHARS), head_ratio=0.5)


def _latest_plan(turns: List[Dict[str, Any]]) -> Optional[Tuple[int, Dict[str, Any]]]:
    """(index in ``turns``, turn) of the latest plan with an answer, or None."""
    return next(((i, t) for i, t in reversed(list(enumerate(turns or [])))
                 if is_plan_turn(t) and str(t.get("answer") or "").strip()), None)


def render_files_digest(changed_files: Any, max_chars: Optional[int] = None) -> str:
    """"Files changed so far" block from ``{path: size_bytes}`` (or a list of paths); "" when empty."""
    if isinstance(changed_files, dict):
        items = [(str(k), v) for k, v in changed_files.items()]
    else:
        items = [(str(k), None) for k in changed_files or []]
    items = [(k, v) for k, v in items if k]
    if not items:
        return ""
    shown = items[-MAX_FILES_LISTED:]

    def render(listed: List[Tuple[str, Any]]) -> str:
        lines = [FILES_HEADER]
        for path, size in listed:
            lines.append(f"- {path}" + (f" ({size} bytes)" if isinstance(size, int) and size >= 0 else ""))
        if len(items) > len(listed):
            lines.append(f"(+{len(items) - len(listed)} earlier file(s) not listed)")
        return "\n".join(lines)

    text = render(shown)
    # Over the budget: the most recently changed files are the ones listed
    while max_chars is not None and len(text) > max_chars and shown:
        shown = shown[1:]
        text = render(shown)
    return text if shown else ""


def is_short_turn(prompt: Optional[str]) -> bool:
    """A reply that refers to the latest turn: an approval, "continue", thanks ("ok", "duyệt", "tiếp tục")."""
    from agentdev.api.services.run_checkpoint import is_resume_intent  # local: keeps this module's imports light

    text = (prompt or "").strip()
    if not text:
        return False
    # "tiếp tục" / "làm tiếp đi" only: "làm tiếp phần xuất PDF" carries a request of its own
    bare_resume = is_resume_intent(text) and len(text.split()) <= MAX_SHORT_RESUME_WORDS
    return is_plan_approval(text) or bare_resume or is_small_talk(text)


def is_chat_only_turn(prompt: Optional[str]) -> bool:
    """Thanks / greetings and short questions: no file work, so the changed-files list is not sent."""
    text = (prompt or "").strip()
    if is_small_talk(text):
        return True
    return (0 < len(text) <= MAX_CHAT_QUESTION_CHARS and text.endswith(("?", "？")) and not has_go_ahead(text)
            and not _ACTION_WORDS.search(text) and not _FILE_TOKEN.search(text))


# A question that asks for work ("Can you fix the crash in login.py?") still needs the changed-files list.
_ACTION_WORDS = re.compile(
    r"\b(sửa|thêm|đổi|tạo|xóa|xoá|viết|chạy|cập nhật|triển khai|kiểm tra|cài|dựng|làm lại|"
    r"fix|add|change|create|delete|remove|write|run|update|deploy|test|install|build|implement|refactor|rename)\b",
    re.IGNORECASE,
)
# A file name (login.py, main.ts) or a path (src/app, src\app).
_FILE_TOKEN = re.compile(r"\b\w+\.[A-Za-z]\w{0,4}\b|[\w.-]+[/\\][\w./\\-]+")


def compose_follow_up_prompt(
    turns: List[Dict[str, Any]], prompt: str, resume_note: str = "", changed_files: Any = None
) -> str:
    """Prefix ``prompt`` with the session history; unchanged when there is no history.

    The history (brief, changed files, transcript) fits SHORT_TURN_HISTORY_CHARS for a short reply
    and NORMAL_TURN_HISTORY_CHARS otherwise. The parts that change least come first (brief, files,
    then the transcript), so consecutive turns share a longer prompt prefix (provider prompt cache).

    ``resume_note``: what an interrupted run had done (see run_checkpoint.build_resume_note); it
    goes between the history and the new message, and is used even when there is no transcript.
    """
    short = is_short_turn(prompt)
    budget = SHORT_TURN_HISTORY_CHARS if short else NORMAL_TURN_HISTORY_CHARS
    max_turns = SHORT_TURN_MAX_TURNS if short else MAX_TURNS
    files = "" if is_chat_only_turn(prompt) else render_files_digest(changed_files, int(budget * FILES_SHARE))
    brief_cap = int(budget * BRIEF_SHARE)
    # A short reply approves the latest plan: send that plan whole (the brief and the transcript would clip it)
    plan = _latest_plan(turns) if short else None
    plan_block = (f"Plan the user is replying to (full text):\n{_clip(str(plan[1]['answer']).strip(), MAX_SHORT_PLAN_CHARS)}"
                  if plan else "")
    pinned = plan[0] if plan else None
    brief = build_project_brief(turns, max_chars=brief_cap, include_plan=not plan)  # upper bound: no turn shown yet
    transcript = ""
    for _ in range(2):  # the brief shrinks once the transcript shows turns: give that room back
        room = budget - len(brief) - len(files) - 4 - len(HEADER) - 40
        transcript, visible_from = _render_transcript(
            turns, max_turns=max_turns, max_chars=max(room, 600), short=short, pinned_plan=pinned
        )
        new_brief = build_project_brief(turns, visible_from=visible_from, max_chars=brief_cap, include_plan=not plan)
        if new_brief == brief:
            break
        brief = new_brief
    if not transcript:
        if resume_note:
            return f"{resume_note}\n\n{NEW_MESSAGE_HEADER}\n{prompt or ''}".rstrip()
        return prompt
    history = "\n\n".join(x for x in (brief, plan_block, files, transcript) if x)
    note = f"{resume_note}\n\n" if resume_note else ""
    if turns and is_plan_turn(turns[-1]):
        # Before the new-message header: the header still marks where the user's own text starts.
        reply = _clip((prompt or "").strip(), MAX_LATEST_USER_CHARS) or "(no text)"
        note += PLAN_REPLY_NOTE.format(reply=reply) + "\n\n"
    return f"{history}\n\n{note}{NEW_MESSAGE_HEADER}\n{prompt or ''}".rstrip()


def is_plan_turn(turn: Any) -> bool:
    """True for a turn whose answer is a plan waiting for the user's approval."""
    return isinstance(turn, dict) and turn.get("kind") == PLAN_KIND
