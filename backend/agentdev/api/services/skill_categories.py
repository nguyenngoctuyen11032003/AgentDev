"""Group library skills into categories (dev, video, design, ...) so a large library stays easy to browse.

A skill's category is, in order:
1. set by hand: ``metadata.category`` (or a top-level ``category``) in its SKILL.md frontmatter;
2. otherwise guessed from keywords in its name (weighted) and description.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple

OTHER = "other"

# Display order of the categories.
CATEGORIES: Tuple[str, ...] = (
    "video", "image", "audio", "motion", "marketing", "design", "dev", "workflow", "docs", OTHER,
)
# Order that breaks a tie between two guesses: the more specific domain wins ("api-design" is dev,
# "bfl-api" is image, "using-git-worktrees" is workflow).
_TIE_ORDER: Tuple[str, ...] = ("video", "image", "audio", "motion", "marketing", "workflow", "dev", "design", "docs")

_KEYWORDS: Dict[str, Tuple[str, ...]] = {
    "video": (
        "video", "videos", "footage", "remotion", "hyperframes", "heygen", "kling", "seedance", "ltx2", "veo",
        "avatar", "montage", "film", "clip", "clips", "ffmpeg", "moviepy", "reel", "reels", "youtube", "shorts",
        "previz", "storyboard", "caption", "captions", "subtitle", "subtitles", "vox", "director", "broll",
        "cinematic", "screencast", "recording", "trailer", "slideshow", "explainer", "mp4", "translate",
    ),
    "image": (
        "image", "images", "photo", "photos", "picture", "sticker", "sprite", "flux", "ideogram", "midjourney",
        "illustration", "thumbnail", "faceswap", "gif", "logo", "bfl", "qwen", "comfyui", "mockup", "mockups",
        "moodboard", "png", "jpeg",
    ),
    "audio": (
        "audio", "music", "sound", "sounds", "speech", "voice", "voices", "tts", "voiceover", "elevenlabs",
        "podcast", "lyria", "acestep", "song", "songs", "jingle", "sfx", "transcribe", "transcription", "whisper",
        "stt", "doubao", "narration",
    ),
    "motion": (
        "animation", "animations", "animate", "animated", "gsap", "threejs", "three", "3d", "lottie", "bodymovin",
        "manim", "manimce", "manimgl", "motion", "shader", "shaders", "kinetic", "transition", "transitions",
        "webgl", "scrolltrigger", "timeline", "keyframe", "keyframes", "d3",
    ),
    "marketing": (
        "ad", "ads", "advert", "advertising", "marketing", "ecommerce", "campaign", "seo", "social", "shop",
        "dropship", "ugc", "compliance", "hook", "hooks", "brand", "product", "unboxing", "tryon", "conversion",
        "localize", "tiktok",
    ),
    "design": (
        "design", "designs", "ui", "ux", "frontend", "interface", "interfaces", "figma", "tailwind", "typography",
        "layout", "visual", "css", "landing", "style", "styles", "theme", "palette", "accessibility", "a11y",
        "responsive", "impeccable", "taste", "redesign", "polish",
    ),
    "docs": (
        "doc", "docs", "document", "documents", "documentation", "writing", "write", "pdf", "docx", "pptx", "xlsx",
        "report", "adr", "adrs", "markdown", "mermaid", "research", "resume", "cv", "slides", "glossary",
    ),
    "workflow": (
        "plan", "plans", "planning", "brainstorm", "brainstorming", "agents", "agent", "subagent", "subagents",
        "parallel", "dispatching", "worktree", "worktrees", "handoff", "grilling", "grill", "idea", "ideas",
        "spec", "executing", "finishing", "skills", "skill", "prompt", "context", "superpowers", "breakdown",
        "doubt", "verification", "delegate",
    ),
    "dev": (
        "code", "coding", "codebase", "test", "tests", "testing", "debug", "debugging", "git", "api", "apis",
        "refactor", "review", "security", "hardening", "performance", "ci", "cd", "deploy", "deployment",
        "database", "python", "react", "vue", "backend", "bug", "bugs", "pr", "prs", "commit", "architecture",
        "observability", "lint", "playwright", "pre", "implementation", "simplification", "shipping", "rest",
        "github", "scratchpad", "error", "vercel", "nextjs", "typescript",
    ),
}

_WORD = re.compile(r"[a-z0-9]+")
_NAME_WEIGHT = 3


def _words(text: str) -> set[str]:
    return set(_WORD.findall((text or "").lower()))


def guess_category(name: str, description: str = "") -> str:
    """Best keyword match for a skill; ``other`` when nothing matches."""
    name_words = _words(name)
    desc_words = _words(description)
    best, best_score = OTHER, 0
    for category in _TIE_ORDER:
        keywords = _KEYWORDS.get(category, ())
        score = _NAME_WEIGHT * sum(1 for k in keywords if k in name_words) + sum(1 for k in keywords if k in desc_words)
        if score > best_score:  # strict: on a tie the earlier category in _TIE_ORDER wins
            best, best_score = category, score
    return best


def explicit_category(frontmatter: Optional[Mapping[str, Any]]) -> Optional[str]:
    """The category written in the frontmatter, if it is a known one."""
    if not frontmatter:
        return None
    metadata = frontmatter.get("metadata")
    candidates: Iterable[Any] = (
        metadata.get("category") if isinstance(metadata, Mapping) else None,
        frontmatter.get("category"),
    )
    for value in candidates:
        if isinstance(value, str) and value.strip().lower() in CATEGORIES:
            return value.strip().lower()
    return None


def categorize(name: str, description: str, frontmatter: Optional[Mapping[str, Any]]) -> Tuple[str, str]:
    """Return (category, source) where source is ``manual`` or ``auto``."""
    manual = explicit_category(frontmatter)
    if manual:
        return manual, "manual"
    return guess_category(name, description), "auto"
