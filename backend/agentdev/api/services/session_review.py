"""What a finished session delivered, condensed for the user's review.

Built from the session's recorded WebSocket messages (the same ones a replay sends), so
it works for any saved run: the task and the user's replies, what each agent handed
over, the files that changed, and the final summary.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from agentdev.runtime.node.agent.team import PLAN_PROPOSED_EVENT, is_small_talk

OUTPUT_LIMIT = 6000
SUMMARY_LIMIT = 12000
REPLY_LIMIT = 2000
MAX_FILES = 200

VERDICTS = ("pending", "approved", "rework")
RUN_END_EVENTS = ("workflow_completed", "workflow_cancelled", "error")


def _text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _ms(timestamp: Any) -> Optional[float]:
    """Log timestamps are naive local ISO strings; expose them as epoch milliseconds."""
    if not isinstance(timestamp, str) or not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp).timestamp() * 1000
    except ValueError:
        return None


def build_digest(messages: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Condense a session's messages for review.

    A session is a conversation: each new message starts a run. Only the user's answers to the
    team count as ``replies`` (feedback): a reply typed while a run waited for input, or the
    answer to a plan the lead proposed. Any other message is a new request. The ``task`` is the
    latest real request (the delivered result answers it; greetings and thanks don't count);
    the other requests are listed in ``other_requests``. ``active_ms`` adds up the runs only;
    ``started_at``..``ended_at`` also spans the idle time between messages.
    """
    requests: List[Dict[str, Any]] = []
    replies: List[str] = []
    in_run = False  # a run is going: a message now answers its question
    after_plan = False  # the last run ended on a plan: the next message answers it
    active_ms = 0.0
    run_start = run_end = None
    steps: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    files: Dict[str, Dict[str, Any]] = {}
    summary = ""
    error = ""
    outcome = ""
    token_usage = None
    started_at = ended_at = None

    for message in messages:
        kind = message.get("type")
        data = message.get("data") or {}
        if not isinstance(data, dict):
            continue
        if kind == "error" and data.get("fatal") is False:
            continue  # about one client message (e.g. sent while busy); the run kept going

        if kind == "user_message":
            if requests and (in_run or after_plan):
                replies.append(_text(data.get("text"), REPLY_LIMIT))
            else:
                requests.append({"text": _text(data.get("text"), SUMMARY_LIMIT), "attachments": list(data.get("attachments") or [])})
            after_plan = False
            in_run = True

        elif kind == PLAN_PROPOSED_EVENT:
            after_plan = True

        elif kind == "log":
            at = _ms(data.get("timestamp"))
            if at is not None:
                started_at = at if started_at is None else min(started_at, at)
                ended_at = at if ended_at is None else max(ended_at, at)
                run_start = at if run_start is None else min(run_start, at)
                run_end = at if run_end is None else max(run_end, at)
            node_id = data.get("node_id")
            event = data.get("event_type")
            if not node_id or event not in ("NODE_START", "NODE_END"):
                continue
            if node_id not in steps:
                steps[node_id] = {"node_id": node_id, "runs": 0, "output": "", "started_at": at, "ended_at": None}
                order.append(node_id)
            step = steps[node_id]
            if event == "NODE_START":
                step["runs"] += 1
                if step["started_at"] is None:
                    step["started_at"] = at
            else:
                output = _text((data.get("details") or {}).get("output"), OUTPUT_LIMIT)
                if output:
                    step["output"] = output  # the last hand-over is what counts
                step["ended_at"] = at
                step["runs"] = max(step["runs"], 1)

        elif kind == "artifact_created":
            for item in data.get("events") or []:
                if not isinstance(item, dict):
                    continue
                path = item.get("relative_path") or item.get("file_name")
                if not path:
                    continue
                change = item.get("change_type") or "created"
                previous = files.get(path)
                # created then updated is still "created" from the reviewer's point of view
                if previous and previous["change"] == "created" and change == "updated":
                    change = "created"
                files[path] = {
                    "path": path,
                    "name": item.get("file_name") or path,
                    "change": change,
                    "node_id": item.get("node_id"),
                    "size": item.get("size"),
                    "attachment_id": item.get("attachment_id"),
                }

        if kind in RUN_END_EVENTS:
            in_run = False
            if run_start is not None:
                active_ms += run_end - run_start
            run_start = run_end = None

        if kind == "workflow_completed":
            outcome = "completed"
            summary = _text(data.get("summary"), SUMMARY_LIMIT)
            token_usage = data.get("token_usage")
        elif kind == "workflow_cancelled":
            outcome = "cancelled"
            error = _text(data.get("message"), REPLY_LIMIT)
        elif kind == "error":
            outcome = "error"
            error = _text(data.get("message"), REPLY_LIMIT)

    if run_start is not None:  # a run that never reported its end
        active_ms += run_end - run_start

    real = [r for r in requests if not is_small_talk(r["text"])]
    task = real[-1] if real else (requests[0] if requests else None)
    other_requests = [_text(r["text"], REPLY_LIMIT) for r in real if r is not task]

    # Without an explicit summary, the last agent's hand-over is the delivered result
    if not summary and order:
        last = next((steps[n]["output"] for n in reversed(order) if steps[n]["output"]), "")
        summary = last

    return {
        "task": task,
        "replies": replies,
        "other_requests": other_requests,
        "steps": [steps[n] for n in order],
        "files": list(files.values())[:MAX_FILES],
        "summary": summary,
        "error": error,
        "outcome": outcome,
        "token_usage": token_usage,
        "started_at": started_at,
        "ended_at": ended_at,
        "active_ms": active_ms,
    }


def clean_review(raw: Dict[str, Any], previous: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalise a review the UI sent; rounds of rework are counted, history is kept short."""
    verdict = raw.get("verdict") if raw.get("verdict") in VERDICTS else "pending"
    rating = raw.get("rating")
    rating = int(rating) if isinstance(rating, (int, float)) and 0 <= rating <= 5 else 0
    tags = [str(tag)[:60] for tag in (raw.get("tags") or []) if str(tag).strip()][:12]
    review = {
        "verdict": verdict,
        "rating": rating,
        "tags": tags,
        "feedback": str(raw.get("feedback") or "")[:4000],
        "rework_session_id": raw.get("rework_session_id") or (previous or {}).get("rework_session_id"),
        "reviewed_at": datetime.now().timestamp(),
    }
    history = list((previous or {}).get("history") or [])
    if previous and previous.get("verdict") in ("approved", "rework"):
        history.append({k: previous.get(k) for k in ("verdict", "rating", "tags", "feedback", "reviewed_at")})
    review["history"] = history[-10:]
    return review
