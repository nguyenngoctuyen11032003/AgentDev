"""Carry the earlier turns of a session into a follow-up run.

Every message the user sends after a run finished starts a brand-new graph run, so
agents begin with empty conversations. To keep a chat coherent, the start node of a
follow-up run receives a compact transcript of the previous turns of the same
session (what the user asked, the questions the lead asked during the turn with the
user's replies, and the final answer they got), followed by the new message. Members
briefed by a team lead are not affected: the lead decides what to tell them.
"""

from typing import Any, Dict, Iterable, List, Optional

MAX_TURNS = 10
MAX_TRANSCRIPT_CHARS = 12_000
MAX_USER_CHARS = 2_000
MAX_ANSWER_CHARS = 4_000
MAX_EXCHANGES = 4
MAX_EXCHANGE_CHARS = 600

HEADER = (
    "[Earlier in this conversation, oldest first. Context only: decisions, approvals and facts in it still "
    "apply; do not redo finished work unless asked.]"
)
NEW_MESSAGE_HEADER = (
    "[The user's NEW message: answer this one, in its language. If it approves or answers what you proposed "
    "or asked above, act on it without asking again.]"
)


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def make_turn(
    user_text: Optional[str],
    answer: Optional[str],
    attachments: Iterable[str] = (),
    exchanges: Iterable[Dict[str, str]] = (),
    status: str = "completed",
) -> Dict[str, Any]:
    """One finished turn. ``exchanges``: questions asked to the user during the turn and the replies.

    ``status``: how the run ended ("completed", "cancelled" or "error").
    """
    turn: Dict[str, Any] = {
        "user": (user_text or "").strip(),
        "answer": (answer or "").strip(),
        "attachments": [str(name) for name in attachments or [] if name],
        "status": status or "completed",
    }
    kept = [
        {"question": str(e.get("question") or "").strip(), "answer": str(e.get("answer") or "").strip()}
        for e in exchanges or []
        if isinstance(e, dict) and (e.get("question") or e.get("answer"))
    ]
    if kept:
        turn["exchanges"] = kept[-MAX_EXCHANGES:]
    return turn


def _render_turn(index: int, turn: Dict[str, Any]) -> str:
    user = _clip(str(turn.get("user") or ""), MAX_USER_CHARS) or "(no text)"
    attachments = turn.get("attachments") or []
    if attachments:
        user += f"\n(attached: {', '.join(str(a) for a in attachments)})"
    lines = [f"--- Turn {index} ---", f"User: {user}"]
    for exchange in (turn.get("exchanges") or [])[-MAX_EXCHANGES:]:
        if not isinstance(exchange, dict):
            continue
        lines.append(f"You asked: {_clip(str(exchange.get('question') or ''), MAX_EXCHANGE_CHARS)}")
        lines.append(f"User replied: {_clip(str(exchange.get('answer') or ''), MAX_EXCHANGE_CHARS)}")
    answer = _clip(str(turn.get("answer") or ""), MAX_ANSWER_CHARS) or "(no answer was produced)"
    lines.append(f"You answered: {answer}")
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
    first_index = max(len(usable) - max_turns, 0)
    rendered = [_render_turn(i + 1, t) for i, t in enumerate(usable)][first_index:]
    omitted = first_index
    while len(rendered) > 1 and sum(len(r) + 2 for r in rendered) > max_chars:
        rendered.pop(0)
        omitted += 1
    body = "\n\n".join(rendered)
    if len(body) > max_chars:  # a single oversized turn: keep its tail (the answer)
        body = "…" + body[-(max_chars - 1):]
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
