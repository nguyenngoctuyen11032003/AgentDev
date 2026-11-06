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

from agentdev.api.services.skill_categories import CATEGORIES, categorize
from agentdev.paths import SKILLS_ROOT
from agentdev.runtime.node.agent.skills.manager import SkillValidationError, parse_skill_file
from agentdev.utils.exceptions import ValidationError
from agentdev.utils.workspace_paths import is_link, iter_tree_without_links

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MAX_SKILL_MD_BYTES = 256 * 1024
# Public video skills ship tens of MB of example media (hyperframes-animation ~39 MB); the cap only stops a
# wrong folder (a whole repo) from being copied.
MAX_IMPORT_DIR_BYTES_DEFAULT = 64 * 1024 * 1024
MAX_IMPORT_DIR_BYTES = MAX_IMPORT_DIR_BYTES_DEFAULT
AUTO_CATEGORY = "auto"
# Human-facing notes kept in ``metadata.guide``: what the skill is for, when to pick it, what it brings,
# what it needs and whether it costs money. Agents never see them (only name + description reach prompts).
GUIDE_TEXT_FIELDS = ("purpose", "when", "benefit", "requires")
MAX_GUIDE_FIELD_CHARS = 400
SKIPPED_IMPORT_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
DEFAULT_IMPORT_SOURCE = Path.home() / ".claude" / "skills"


@dataclass
class SkillEntry:
    name: str
    description: str
    valid: bool
    error: Optional[str]
    extra_files: int
    category: str = "other"
    category_source: str = "auto"
    guide: Optional[dict] = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "valid": self.valid,
            "error": self.error,
            "extra_files": self.extra_files,
            "category": self.category,
            "category_source": self.category_source,
            "guide": self.guide,
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


def _apply_category(meta: dict, category: Optional[str]) -> None:
    """Set ``metadata.category`` (a known category) or remove it (``auto``); None leaves it as written."""
    if category is None:
        return
    category = category.strip().lower()
    if category != AUTO_CATEGORY and category not in CATEGORIES:
        raise ValidationError(f"Unknown category '{category}'. Use one of: {', '.join(CATEGORIES)} or auto")
    metadata = meta.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValidationError("Frontmatter 'metadata' must be a mapping to hold a category")
    metadata = dict(metadata or {})
    meta.pop("category", None)  # one place only: metadata.category
    if category == AUTO_CATEGORY:
        metadata.pop("category", None)
    else:
        metadata["category"] = category
    if metadata:
        meta["metadata"] = metadata
    else:
        meta.pop("metadata", None)


def _read_guide(frontmatter: Optional[dict]) -> Optional[dict]:
    """``metadata.guide`` as {purpose, when, benefit, requires, paid}; None when absent or empty."""
    metadata = (frontmatter or {}).get("metadata")
    raw = metadata.get("guide") if isinstance(metadata, dict) else None
    if not isinstance(raw, dict):
        return None
    guide = {key: " ".join(str(raw.get(key) or "").split()) for key in GUIDE_TEXT_FIELDS}
    guide["paid"] = raw.get("paid") is True
    return guide if any(guide[k] for k in GUIDE_TEXT_FIELDS) or guide["paid"] else None


def _apply_guide(meta: dict, guide: Optional[dict]) -> None:
    """Store ``guide`` in ``metadata.guide``; an empty dict removes it; None leaves it as written."""
    if guide is None:
        return
    if not isinstance(guide, dict):
        raise ValidationError("Skill guide must be an object")
    clean = {}
    for key in GUIDE_TEXT_FIELDS:
        value = " ".join(str(guide.get(key) or "").split())
        if len(value) > MAX_GUIDE_FIELD_CHARS:
            raise ValidationError(f"Guide field '{key}' is longer than {MAX_GUIDE_FIELD_CHARS} characters")
        if value:
            clean[key] = value
    if guide.get("paid") is True:
        clean["paid"] = True
    metadata = meta.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise ValidationError("Frontmatter 'metadata' must be a mapping to hold a guide")
    metadata = dict(metadata or {})
    if clean:
        metadata["guide"] = clean
    else:
        metadata.pop("guide", None)
    if metadata:
        meta["metadata"] = metadata
    else:
        meta.pop("metadata", None)


