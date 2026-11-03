"""Shared skill library: the SKILL.md folders under ``workspace/skills`` that agents can tick.

A skill is ``<SKILLS_ROOT>/<name>/SKILL.md`` (plus optional supporting files). The runtime
(``AgentSkillManager``) already discovers this folder; this module adds create / edit /
delete and importing from another skills folder such as ``~/.claude/skills``.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

import yaml

from agentdev.paths import SKILLS_ROOT
from agentdev.runtime.node.agent.skills.manager import SkillValidationError, parse_skill_file
from agentdev.utils.exceptions import ValidationError
from agentdev.utils.workspace_paths import is_link, iter_tree_without_links

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MAX_SKILL_MD_BYTES = 256 * 1024
MAX_IMPORT_DIR_BYTES = 5 * 1024 * 1024
SKIPPED_IMPORT_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
DEFAULT_IMPORT_SOURCE = Path.home() / ".claude" / "skills"


@dataclass
class SkillEntry:
    name: str
    description: str
    valid: bool
    error: Optional[str]
    extra_files: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "valid": self.valid,
            "error": self.error,
            "extra_files": self.extra_files,
        }


def _root() -> Path:
    return Path(SKILLS_ROOT)


def validate_name(name: str) -> str:
    name = (name or "").strip()
    if not NAME_RE.match(name):
        raise ValidationError(
            "Skill name must be 1-64 characters: lowercase letters, digits and '-' (e.g. cto-management)"
        )
    return name


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return slug[:64].strip("-")


def _split_frontmatter(text: str) -> tuple[Optional[dict], str]:
    """Return (frontmatter or None, body). Raises ValidationError on malformed frontmatter."""
    stripped = text.lstrip(chr(0xFEFF))
    if not stripped.startswith("---"):
        return None, stripped
    lines = stripped.splitlines()
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            try:
                data = yaml.safe_load("\n".join(lines[1:idx])) or {}
            except yaml.YAMLError as exc:
                raise ValidationError(f"Invalid YAML frontmatter: {exc}") from exc
            if not isinstance(data, dict):
                raise ValidationError("Skill frontmatter must be a YAML mapping")
            return data, "\n".join(lines[idx + 1 :]).lstrip("\n")
    raise ValidationError("Frontmatter opened with '---' but never closed")


def build_skill_markdown(content: str, name: Optional[str] = None, description: Optional[str] = None) -> tuple[str, str]:
    """Normalise pasted text into a valid SKILL.md. Returns (name, markdown).

    - Text with frontmatter: its ``name``/``description`` are used; explicit arguments override.
    - Plain text (no frontmatter): ``name`` and ``description`` are required and a frontmatter is added.
    """
    if not isinstance(content, str) or not content.strip():
        raise ValidationError("Skill content is empty")
    if len(content.encode("utf-8")) > MAX_SKILL_MD_BYTES:
        raise ValidationError(f"SKILL.md is larger than {MAX_SKILL_MD_BYTES // 1024} KB")

    frontmatter, body = _split_frontmatter(content)
    meta = dict(frontmatter or {})
    if name and name.strip():
        meta["name"] = name.strip()
    if description and description.strip():
        meta["description"] = description.strip()

    raw_name = meta.get("name")
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ValidationError("Skill needs a name (add it in the form or as 'name:' in the frontmatter)")
    final_name = validate_name(raw_name)
    raw_desc = meta.get("description")
    if not isinstance(raw_desc, str) or not raw_desc.strip():
        raise ValidationError(
            "Skill needs a description saying when to use it (form field or 'description:' in the frontmatter)"
        )
    meta["name"] = final_name
    meta["description"] = " ".join(raw_desc.split())

    if not body.strip():
        raise ValidationError("Skill has no instructions after the frontmatter")

    header = yaml.safe_dump(meta, allow_unicode=True, sort_keys=False, width=10_000).strip()
    return final_name, f"---\n{header}\n---\n\n{body.rstrip()}\n"


def _count_extra_files(skill_dir: Path) -> int:
    return sum(1 for p in iter_tree_without_links(skill_dir) if p.is_file() and p.name != "SKILL.md")


def _refuse_link(path: Path) -> None:
    """A skill folder that is a symlink / junction points elsewhere: never write into or delete through it."""
    if is_link(path):
        raise ValidationError(
            f"Skill folder '{path.name}' is a link to another folder; remove the link by hand instead"
        )


def _entry_for(skill_dir: Path) -> SkillEntry:
    try:
        meta = parse_skill_file(skill_dir / "SKILL.md")
        return SkillEntry(meta.name, meta.description, True, None, _count_extra_files(skill_dir))
    except (SkillValidationError, OSError, UnicodeDecodeError) as exc:
        return SkillEntry(skill_dir.name, "", False, str(exc), 0)


def _iter_skill_dirs(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return []
    return [d for d in sorted(root.iterdir()) if d.is_dir() and (d / "SKILL.md").is_file()]


def list_skills() -> List[dict]:
    return [_entry_for(d).to_dict() for d in _iter_skill_dirs(_root())]


def _skill_dir(name: str) -> Path:
    return _root() / validate_name(name)


def get_skill(name: str) -> dict:
    skill_dir = _skill_dir(name)
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        raise FileNotFoundError(name)
    entry = _entry_for(skill_dir).to_dict()
    entry["content"] = skill_file.read_text(encoding="utf-8")
    return entry


def save_skill(
    content: str,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    overwrite: bool = False,
    rename_from: Optional[str] = None,
) -> dict:
    final_name, markdown = build_skill_markdown(content, name, description)
    root = _root()
    target = root / final_name

    if rename_from and validate_name(rename_from) != final_name:
        source = root / validate_name(rename_from)
        _refuse_link(source)
        if not source.is_dir():
            raise FileNotFoundError(rename_from)
        if target.exists() or is_link(target):
            raise FileExistsError(final_name)
        source.rename(target)
    elif rename_from:
        # Editing in place: the skill must already exist (an edit never creates one).
        _refuse_link(target)
        if not (target / "SKILL.md").is_file():
            raise FileNotFoundError(rename_from)
    elif target.exists() or is_link(target):
        if not overwrite:
            raise FileExistsError(final_name)
        _refuse_link(target)

    target.mkdir(parents=True, exist_ok=True)
    (target / "SKILL.md").write_text(markdown, encoding="utf-8")
    return get_skill(final_name)


def delete_skill(name: str) -> None:
    skill_dir = _skill_dir(name)
    _refuse_link(skill_dir)
    if not skill_dir.is_dir():
        raise FileNotFoundError(name)
    shutil.rmtree(skill_dir)


def _dir_size(path: Path) -> int:
    """Bytes that an import would copy: links and skipped folders are not followed or counted."""
    total = 0
    for current, dirnames, filenames in os.walk(path, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in SKIPPED_IMPORT_DIRS and not is_link(Path(current) / d)]
        for filename in filenames:
            file_path = Path(current) / filename
            if not is_link(file_path):
                total += file_path.stat().st_size
    return total


def _ignore_links_and_junk(directory: str, names: List[str]) -> set:
    """``copytree`` ignore hook: drop links (never copy what they point to) and skipped folders."""
    return {n for n in names if n in SKIPPED_IMPORT_DIRS or is_link(Path(directory) / n)}


def _import_one(src: Path, dest: Path, overwrite: bool) -> str:
    """Copy one skill folder. Returns "imported" or "skipped"; raises on a problem."""
    if is_link(src):
        # Installers (npx skills, Claude Code) expose skills as links into a shared store.
        # The top-level folder is the user's own pick, so copy the real folder it points to;
        # links *inside* the skill are still never followed (see _ignore_links_and_junk).
        resolved = Path(os.path.realpath(src))
        if not resolved.is_dir() or is_link(resolved):
            raise ValidationError("Source skill folder is a broken link")
        src = resolved
    entry = _entry_for(src) if (src / "SKILL.md").is_file() and not is_link(src / "SKILL.md") else None
    if entry is None or not entry.valid:
        raise ValidationError(entry.error if entry else "SKILL.md not found")
    if _dir_size(src) > MAX_IMPORT_DIR_BYTES:
        raise ValidationError(f"Folder is larger than {MAX_IMPORT_DIR_BYTES // (1024 * 1024)} MB")
    if dest.exists() or is_link(dest):
        if not overwrite:
            return "skipped"
        _refuse_link(dest)
        shutil.rmtree(dest)
    try:
        shutil.copytree(src, dest, symlinks=True, ignore=_ignore_links_and_junk)
    except BaseException:
        if dest.is_dir() and not is_link(dest):
            shutil.rmtree(dest, ignore_errors=True)  # no half-copied skill left behind
        raise
    return "imported"


def list_import_source(source: Optional[str] = None) -> dict:
    src = Path(source).expanduser() if source else DEFAULT_IMPORT_SOURCE
    existing = {d.name for d in _iter_skill_dirs(_root())}
    items = []
    for skill_dir in _iter_skill_dirs(src):
        entry = _entry_for(skill_dir)
        items.append({**entry.to_dict(), "imported": entry.name in existing})
    return {"source": str(src), "exists": src.is_dir(), "skills": items}


def import_skills(names: List[str], *, source: Optional[str] = None, overwrite: bool = False) -> dict:
    src_root = Path(source).expanduser() if source else DEFAULT_IMPORT_SOURCE
    if not src_root.is_dir():
        raise ValidationError(f"Skills folder not found: {src_root}")
    root = _root()
    root.mkdir(parents=True, exist_ok=True)

    imported, skipped, failed = [], [], []
    for raw in names:
        try:
            name = validate_name(raw)
        except ValidationError as exc:
            failed.append({"name": raw, "error": str(exc)})
            continue
        try:
            outcome = _import_one(src_root / name, root / name, overwrite)
        except ValidationError as exc:
            failed.append({"name": name, "error": str(exc)})
            continue
        except PermissionError as exc:
            failed.append({"name": name, "error": f"Permission denied (file in use or read-only): {exc}"})
            continue
        except (OSError, shutil.Error) as exc:
            failed.append({"name": name, "error": f"Could not copy: {exc}"})
            continue
        (imported if outcome == "imported" else skipped).append(name)
    return {"imported": imported, "skipped": skipped, "failed": failed}
