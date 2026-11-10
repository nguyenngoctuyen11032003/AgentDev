"""Read an episode production package (series/tap_<n>/goi_san_xuat.md) by code, not by a model.

Shared by the Veo renderer (workspace/functions/function_calling/video_gen.py) and the "Prompt cho Flow" button,
so the prompts a user pastes into Google Flow are exactly the ones AgentDev would send to Veo:
each shot line ``**N.** IMG: ... VID: ...``, the shot durations from the shot table, the shared style line, and
the character tags (``[LINH-v1]``) expanded from the ``Appearance:`` lines of series/ho_so_nhan_vat.md.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

PACKAGE_FILE = "goi_san_xuat.md"
BIBLE_FILE = "ho_so_nhan_vat.md"
DEFAULT_SHOT_SECONDS = 6.0

_SHOT_RE = re.compile(r"^\s*\*\*(\d+)\.\*\*\s*IMG:\s*(.*?)\s*VID:\s*(.+?)\s*$", re.MULTILINE)
_ROW_RE = re.compile(r"^\|\s*(\d+)\s*\|[^|\n]*\|\s*(\d+(?:[.,]\d+)?)\s*\|", re.MULTILINE)
_STYLE_RE = re.compile(r"^.*?Style(?: chung)?\s*:\s*(.+)$", re.MULTILINE | re.IGNORECASE)
TAG_RE = re.compile(r"\[([A-Z0-9_]+-v\d+)\]")


def parse_package(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """(shared style, shots) from a production package; each shot has number, seconds, img and vid prompts."""
    style_match = _STYLE_RE.search(text)
    style = style_match.group(1).strip() if style_match else ""
    seconds = {int(n): float(s.replace(",", ".")) for n, s in _ROW_RE.findall(text)}
    shots = []
    for number, img, vid in _SHOT_RE.findall(text):
        n = int(number)
        shots.append({"number": n, "seconds": seconds.get(n, DEFAULT_SHOT_SECONDS), "img": img.strip(),
                      "vid": vid.strip()})
    shots.sort(key=lambda s: s["number"])
    return style, shots


def parse_bible(text: str) -> Dict[str, str]:
    """Tag -> appearance, from heading tags followed by an ``Appearance:`` line, or both on one line."""
    looks: Dict[str, str] = {}
    current: Optional[str] = None
    for line in text.splitlines():
        tags = TAG_RE.findall(line)
        lowered = line.lower()
        if "appearance:" in lowered:
            look = line[lowered.index("appearance:") + len("appearance:"):]
            owner = tags[0] if tags else current
            if owner and look.strip():
                looks[owner] = look.strip().rstrip(".")
        elif tags and line.lstrip().startswith("#"):
            current = tags[0]
    return looks


def expand_tags(prompt: str, looks: Dict[str, str]) -> str:
    """Replace each known [TAG] with its appearance (video models know nothing about our tags)."""
    return TAG_RE.sub(lambda m: f"({looks[m.group(1)]})" if m.group(1) in looks else m.group(0), prompt)


def shot_prompts(shot: Dict[str, Any], style: str, looks: Dict[str, str]) -> Tuple[str, str]:
    """(video prompt, first-frame image prompt) of a shot."""
    # Keep this text byte-for-byte: it is hashed into each clip's key (video_gen._shot_key), and any change makes
    # a re-run pay again for clips already made or started.
    lead = f"{style}. " if style else ""
    image = f"{lead}{expand_tags(shot['img'], looks)}"
    return f"{image} Motion: {expand_tags(shot['vid'], looks)}", image


def flow_prompts(package_text: str, bible_text: str = "") -> Dict[str, Any]:
    """Every shot's prompt, ready to paste into Google Flow (Veo in a Google AI subscription), in shot order.

    ``missing_tags``: character tags no Appearance line explains (the bible is missing or lacks them); they stay
    as written, so the user knows those characters may not look the same from shot to shot.
    """
    style, shots = parse_package(package_text)
    looks = parse_bible(bible_text) if bible_text else {}
    missing: set[str] = set()
    out = []
    for shot in shots:
        prompt, image_prompt = shot_prompts(shot, style, looks)
        missing.update(tag for tag in TAG_RE.findall(f"{shot['img']} {shot['vid']}") if tag not in looks)
        out.append({"number": shot["number"], "seconds": shot["seconds"], "prompt": prompt,
                    "image_prompt": image_prompt})
    return {"style": style, "shots": out, "missing_tags": sorted(missing)}