def build_skill_markdown(
    content: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    category: Optional[str] = None,
    guide: Optional[dict] = None,
) -> tuple[str, str]:
    """Normalise pasted text into a valid SKILL.md. Returns (name, markdown).

    - Text with frontmatter: its ``name``/``description`` are used; explicit arguments override.
    - Plain text (no frontmatter): ``name`` and ``description`` are required and a frontmatter is added.
    - ``category``: a known category is stored as ``metadata.category``; ``auto`` removes it.
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
    _apply_category(meta, category)
    _apply_guide(meta, guide)

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
        category, source = categorize(meta.name, meta.description, meta.frontmatter)
        return SkillEntry(
            meta.name, meta.description, True, None, _count_extra_files(skill_dir), category, source,
            _read_guide(dict(meta.frontmatter)),
        )
    except (SkillValidationError, OSError, UnicodeDecodeError) as exc:
        category, source = categorize(skill_dir.name, "", None)
        return SkillEntry(skill_dir.name, "", False, str(exc), 0, category, source)


def _iter_skill_dirs(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        return []
    return [
        d for d in sorted(root.iterdir()) if not d.name.startswith(".") and d.is_dir() and (d / "SKILL.md").is_file()
    ]


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
    entry["content"] = skill_file.read_text(encoding="utf-8", errors="replace")
    return entry


def save_skill(
    content: str,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    overwrite: bool = False,
    rename_from: Optional[str] = None,
    category: Optional[str] = None,
    guide: Optional[dict] = None,
) -> dict:
    final_name, markdown = build_skill_markdown(content, name, description, category, guide)
    root = _root()
    target = root / final_name

    write_dir = target
    renaming = False
    if rename_from and validate_name(rename_from) != final_name:
        source = root / validate_name(rename_from)
        _refuse_link(source)
        if not source.is_dir():
            raise FileNotFoundError(rename_from)
        if target.exists() or is_link(target):
            raise FileExistsError(final_name)
        write_dir, renaming = source, True
    elif rename_from:
        # Editing in place: the skill must already exist (an edit never creates one).
        _refuse_link(target)
        if not (target / "SKILL.md").is_file():
            raise FileNotFoundError(rename_from)
    elif target.exists() or is_link(target):
        if not overwrite:
            raise FileExistsError(final_name)
        _refuse_link(target)

    write_dir.mkdir(parents=True, exist_ok=True)
    _atomic_write(write_dir / "SKILL.md", markdown)
    if renaming:
        # Rename only after the new text is safely on disk.
        write_dir.rename(target)
    return get_skill(final_name)


def _atomic_write(path: Path, text: str) -> None:
    """Write via a temp file next to ``path`` and ``os.replace`` it: a crash never leaves a cut-off file."""
    tmp = path.with_name(f".{path.name}.tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


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
    replacing = dest.exists() or is_link(dest)
    if replacing:
        if not overwrite:
            return "skipped"
        _refuse_link(dest)
    # Copy next to the destination first; the old skill is only moved aside once the copy is complete.
    tmp = dest.with_name(f".{dest.name}.importing")
    backup = dest.with_name(f".{dest.name}.backup")
    for leftover in (tmp, backup):
        if leftover.exists() and not is_link(leftover):
            shutil.rmtree(leftover, ignore_errors=True)
    try:
        shutil.copytree(src, tmp, symlinks=True, ignore=_ignore_links_and_junk)
        if replacing:
            os.replace(dest, backup)
            try:
                os.replace(tmp, dest)
            except BaseException:
                os.replace(backup, dest)  # restore the previous skill
                raise
            shutil.rmtree(backup, ignore_errors=True)
    except BaseException:
        if tmp.is_dir() and not is_link(tmp):
            shutil.rmtree(tmp, ignore_errors=True)  # no half-copied skill left behind
        raise
    if not replacing:
        os.replace(tmp, dest)
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
