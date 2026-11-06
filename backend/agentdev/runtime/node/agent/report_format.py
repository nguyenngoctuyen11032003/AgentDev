"""Field-wise clipping of member reports and old tool results (flag AGENTDEV_STRUCTURED_REPORT, ADR 0007).

A member's report is free text. When it is longer than the lead's cap, the old cut kept the first and last
half and dropped the middle, which is where file:line evidence and command results usually sit. Here the report is
split into fields (summary, evidence file:line, commands + results, files changed, open items), each field gets
its own share of the same total cap, and inside a field the newest lines are kept first (errors first for
commands). Pure functions, no I/O.
"""

from __future__ import annotations

import os
import re
from typing import Callable, List

STRUCTURED_REPORT_DEFAULT = False


def structured_report_enabled() -> bool:
    raw = os.environ.get("AGENTDEV_STRUCTURED_REPORT")
    if raw is None or not raw.strip():
        return STRUCTURED_REPORT_DEFAULT
    return raw.strip().lower() not in ("0", "false", "off", "no")


_EVIDENCE_RE = re.compile(r"[\w./\\-]+\.[A-Za-z]{1,6}:\d+")
_PATH_RE = re.compile(
    r"(?:[\w.-]+[/\\])+[\w.-]+\.[A-Za-z]{1,6}\b|\b[\w-]+\.(?:py|js|ts|vue|json|ya?ml|md|css|html|rs|go|java|cs)\b"
)
_COMMAND_RE = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\$ |`?(?:npm|npx|pnpm|yarn|pytest|uv|python|pip|git|make|cargo|go|dotnet|node)\b)"
    r"|\b(?:exit code|exit status|tests? (?:passed|failed)|\d+ passed|\d+ failed)\b",
    re.IGNORECASE,
)
_ERROR_RE = re.compile(r"error|fail|exception|traceback|denied|not found|timeout|lỗi|thất bại", re.IGNORECASE)
_OPEN_HEAD_RE = re.compile(
    r"^\s*(?:#+\s*|[-*]\s*|\*\*)?(?:open|unresolved|todo|blocked|risks?|not (?:run|verified)|còn|chưa|vấn đề)",
    re.IGNORECASE,
)
_HEADING_RE = re.compile(r"^\s*(?:#+\s+|\*\*[^*]+\*\*:?\s*$|[A-Za-zÀ-ỹ ]{3,30}:?\s*$)")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_CHANGED_RE = re.compile(
    r"\b(?:changed|created|edited|updated|added|modified|deleted|wrote|sửa|tạo|thêm|xóa|cập nhật)\b", re.IGNORECASE
)

# Share of the cap per field (unused room flows on; what is left goes to the summary prose).
_SHARES = (("Evidence", 0.30), ("Commands", 0.22), ("Files changed", 0.15), ("Open", 0.20))


def _classify(lines: List[str]) -> dict:
    fields: dict = {"Evidence": [], "Commands": [], "Files changed": [], "Open": [], "prose": []}
    in_open = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            in_open = False  # an open-items list ends at the first blank line
            fields["prose"].append(line)
            continue
        if _HEADING_RE.match(line) and not _EVIDENCE_RE.search(line) and not _COMMAND_RE.search(line):
            in_open = bool(_OPEN_HEAD_RE.match(line))
            fields["prose"].append(line)
            continue
        if _EVIDENCE_RE.search(line):
            fields["Evidence"].append(stripped)
        elif _COMMAND_RE.search(line):
            fields["Commands"].append(stripped)
        elif (in_open and _BULLET_RE.match(line)) or _OPEN_HEAD_RE.match(line) or stripped.upper().startswith("DECISION NEEDED"):
            fields["Open"].append(stripped)
        elif _PATH_RE.search(line) and _CHANGED_RE.search(line):
            fields["Files changed"].append(stripped)
        else:
            fields["prose"].append(line)
    return fields


def _fit(lines: List[str], room: int, errors_first: bool = False) -> tuple[List[str], int]:
    """Whole lines that fit in ``room`` chars: errors first if asked, then newest (last) first; shown in original order."""
    lines = list(lines)
    order = sorted(range(len(lines)), key=lambda i: (0 if errors_first and _ERROR_RE.search(lines[i]) else 1, -i))
    chosen: set = set()
    used = 0
    for i in order:
        if len(lines[i]) + 1 > room and not chosen:
            lines[i] = lines[i][: max(room - 2, 10)] + "…"  # one oversized line must not empty the field
        cost = len(lines[i]) + 1
        if used + cost > room:
            continue
        chosen.add(i)
        used += cost
    kept = [lines[i] for i in sorted(chosen)]
    return kept, len(lines) - len(kept)


def structure_report(text: str, limit: int, fallback: Callable[[str, int], str]) -> str:
    """At most about ``limit`` chars; text within the cap is returned unchanged."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    fields = _classify(text.splitlines())
    if not any(fields[name] for name, _ in _SHARES):
        return fallback(text, limit)  # nothing structured to keep: plain head + tail
    blocks: List[str] = []
    dropped = 0
    room_left = int(limit * 0.9)  # the rest is for the omission note
    carry = 0
    for name, share in _SHARES:
        lines = fields[name]
        if not lines:
            carry += int(limit * share)
            continue
        room = min(int(limit * share) + carry, room_left)
        kept, cut = _fit(lines, max(room - len(name) - 3, 0), errors_first=(name == "Commands"))
        dropped += cut
        used = sum(len(line) + 1 for line in kept) + len(name) + 3 if kept else 0
        carry = max(room - used, 0)
        room_left -= used
        if kept:
            blocks.append(name + ":\n" + "\n".join(kept))
    prose = "\n".join(line for line in fields["prose"] if line.strip())
    prose_room = max(room_left, int(limit * 0.25))
    summary = fallback(prose, prose_room) if len(prose) > prose_room else prose
    note = f"[report clipped from {len(text)} chars" + (f"; {dropped} detail lines omitted" if dropped else "") + "]"
    result = "\n\n".join(([summary] if summary else []) + blocks + [note])
    if len(result) > limit + 120:  # hard guard: never beat the cap by much
        result = fallback(result, limit)
    return result


def clip_old_result(text: str, limit: int) -> str:
    """Old tool result for later model calls: head and tail kept, error lines of the middle kept first."""
    if len(text) <= limit:
        return text
    head_n, tail_n = int(limit * 0.4), int(limit * 0.3)
    middle = text[head_n: len(text) - tail_n]
    errors = [line.strip() for line in middle.splitlines() if _ERROR_RE.search(line)]
    kept, _ = _fit(errors, limit - head_n - tail_n) if errors else ([], 0)
    head = text[:head_n].rstrip()
    tail = text[len(text) - tail_n:].lstrip()
    if kept:
        mid = "\n[… errors from the omitted middle …]\n" + "\n".join(kept) + "\n[…]\n"
    else:
        mid = f"\n[… {len(middle)} chars omitted …]\n"
    return head + mid + tail
