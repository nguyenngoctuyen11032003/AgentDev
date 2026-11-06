"""Mask secret-looking strings before tool commands, outputs or errors are stored, shown or sent to a model.

Shared by the Lab (evidence, judge prompt) and the platform report. Best effort: it catches common credential
shapes (headers, ``key=value`` pairs, well-known token prefixes); it is not a guarantee.
"""

from __future__ import annotations

import re
from typing import Any

MASK = "[REDACTED]"

# Each pattern keeps group 1 (the label) and masks the rest of the match.
_SECRET_PATTERNS = (
    re.compile(r"(\bAuthorization\s*[\"']?\s*[:=]\s*[\"']?)(?:Bearer|Basic|Token|Digest)?\s*[^\s'\",}]+",
               re.IGNORECASE),
    re.compile(r"(\bBearer\s+)[^\s'\",}]+", re.IGNORECASE),
    re.compile(r"()\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"()\bgh[poursa]_[A-Za-z0-9]{20,}"),
    re.compile(r"()\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"()\bAIza[0-9A-Za-z_-]{30,}"),
    re.compile(r"()\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"()\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"(\b[\w-]*(?:api[_-]?key|access[_-]?key|token|secret|password|passwd|pwd)[\w-]*[\"']?\s*[=:]\s*"
               r"[\"']?)[^\s'\",}&]+", re.IGNORECASE),
)


def redact_secrets(text: Any) -> str:
    out = str(text or "")
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(lambda m: m.group(1) + MASK, out)
    return out
