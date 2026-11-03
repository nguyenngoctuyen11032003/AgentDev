"""Validate names and confine generated files to their workspace."""

import os
import re
from collections.abc import Iterator
from pathlib import Path

from agentdev.utils.exceptions import ValidationError


def validate_path_component(name: str, *, field: str = "name") -> str:
    """Accept a single directory name on both POSIX and Windows."""
    if (
        name.strip() in {"", ".", ".."}
        or re.search(r"[/\\:\x00-\x1f\x7f]", name)
    ):
        raise ValidationError(
            f"Invalid {field}: expected a single directory name without path separators, "
            "drive prefixes, or control characters",
            field=field,
        )
    return name


def is_link(path: Path | str) -> bool:
    """Return True for symbolic links *and* Windows directory junctions.

    ``Path.is_symlink()`` is False for NTFS junctions, yet a junction redirects
    a directory exactly like a symlink and can be created without any
    privilege, so every "must not follow links" check has to treat it the same.
    """
    candidate = Path(path)
    return candidate.is_symlink() or candidate.is_junction()


def iter_tree_without_links(root: Path | str) -> Iterator[Path]:
    """Yield every descendant of ``root`` that is not a link, in sorted order.

    Links (symlinks and junctions) are skipped and never descended into, unlike
    ``Path.rglob`` which walks through Windows junctions.
    """
    pending = [Path(root)]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as scanner:
                entries = sorted(scanner, key=lambda entry: entry.name)
        except OSError:
            continue
        subdirs = []
        for entry in entries:
            if entry.is_symlink() or entry.is_junction():
                continue
            path = Path(entry.path)
            yield path
            if entry.is_dir(follow_symlinks=False):
                subdirs.append(path)
        pending.extend(reversed(subdirs))


def resolve_workspace_path(root: Path | str, *parts: str) -> Path:
    """Resolve a child path, rejecting traversal and existing escaping symlinks."""
    for part in parts:
        validate_path_component(part)
    try:
        resolved_root = Path(root).resolve()
        candidate = resolved_root.joinpath(*parts).resolve()
    except (OSError, RuntimeError) as exc:
        raise ValidationError("Unable to resolve workspace path", field="workspace") from exc
    if candidate == resolved_root or not candidate.is_relative_to(resolved_root):
        raise ValidationError("Workspace path escapes its root directory", field="workspace")
    return candidate


def session_directory_name(session_id: str) -> str:
    """Map a raw transport session ID to one distinct directory name."""
    return f"session_{validate_path_component(session_id, field='session_id')}"
