"""Vetted workflow skeletons the assistant starts from.

Each ``*.yaml`` file here begins with a comment header (``# id:``, ``# keywords:``, ``# when:``,
``# slots:``) followed by a complete workflow that passes the static check. ``pick_pattern`` scores the
conversation against the keywords; only the best pattern is added to the turn context.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Optional, Tuple

PATTERN_DIR = Path(__file__).parent


@dataclass(frozen=True)
class Pattern:
    id: str
    keywords: Tuple[str, ...]
    when: str
    slots: str
    yaml: str  # the whole file, header included


def fold(text: str) -> str:
    """Lower-case, accent-free text (``đ`` too), so Vietnamese typed with or without accents matches."""
    text = unicodedata.normalize("NFD", (text or "").lower().replace("đ", "d"))
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def _header(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        match = re.match(r"#\s*(id|keywords|when|slots):\s*(.*)", line)
        if not match:
            break
        out[match.group(1)] = match.group(2).strip()
    return out


@lru_cache(maxsize=1)
def load_patterns() -> Tuple[Pattern, ...]:
    patterns: List[Pattern] = []
    for path in sorted(PATTERN_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        head = _header(text)
        keywords = tuple(fold(k.strip()) for k in head.get("keywords", "").split(",") if k.strip())
        patterns.append(Pattern(head.get("id") or path.stem, keywords, head.get("when", ""),
                                head.get("slots", ""), text))
    return tuple(patterns)


def pick_pattern(user_text: str) -> Optional[Pattern]:
    """The pattern whose keywords match ``user_text`` most often (whole words or phrases), else None."""
    haystack = fold(user_text)
    best: Optional[Pattern] = None
    best_score = 0
    for pattern in load_patterns():
        score = sum(1 for k in pattern.keywords if re.search(rf"(?<!\w){re.escape(k)}(?!\w)", haystack))
        if score > best_score:
            best, best_score = pattern, score
    return best


def pattern_fragment(pattern: Pattern) -> str:
    """The pattern as text for the turn context (header comments kept: they say when and what to fill)."""
    return pattern.yaml.rstrip() + "\n"
