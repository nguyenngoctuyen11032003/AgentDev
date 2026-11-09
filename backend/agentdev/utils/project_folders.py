"""Human-named project folders, like IntelliJ's ``~/IdeaProjects``.

A session that opened no project folder saves its work in ``<PROJECTS_DIR>/<project-name>/`` instead of a
``storage/warehouse/session_<uuid>/code_workspace`` nobody can find. The code sits at the project root; what
AgentDev itself writes (execution logs, token usage, attachments of a turn) goes to ``<project>/.agentdev/``.
Lab runs get ``<PROJECTS_DIR>/AgentDev_lab/<run-name>/`` the same way.

``PROJECTS_DIR`` is ``~/AgentDev`` unless ``AGENTDEV_PROJECTS_DIR`` says otherwise (see ``agentdev.paths``).
It is read at call time, so tests redirect it with one ``monkeypatch.setattr(paths, "PROJECTS_DIR", ...)``.
"""

from __future__ import annotations

import os
import re
import unicodedata
from pathlib import Path
from typing import Optional

from agentdev import paths

INTERNAL_DIRNAME = ".agentdev"
LAB_DIRNAME = "AgentDev_lab"
SLUG_MAX = 40
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
)


def projects_root() -> Path:
    return Path(paths.PROJECTS_DIR)


def lab_root() -> Path:
    return projects_root() / LAB_DIRNAME


def slugify(text: Optional[str], fallback: str = "project", max_len: int = SLUG_MAX) -> str:
    """A readable folder name: "Quản lý công việc nhóm!" -> "quan-ly-cong-viec-nhom".

    ASCII letters, digits and single hyphens only (Vietnamese diacritics and đ are folded), so the name is
    valid on every file system and never a Windows reserved name. Never empty."""
    folded = unicodedata.normalize("NFKD", (text or "").replace("đ", "d").replace("Đ", "D"))
    ascii_text = "".join(ch for ch in folded if not unicodedata.combining(ch)).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0] if "-" in slug[:max_len] else slug[:max_len]
        slug = slug.strip("-")
    if not slug:
        return fallback
    if slug in _WINDOWS_RESERVED:
        slug = f"{slug}-project"
    return slug


def create_project_dir(name: Optional[str], *, root: Optional[Path] = None, fallback: str = "project") -> Path:
    """Create ``<root>/<slug>`` (``-2``, ``-3`` ... when taken) and return it. The folder is new and empty:
    the name is never shared with another project, so two sessions can not write into each other's folder.
    ``.agentdev/`` carries its own ``.gitignore`` (``*``), so it stays out of git when the user starts one,
    and the project root itself stays empty until the agents write something."""
    base = Path(root) if root is not None else projects_root()
    base.mkdir(parents=True, exist_ok=True)
    slug = slugify(name, fallback)
    for number in range(1, 1000):
        candidate = base / (slug if number == 1 else f"{slug}-{number}")
        try:
            candidate.mkdir()  # atomic: fails when the name is taken (even by a concurrent run)
        except FileExistsError:
            continue
        internal = candidate / INTERNAL_DIRNAME
        internal.mkdir()
        (internal / ".gitignore").write_text("*\n", encoding="utf-8")
        return candidate.resolve()
    raise FileExistsError(f"No free project folder name for {slug!r} in {base}")


def internal_dir(project: Path) -> Path:
    """Where AgentDev keeps its own files of ``project`` (created on use)."""
    return Path(project) / INTERNAL_DIRNAME


def is_managed(path: Path | str | None) -> bool:
    """True for a folder AgentDev created under ``projects_root()`` (not one the user opened elsewhere)."""
    if not path:
        return False
    try:
        resolved = Path(path).resolve()
        root = projects_root().resolve()
    except (OSError, ValueError):
        return False
    return root in resolved.parents
