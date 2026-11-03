"""Carry the earlier turns of a session into a follow-up run.

Every message the user sends after a run finished starts a brand-new graph run, so
agents begin with empty conversations. To keep a chat coherent, the start node of a
follow-up run receives a compact transcript of the previous turns of the same
session (what the user asked, the questions the lead asked during the turn with the
user's replies, what the team did, and the final answer they got), followed by the new
message. Members briefed by a team lead are not affected: the lead decides what to tell
them (their own earlier reports reach their brief through the team state).
"""

from typing import Any, Dict, Iterable, List, Optional

from agentdev.runtime.node.agent.team import DELEGATION_KIND, MAX_DIGEST_ENTRIES, clip_middle

MAX_TURNS = 10
MAX_TRANSCRIPT_CHARS = 20_000
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

HEADER = (
    "[Earlier in this conversation, oldest first. Context only: decisions, approvals and facts in it still "
    "apply; do not redo finished work unless asked.]"
)
NEW_MESSAGE_HEADER = (
    "[The user's NEW message: answer this one, in its language. If it approves or answers what you proposed "
    "or asked above, act on it without asking again.]"
)
STATUS_NOTES = {
    "cancelled": "(This turn was cancelled before it finished: the work may be incomplete.)",
    "error": "(This turn ended with an error before it finished: the work may be incomplete.)",
}


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
        "attachments": [str(name) for name in attachments or [] if name],
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


def _render_turn(index: int, turn: Dict[str, Any], *, latest: bool = False, team_budget: int = 0) -> str:
    user = _clip(str(turn.get("user") or ""), MAX_LATEST_USER_CHARS if latest else MAX_USER_CHARS) or "(no text)"
    attachments = turn.get("attachments") or []
    if attachments:
        user += f"\n(attached: {', '.join(str(a) for a in attachments)})"
    lines = [f"--- Turn {index} ---", f"User: {user}"]
    for exchange in (turn.get("exchanges") or [])[-MAX_EXCHANGES:]:
        if not isinstance(exchange, dict):
            continue
        lines.append(f"You asked: {_clip(str(exchange.get('question') or ''), MAX_QUESTION_CHARS)}")
        lines.append(f"User replied: {_clip(str(exchange.get('answer') or ''), MAX_REPLY_CHARS)}")
    if team_budget > 0 and isinstance(turn.get("team"), list):
        lines.extend(_render_team(turn["team"], team_budget))
    note = STATUS_NOTES.get(str(turn.get("status") or "").strip().lower())
    if note:
        lines.append(note)
    answer = _clip(str(turn.get("answer") or ""), MAX_LATEST_ANSWER_CHARS if latest else MAX_ANSWER_CHARS)
    lines.append(f"You answered: {answer or '(no answer was produced)'}")
    return "\n".join(lines)


def build_transcript(
    turns: List[Dict[str, Any]],
    *,
    max_turns: int = MAX_TURNS,
    max_chars: int = MAX_TRANSCRIPT_CHARS,
) -> str:
    """Render the latest turns, dropping the oldest ones until the text fits ``max_chars``."""
    usable = [t for t in turns or [] if isinstance(t, dict) and (t.get("user") or t.get("answer"))]
    if not usable:
        return ""
    last = len(usable) - 1
    first_index = max(len(usable) - max_turns, 0)

    def team_budget(i: int) -> int:
        if i == last:
            return MAX_TEAM_CHARS_LATEST
        return MAX_TEAM_CHARS_OLDER if i > last - TEAM_DIGEST_TURNS else 0

    rendered = [
        _render_turn(i + 1, t, latest=i == last, team_budget=team_budget(i))
        for i, t in enumerate(usable)
    ][first_index:]
    omitted = first_index
    while len(rendered) > 1 and sum(len(r) + 2 for r in rendered) > max_chars:
        rendered.pop(0)
        omitted += 1
    body = "\n\n".join(rendered)
    if len(body) > max_chars:  # a single oversized turn: keep its start (the request) and end (the answer)
        body = clip_middle(body, max_chars, head_ratio=0.4)
    lines = [HEADER]
    if omitted:
        lines.append(f"({omitted} older turn(s) omitted)")
    lines.append(body)
    return "\n".join(lines)


def compose_follow_up_prompt(turns: List[Dict[str, Any]], prompt: str) -> str:
    """Prefix ``prompt`` with the session transcript; unchanged when there is no history."""
    transcript = build_transcript(turns)
    if not transcript:
        return prompt
    return f"{transcript}\n\n{NEW_MESSAGE_HEADER}\n{prompt or ''}".rstrip()
