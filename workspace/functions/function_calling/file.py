"""File-related function tools for model-invoked file access."""

import fnmatch
import codecs
import locale
import mimetypes
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import (
    Annotated,
    Any,
    Dict,
    Iterable,
    List,
    Literal,
    Mapping,
    MutableSequence,
    Optional,
    Sequence,
)

from agentdev.entity.messages import MessageBlock, MessageBlockType
from agentdev.utils.attachments import AttachmentStore
from agentdev.utils.function_catalog import ParamMeta


class FileToolContext:
    """Helper to read runtime context injected via `_context` kwarg."""

    def __init__(self, ctx: Dict[str, Any] | None):
        if ctx is None:
            raise ValueError("_context is required for file tools")
        self._ctx = ctx
        self.attachment_store = self._require_store(ctx.get("attachment_store"))
        self.workspace_root = self._require_workspace(ctx.get("python_workspace_root"))
        self.session_root = self._require_session_root(ctx.get("graph_directory"), self.workspace_root)

    @staticmethod
    def _require_store(store: Any) -> AttachmentStore:
        if not isinstance(store, AttachmentStore):
            raise ValueError("attachment_store missing from _context")
        return store

    @staticmethod
    def _require_workspace(root: Any) -> Path:
        if root is None:
            raise ValueError("python_workspace_root missing from _context")
        path = Path(root).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _require_session_root(root: Any, workspace_root: Path) -> Path:
        base = root or workspace_root.parent
        path = Path(base).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return path

    def resolve_under_workspace(self, relative_path: str | Path) -> Path:
        rel = Path(relative_path)
        target = rel.resolve() if rel.is_absolute() else (self.workspace_root / rel).resolve()
        if self.workspace_root not in target.parents and target != self.workspace_root:
            raise ValueError("Path is outside workspace")
        return target

    def resolve_under_session(self, relative_path: str | Path) -> Path:
        raw = Path(relative_path)
        candidates = []
        if raw.is_absolute():
            candidates.append(raw.resolve())
        else:
            candidates.append((self.session_root / raw).resolve())
            candidates.append(raw.resolve())
        for target in candidates:
            if self.session_root in target.parents or target == self.session_root:
                return target
        raise ValueError("Path is outside session directory")

    def to_session_relative(self, absolute_path: str | Path | None) -> Optional[str]:
        if not absolute_path:
            return None
        target = Path(absolute_path).resolve()
        if self.session_root in target.parents or target == self.session_root:
            return target.relative_to(self.session_root).as_posix()
        return str(target)

    def to_workspace_relative(self, absolute_path: str | Path | None) -> Optional[str]:
        if not absolute_path:
            return None
        target = Path(absolute_path).resolve()
        if self.workspace_root in target.parents or target == self.workspace_root:
            rel = target.relative_to(self.workspace_root)
            return rel.as_posix() or "."
        return None


def _check_attachments_not_modified(path: str) -> None:
    if path.startswith("attachments"):
        raise ValueError("Modifications to the attachments directory are not allowed")


# ---------------------------------------------------------------------------
# Token economy: every tool result is re-read by each later model call of the agent's
# loop, so listings stay compact and errors say how to fix the call in one step.
# ---------------------------------------------------------------------------

# Dependency / build / VCS folders: walked only when the agent names them explicitly.
# (Same list as attachment_service.IGNORED_PROJECT_DIRS, which the web upload already filters.)
_SKIP_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", "node_modules", "bower_components", ".venv", "venv",
        "env", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
        "dist", "build", "out", ".next", ".nuxt", ".svelte-kit", ".turbo", ".parcel-cache",
        ".cache", "coverage", ".gradle", ".idea", "target", "Pods", "DerivedData",
    }
)
# Files never worth a text search (and a 200 MB video is slow to decode).
_BINARY_EXTS = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".bmp", ".ico", ".tif", ".tiff", ".psd",
        ".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".mp4", ".mov", ".webm", ".mkv", ".avi",
        ".glb", ".gltf", ".fbx", ".obj", ".blend", ".ktx2", ".hdr", ".exr",
        ".zip", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar", ".tar", ".jar", ".war",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".woff", ".woff2", ".ttf", ".otf", ".eot",
        ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".class", ".pyc", ".wasm",
        ".db", ".sqlite", ".sqlite3", ".lock.bin",
    }
)
_MAX_SEARCH_FILE_BYTES = 2 * 1024 * 1024
# describe_available_files / recursive list_directory: a folder with more direct files than this
# is summarised in one line (count, extensions, size) instead of one line per file.
_COLLAPSE_FILES = 25
_HINT_TOP_LEVEL = 25


def _human_size(size: Optional[int]) -> str:
    if size is None:
        return ""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _walk_workspace(
    root: Path,
    start: Path | None = None,
    *,
    include_hidden: bool = False,
    max_depth: int | None = None,
    skip_dirs: frozenset[str] = _SKIP_DIRS,
) -> Iterable[tuple[Path, int, List[Path], List[Path], List[Path]]]:
    """Breadth-first walk yielding ``(dir, depth, subdirs, files, skipped_dirs)``, sorted by name.

    Hidden entries and dependency/build folders are pruned (reported in ``skipped_dirs``), so an
    opened project with ``node_modules`` does not turn one listing or search into 25,000 files.
    """
    queue: List[tuple[Path, int]] = [(start or root, 0)]
    while queue:
        current, depth = queue.pop(0)
        try:
            children = sorted(current.iterdir(), key=lambda p: p.name.lower())
        except (FileNotFoundError, PermissionError, NotADirectoryError, OSError):
            continue
        subdirs: List[Path] = []
        files: List[Path] = []
        skipped: List[Path] = []
        for child in children:
            if not include_hidden and child.name.startswith("."):
                continue
            try:
                is_dir = child.is_dir()
            except OSError:
                continue
            if is_dir:
                (skipped if child.name in skip_dirs else subdirs).append(child)
            else:
                files.append(child)
        yield current, depth, subdirs, files, skipped
        if max_depth is None or depth + 1 < max_depth:
            queue.extend((sub, depth + 1) for sub in subdirs)


def _file_size(path: Path) -> Optional[int]:
    try:
        return path.stat().st_size
    except OSError:
        return None


def _extension_summary(files: Sequence[Path], top: int = 4) -> str:
    counts: Dict[str, int] = {}
    for item in files:
        ext = item.suffix.lower() or "(no ext)"
        counts[ext] = counts.get(ext, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    parts = [f"{count} {ext}" for ext, count in ranked[:top]]
    if len(ranked) > top:
        parts.append(f"{sum(count for _, count in ranked[top:])} other")
    return ", ".join(parts)


def _top_level_hint(ctx: "FileToolContext") -> str:
    """``top-level entries: a/, b/, c.json`` of the workspace, for not-found errors."""
    try:
        children = sorted(ctx.workspace_root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return ""
    names = [f"{c.name}/" if c.is_dir() else c.name for c in children if not c.name.startswith(".")]
    if not names:
        return "The workspace is empty."
    more = f", ... (+{len(names) - _HINT_TOP_LEVEL})" if len(names) > _HINT_TOP_LEVEL else ""
    return "Top-level entries: " + ", ".join(names[:_HINT_TOP_LEVEL]) + more + "."


def _similar_paths(ctx: "FileToolContext", path: str, *, want_dir: bool, limit: int = 5) -> List[str]:
    """Existing workspace paths whose name matches the missing one (bounded walk, skips dependencies)."""
    import difflib

    wanted = Path(path.replace("\\", "/")).name.lower()
    if not wanted:
        return []
    exact: List[str] = []
    names: Dict[str, List[str]] = {}
    seen = 0
    for current, _depth, subdirs, files, _skipped in _walk_workspace(ctx.workspace_root):
        for item in subdirs if want_dir else files:
            rel = item.relative_to(ctx.workspace_root).as_posix()
            lowered = item.name.lower()
            if lowered == wanted:
                exact.append(rel)
            names.setdefault(lowered, []).append(rel)
        seen += len(subdirs) + len(files)
        if len(exact) >= limit or seen > 20000:
            break
    if exact:
        return exact[:limit]
    close = difflib.get_close_matches(wanted, list(names), n=limit, cutoff=0.75)
    return [rel for name in close for rel in names[name]][:limit]


def _not_found(ctx: "FileToolContext", path: str, *, want_dir: bool) -> FileNotFoundError:
    """A not-found error that tells the model how to fix its next call (no extra listing round)."""
    kind = "Directory" if want_dir else "File"
    parts = [f"{kind} not found: {path}."]
    root_name = ctx.workspace_root.name
    parts.append(
        "Paths are relative to the workspace root ('.')"
        + (f"; do not prefix them with the folder name '{root_name}/'." if root_name else ".")
    )
    similar = _similar_paths(ctx, path, want_dir=want_dir)
    if similar:
        parts.append("Did you mean: " + ", ".join(similar) + "?")
    hint = _top_level_hint(ctx)
    if hint:
        parts.append(hint)
    return FileNotFoundError(" ".join(parts))


def _resolve_existing(ctx: "FileToolContext", path: str) -> tuple[Path, Optional[str]]:
    """Resolve ``path`` under the workspace, repairing the two path mistakes agents make most.

    * ``<root folder name>/src/x.ts`` for a project opened in place (the workspace IS that folder);
    * ``<project id>/src/x.ts`` for an uploaded project that lives under ``projects/<id>/``.

    Only applied when the path as given does not exist and the repaired one does, so a real
    sub-folder that happens to share the name always wins. Returns ``(target, note)``; ``note`` tells
    the model which path was used so its next call is right the first time.
    """
    target = ctx.resolve_under_workspace(path)
    if target.exists():
        return target, None
    normalized = str(path).replace("\\", "/").strip()
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts = [part for part in normalized.split("/") if part]
    if not parts or Path(normalized).is_absolute():
        return target, None
    candidates: List[List[str]] = []
    if parts[0].lower() == ctx.workspace_root.name.lower():
        candidates.append(parts[1:])
    candidates.append(["projects", *parts])
    for candidate in candidates:
        rel = "/".join(candidate) or "."
        try:
            repaired = ctx.resolve_under_workspace(rel)
        except ValueError:
            continue
        if repaired.exists():
            return repaired, f"'{path}' does not exist; used '{rel}' (paths are relative to the workspace root)."
    return target, None


def _resolve_for_write(ctx: "FileToolContext", path: str) -> tuple[Path, Optional[str]]:
    """Like :func:`_resolve_existing` for a file that may not exist yet.

    ``<root folder name>/x`` would otherwise create a stray nested copy of the project folder
    inside the user's project; it is written to ``x`` unless that sub-folder really exists.
    """
    target, note = _resolve_existing(ctx, path)
    if target.exists() or note:
        return target, note
    parts = [part for part in str(path).replace("\\", "/").split("/") if part and part != "."]
    root_name = ctx.workspace_root.name
    if len(parts) > 1 and root_name and parts[0].lower() == root_name.lower():
        if not (ctx.workspace_root / parts[0]).exists():
            rel = "/".join(parts[1:])
            return ctx.resolve_under_workspace(rel), (
                f"Wrote to '{rel}': paths are relative to the workspace root, which is the folder '{root_name}' itself."
            )
    return target, None


def describe_available_files(
    *,
    recursive: bool = True,
    limit: int = 200,
    include_hidden: bool = False,
    # max_depth: int = 5,
    _context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Overview of the workspace files as a compact tree of paths relative to the workspace root.
    Big folders are summarised (file count, extensions); dependency/build folders are skipped.
    """

    ctx = FileToolContext(_context)
    root = ctx.workspace_root
    budget = max(1, limit)
    lines: List[str] = []
    total_files = 0
    truncated = False
    for current, _depth, subdirs, files, skipped in _walk_workspace(
        root, include_hidden=include_hidden, max_depth=None if recursive else 1
    ):
        rel_dir = current.relative_to(root).as_posix()
        prefix = "" if rel_dir == "." else rel_dir + "/"
        total_files += len(files)
        if len(lines) >= budget:
            truncated = True
            continue  # keep counting files for the total
        if prefix:
            size = sum(_file_size(item) or 0 for item in files)
            detail = (f"{len(files)} file" if len(files) == 1 else f"{len(files)} files") + (f", {_human_size(size)}" if files else "")
            if subdirs:
                detail += f", {len(subdirs)} folder" + ("" if len(subdirs) == 1 else "s")
            if len(files) > _COLLAPSE_FILES:
                lines.append(f"{prefix} ({detail}: {_extension_summary(files)}; list it to see the files)")
            else:
                lines.append(f"{prefix} ({detail})")
                lines.extend(f"{prefix}{item.name}  {_human_size(_file_size(item))}" for item in files)
        else:
            lines.extend(f"{item.name}  {_human_size(_file_size(item))}" for item in files)
        lines.extend(f"{prefix}{item.name}/ (skipped: dependency/build folder)" for item in skipped)
    if len(lines) > budget:
        lines = lines[:budget]
        truncated = True
    result: Dict[str, Any] = {
        "root": ".",
        "total_files": total_files,
        "tree": "\n".join(lines),
        "truncated": truncated,
    }
    if truncated:
        result["note"] = "Listing cut at the limit: use list_directory on a sub-folder for the rest."
    return result


def list_directory(
    path: Annotated[str, ParamMeta(description="Directory path relative to the workspace root ('.' = root)")]=".",
    *,
    recursive: Annotated[bool, ParamMeta(description="Traverse subdirectories")] = False,
    max_depth: Annotated[int, ParamMeta(description="Maximum depth when recursive=True")] = 3,
    include_hidden: Annotated[bool, ParamMeta(description="Include entries starting with '.'")] = False,
    limit: Annotated[int, ParamMeta(description="Maximum entries to return")] = 300,
    _context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """List a directory. Entries are paths relative to the workspace root (folders end with '/',
    files show their size), ready to pass to the other file tools."""

    ctx = FileToolContext(_context)
    target, note = _resolve_existing(ctx, path)
    if not target.exists():
        # Agents routinely probe the reserved "attachments" folder. It only exists in
        # sessions with uploads; a folder opened in place has none, so report it empty.
        if path.strip().strip("/\\").lower() == "attachments":
            return {
                "directory": "attachments",
                "entries": [],
                "truncated": False,
                "recursive": recursive,
                "note": "No uploaded attachments in this session.",
            }
        raise _not_found(ctx, path, want_dir=True)
    if not target.is_dir():
        raise NotADirectoryError(
            f"Path is not a directory: {path}. Read it with read_file_segment, or list its folder."
        )

    if limit <= 0:
        raise ValueError("limit must be positive")
    if recursive and max_depth < 1:
        raise ValueError("max_depth must be >= 1 when recursive")

    root = ctx.workspace_root
    base_relative = ctx.to_workspace_relative(target) or "."

    def rel(item: Path) -> str:
        return item.relative_to(root).as_posix()

    entries: List[str] = []
    truncated = False
    for current, depth, subdirs, files, skipped in _walk_workspace(
        root, target, include_hidden=include_hidden, max_depth=max_depth if recursive else 1
    ):
        if len(entries) >= limit:
            truncated = True
            break
        if depth > 0 and len(files) > _COLLAPSE_FILES:
            size = sum(_file_size(item) or 0 for item in files)
            entries.append(
                f"{rel(current)}/* ({len(files)} files, {_human_size(size)}: {_extension_summary(files)};"
                " list this folder to see them)"
            )
        else:
            entries.extend(f"{rel(item)}  {_human_size(_file_size(item))}" for item in files)
        entries.extend(f"{rel(item)}/" for item in subdirs)
        entries.extend(f"{rel(item)}/ (dependency/build folder, not expanded)" for item in skipped)
    truncated = truncated or len(entries) > limit
    result: Dict[str, Any] = {
        "directory": base_relative,
        "entries": entries[:limit],
        "truncated": truncated,
        "recursive": recursive,
    }
    if note:
        result["note"] = note
    return result


def create_folder(
    path: Annotated[str, ParamMeta(description="Workspace-relative folder path")],
    *,
    parents: Annotated[bool, ParamMeta(description="Create missing parent directories")]
    = True,
    exist_ok: Annotated[bool, ParamMeta(description="Do not raise if folder already exists")]
    = True,
    _context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Create a directory tree under the workspace."""

    if not path:
        raise ValueError("path must be provided")
    _check_attachments_not_modified(path)

    ctx = FileToolContext(_context)
    target = ctx.resolve_under_workspace(path)

    if target.exists() and not target.is_dir():
        raise ValueError("Target exists and is not a directory")

    previously_exists = target.exists()
    target.mkdir(parents=parents, exist_ok=exist_ok)

    return {
        "path": ctx.to_workspace_relative(target),
        "absolute_path": str(target),
        "created": not previously_exists,
    }


def delete_path(
    path: Annotated[str, ParamMeta(description="Workspace-relative file or folder path")],
    *,
    recursive: Annotated[
        bool,
        ParamMeta(description="Allow deleting non-empty directories recursively"),
    ] = False,
    missing_ok: Annotated[bool, ParamMeta(description="Suppress error if path is missing")]
    = False,
    _context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Delete a workspace file or directory."""

    if not path:
        raise ValueError("path must be provided")

    _check_attachments_not_modified(path)

    ctx = FileToolContext(_context)
    target = ctx.resolve_under_workspace(path)

    if not target.exists():
        if missing_ok:
            return {
                "path": ctx.to_workspace_relative(target),
                "absolute_path": str(target),
                "deleted": False,
                "reason": "missing",
            }
        raise FileNotFoundError(f"Path not found: {path}")

    if target.is_dir():
        if not recursive:
            raise IsADirectoryError("Set recursive=True to delete directories")
        shutil.rmtree(target)
        deleted_type = "directory"
    else:
        target.unlink()
        deleted_type = "file"

    return {
        "path": ctx.to_workspace_relative(target),
        "absolute_path": str(target),
        "deleted": True,
        "type": deleted_type,
    }


def load_file(
    path_or_id: str,
    *,
    # mime_override: Optional[str] = None,
    _context: Dict[str, Any] | None = None,
) -> List[MessageBlock]:
    """
    Load an attachment by ID or register a workspace file as a new attachment.
    """

    ctx = FileToolContext(_context)

    # First, try existing attachment id
    record = ctx.attachment_store.get(path_or_id)
    if record:
        return [record.as_message_block()]

    # Otherwise treat as workspace path
    target, _note = _resolve_existing(ctx, path_or_id)
    if not target.exists() or not target.is_file():
        raise _not_found(ctx, path_or_id, want_dir=False)

    # mime_type = mime_override or (mimetypes.guess_type(target.name)[0] or "application/octet-stream")
    mime_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
    record = ctx.attachment_store.register_file(
        target,
        kind=MessageBlockType.from_mime_type(mime_type),
        display_name=target.name,
        mime_type=mime_type,
        copy_file=False,
        persist=False,
        deduplicate=True,
        extra={
            "source": "workspace",
            "workspace_path": path_or_id,
            "storage": "reference",
        },
    )
    return [record.as_message_block()]


def save_file(
    path: str,
    content: str,
    *,
    encoding: str = "utf-8",
    mode: Literal["overwrite", "append"] = "overwrite",
    _context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Persist data to a workspace file while optionally registering it as an attachment.

    Args:
        path: Relative path where the file will be written.
        content: Plain-text payload encoded with `encoding`.
        encoding: Text encoding used when `content` is provided.
        mode: Whether to replace the file (`overwrite`) or append to it (`append`).

    Returns:
        A dictionary describing the persisted file, including workspace path, absolute path,
        and byte size.

    Raises:
        ValueError: If arguments are missing/invalid or the path escapes the workspace.
        OSError: If the file cannot be written.
    """

    if mode not in {"overwrite", "append"}:
        raise ValueError("mode must be either 'overwrite' or 'append'")

    ctx = FileToolContext(_context)
    target, note = _resolve_for_write(ctx, path)
    if target.exists() and target.is_dir():
        raise ValueError("Target path points to a directory")
    target.parent.mkdir(parents=True, exist_ok=True)

    data = content.encode(encoding)

    write_mode = "wb" if mode == "overwrite" else "ab"
    try:
        with target.open(write_mode) as handle:
            handle.write(data)
    except OSError as exc:
        raise OSError(f"Failed to write file '{target}': {exc}") from exc

    size = target.stat().st_size if target.exists() else None
    result = {
        "path": ctx.to_workspace_relative(target),
        "absolute_path": str(target),
        "size": size,
    }
    if note:
        result["note"] = note
    return result


def read_text_file_snippet(
    path: str,
    *,
    offset: int = 0,
    limit: int = 4000,
    encoding: str = "utf-8",
    _context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Read a snippet of a workspace text file without loading entire content."""

    ctx = FileToolContext(_context)
    target: Path | None = None
    try:
        candidate, _note = _resolve_existing(ctx, path)
    except ValueError:
        candidate = None

    if candidate and candidate.exists() and candidate.is_file():
        target = candidate

    if target is None:
        target = ctx.resolve_under_session(path)
        if not target.exists() or not target.is_file():
            raise _not_found(ctx, path, want_dir=False)

    data = target.read_text(encoding=encoding, errors="replace")
    snippet = data[offset : offset + limit]
    return {
        "snippet": snippet,
        "truncated": offset + limit < len(data),
        "length": len(data),
        "offset": offset,
    }


def read_file_segment(
    path: Annotated[str, ParamMeta(description="Workspace-relative text file path")],
    *,
    start_line: Annotated[int, ParamMeta(description="1-based line to begin the snippet")]=1,
    line_count: Annotated[int, ParamMeta(description="Number of lines to include starting from start_line")]=40,
    inline_line_numbers: Annotated[
        bool,
        ParamMeta(description="If true, prefix each snippet line with its line number inside the snippet"),
    ] = False,
    encoding: Annotated[str, ParamMeta(description="Explicit encoding or 'auto'")]="auto",
    include_line_offsets: Annotated[
        bool,
        ParamMeta(description="Include 1-based line metadata for the returned snippet"),
    ] = False,
    _context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Read a line range plus metadata from a workspace file."""

    if start_line < 1:
        raise ValueError("start_line must be >= 1")
    if line_count < 1:
        raise ValueError("line_count must be >= 1")

    ctx = FileToolContext(_context)
    try:
        target, note = _resolve_existing(ctx, path)
    except ValueError:
        # An absolute path outside the workspace: the conversation history points at attachments
        # (e.g. a project overview) by their stored path, which lives in the session folder when
        # the project folder is opened in place. Reading them is allowed; writing is not.
        target, note = ctx.resolve_under_session(path), None
    if target.is_dir():
        raise IsADirectoryError(f"Path is a directory, not a file: {path}. List it with list_directory.")
    if not target.is_file():
        raise _not_found(ctx, path, want_dir=False)

    text, used_encoding = _read_text_content(target, encoding)
    newline_style = _detect_newline(text)
    stat = target.stat()

    lines_with_breaks = text.splitlines(keepends=True)
    if not lines_with_breaks:
        lines_with_breaks = [""]
    total_lines = len(lines_with_breaks)
    start_idx = start_line - 1
    if start_idx >= total_lines:
        raise ValueError(f"start_line {start_line} is beyond the end of the file ({total_lines} lines)")

    lines_returned = min(line_count, total_lines - start_idx)
    end_idx = start_idx + lines_returned
    segment_lines = lines_with_breaks[start_idx:end_idx]
    snippet = "".join(segment_lines)
    raw_snippet = snippet

    line_starts: List[int] = [0]
    for line in lines_with_breaks:
        line_starts.append(line_starts[-1] + len(line))
    start_char = line_starts[start_idx]

    # Lean metadata: this dict is re-read by every later model call of the loop. Encoding and
    # newline style only matter to apply_text_edits, which detects and preserves them itself.
    response: Dict[str, Any] = {
        "path": ctx.to_workspace_relative(target),
        "start_line": start_line,
        "end_line": start_line + lines_returned - 1,
        "total_lines": total_lines,
        "truncated": end_idx < total_lines,
        "file_size": stat.st_size,
        "snippet": raw_snippet,
    }
    if note:
        response["note"] = note

    if inline_line_numbers:
        snippet = _render_snippet_with_line_numbers(
            segment_lines,
            start_line,
            newline_style,
            raw_snippet.endswith(("\r\n", "\n", "\r")),
        )
        response["snippet"] = snippet

    if include_line_offsets:
        response.update(_describe_segment_line_offsets(text, start_char, raw_snippet))

    return response


@dataclass(frozen=True)
class TextEdit:
    """Normalized representation of a single line edit."""

    start_line: int
    end_line: int
    replacement_lines: List[str]


def apply_text_edits(
    path: Annotated[str, ParamMeta(description="Workspace-relative file to edit")],
    *,
    start_line: Annotated[int, ParamMeta(description="1-based line where the replacement should begin")],
    end_line: Annotated[
        Optional[int],
        ParamMeta(description="Last line (>= start_line-1) to replace; defaults to start_line"),
    ] = None,
    replacement: Annotated[
        Optional[str],
        ParamMeta(description="Text that should replace the selected line range"),
    ] = "",
    encoding: Annotated[str, ParamMeta(description="Text encoding or 'auto'")]="auto",
    newline: Annotated[
        str,
        ParamMeta(description="Newline style: 'preserve', 'lf', 'crlf', or 'cr'"),
    ]="preserve",
    ensure_trailing_newline: Annotated[
        Optional[bool],
        ParamMeta(description="Force presence/absence of trailing newline; default preserves original"),
    ] = None,
    expected_old: Annotated[
        Optional[str],
        ParamMeta(description="Optional safety check: current text of the selected lines; the edit fails if it differs"),
    ] = None,
    _context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Apply ordered line edits with newline and encoding preservation. Prefer edit_file for content-anchored edits."""

    ctx = FileToolContext(_context)
    target, note = _resolve_existing(ctx, path)
    if not target.is_file():
        raise _not_found(ctx, path, want_dir=False)

    _check_attachments_not_modified(ctx.to_workspace_relative(target) or path)

    normalized = _normalize_edits(_build_single_edit(start_line, end_line, replacement))
    original_text, used_encoding = _read_text_content(target, encoding)
    # "auto" tries utf-8-sig first, which also reads plain UTF-8: write it back as plain UTF-8 unless the file
    # really started with a BOM, or every edit would add one.
    if used_encoding.lower() == "utf-8-sig" and not target.read_bytes().startswith(codecs.BOM_UTF8):
        used_encoding = "utf-8"
    lines, had_trailing_newline = _split_lines(original_text)
    newline_style = _resolve_newline_choice(newline, _detect_newline(original_text))

    if expected_old is not None:
        first = normalized[0]
        current = "\n".join(lines[first.start_line - 1 : max(first.end_line, first.start_line - 1)])
        wanted = expected_old.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
        if current != wanted:
            raise ValueError(
                f"expected_old does not match lines {first.start_line}-{first.end_line}; the file changed or the "
                "line numbers are wrong. Re-read the file (read_file_segment) or use edit_file."
            )
    _apply_edits_in_place(lines, normalized)

    if ensure_trailing_newline is None:
        final_trailing = had_trailing_newline
    else:
        final_trailing = ensure_trailing_newline

    rendered = newline_style.join(lines)
    if final_trailing:
        rendered += newline_style

    target.parent.mkdir(parents=True, exist_ok=True)
    # newline="": the text already carries the file's own line endings; Windows must not translate them again
    # (CRLF became CR CR LF).
    with target.open("w", encoding=used_encoding, newline="") as handle:
        handle.write(rendered)
    stat = target.stat()
    return {
        "path": ctx.to_workspace_relative(target),
        "encoding": used_encoding,
        "newline": newline_style,
        "line_count": len(lines),
        "applied_edits": len(normalized),
        "trailing_newline": final_trailing,
        "file_size": stat.st_size,
        **({"note": note} if note else {}),
    }


# ---------------------------------------------------------------------------
# Content-anchored edits (ADR 0001): exact old_string -> new_string, atomic, EOL/BOM preserving.
# ---------------------------------------------------------------------------


def _edit_tools_enabled() -> bool:
    return os.environ.get("AGENTDEV_EDIT_TOOLS", "1").strip().lower() not in {"0", "false", "off", "no"}


def _unix_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _load_for_edit(ctx: "FileToolContext", path: str) -> tuple[Path, str, bool, str, Optional[str]]:
    """Return (target, text, has_bom, newline, note) of a UTF-8 workspace file."""

    if not _edit_tools_enabled():
        raise ValueError("edit_file/multi_edit are disabled (AGENTDEV_EDIT_TOOLS=0); use apply_text_edits")
    target, note = _resolve_existing(ctx, path)
    if not target.is_file():
        raise _not_found(ctx, path, want_dir=False)
    _check_attachments_not_modified(ctx.to_workspace_relative(target) or path)
    raw = target.read_bytes()
    has_bom = raw.startswith(codecs.BOM_UTF8)
    try:
        text = raw[len(codecs.BOM_UTF8):].decode("utf-8") if has_bom else raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"'{path}' is not valid UTF-8; edit_file supports UTF-8 only. Use apply_text_edits with an encoding."
        ) from exc
    newline = "\r\n" if "\r\n" in text else ("\r" if "\r" in text and "\n" not in text else "\n")
    return target, text, has_bom, newline, note


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _replace_once_or_all(
    text: str, old: Any, new: Any, replace_all: bool, newline: str, label: str
) -> tuple[str, int]:
    if not isinstance(old, str) or not isinstance(new, str):
        raise ValueError(f"{label}old_string and new_string must be strings")
    if old == "":
        raise ValueError(f"{label}old_string must not be empty")
    old = _unix_newlines(old)
    new = _unix_newlines(new)
    if old == new:
        raise ValueError(f"{label}old_string and new_string are identical; nothing to change")
    if newline != "\n":
        old = old.replace("\n", newline)
        new = new.replace("\n", newline)
    count = text.count(old)
    if count == 0:
        first = next((ln.strip() for ln in old.splitlines() if ln.strip()), "")
        hint = ""
        if first and first in text:
            hint = (
                f" The first line was found at line {_line_of(text, text.index(first))}; "
                "re-read it and copy the text exactly (whitespace matters)."
            )
        raise ValueError(f"{label}old_string not found in the file.{hint}")
    if count > 1 and not replace_all:
        lines: List[str] = []
        start = 0
        while len(lines) < 5:
            idx = text.find(old, start)
            if idx < 0:
                break
            lines.append(str(_line_of(text, idx)))
            start = idx + len(old)
        more = "..." if count > len(lines) else ""
        raise ValueError(
            f"{label}old_string matches {count} times (lines {', '.join(lines)}{more}); "
            "add surrounding context to make it unique or set replace_all=true."
        )
    return text.replace(old, new), count


def _atomic_write_text(target: Path, text: str, has_bom: bool) -> int:
    import tempfile

    data = text.encode("utf-8")
    if has_bom:
        data = codecs.BOM_UTF8 + data
    fd, tmp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        try:
            shutil.copymode(target, tmp_name)
        except OSError:
            pass
        os.replace(tmp_name, target)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return len(data)


def edit_file(
    path: Annotated[str, ParamMeta(description="Workspace-relative file to edit")],
    old_string: Annotated[str, ParamMeta(description="Exact text to replace; must be unique unless replace_all")],
    new_string: Annotated[str, ParamMeta(description="Replacement text")],
    replace_all: Annotated[bool, ParamMeta(description="Replace every occurrence instead of requiring a unique one")] = False,
    _context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Replace exact text in a UTF-8 file (unique match unless replace_all). Keeps CRLF/LF and BOM; atomic."""

    ctx = FileToolContext(_context)
    target, text, has_bom, newline, note = _load_for_edit(ctx, path)
    updated, count = _replace_once_or_all(text, old_string, new_string, replace_all, newline, "")
    size = _atomic_write_text(target, updated, has_bom)
    return {
        "path": ctx.to_workspace_relative(target),
        "replacements": count,
        "newline": newline,
        "file_size": size,
        **({"note": note} if note else {}),
    }


def multi_edit(
    path: Annotated[str, ParamMeta(description="Workspace-relative file to edit")],
    edits: Annotated[
        List[Dict[str, Any]],
        ParamMeta(description="Ordered list of {old_string, new_string, replace_all?}; all apply or none do"),
    ],
    _context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Apply several edit_file style edits to one file in order; if any fails nothing is written."""

    if not edits or not isinstance(edits, (list, tuple)):
        raise ValueError("edits must be a non-empty list of {old_string, new_string, replace_all?}")
    ctx = FileToolContext(_context)
    target, text, has_bom, newline, note = _load_for_edit(ctx, path)
    total = 0
    for index, item in enumerate(edits, start=1):
        label = f"edit {index}: "
        if not isinstance(item, Mapping):
            raise ValueError(f"{label}must be an object with old_string and new_string")
        text, count = _replace_once_or_all(
            text,
            item.get("old_string"),
            item.get("new_string"),
            bool(item.get("replace_all", False)),
            newline,
            label,
        )
        total += count
    size = _atomic_write_text(target, text, has_bom)
    return {
        "path": ctx.to_workspace_relative(target),
        "applied_edits": len(edits),
        "replacements": total,
        "newline": newline,
        "file_size": size,
        **({"note": note} if note else {}),
    }


def rename_path(
    src: Annotated[str, ParamMeta(description="Existing workspace-relative path")],
    dst: Annotated[str, ParamMeta(description="New workspace-relative path")],
    *,
    overwrite: Annotated[
        bool,
        ParamMeta(description="Allow replacing an existing destination"),
    ] = False,
    _context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Rename files or directories inside the workspace."""

    ctx = FileToolContext(_context)
    source = ctx.resolve_under_workspace(src)
    destination = ctx.resolve_under_workspace(dst)
    _check_attachments_not_modified(src)
    _check_attachments_not_modified(dst)

    if not source.exists():
        raise FileNotFoundError(f"Source does not exist: {src}")
    if source == destination:
        return {
            "path": ctx.to_workspace_relative(destination),
            "operation": "rename",
            "skipped": True,
        }

    _clear_destination(destination, overwrite)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.rename(destination)
    return {
        "path": ctx.to_workspace_relative(destination),
        "previous_path": ctx.to_workspace_relative(source),
        "operation": "rename",
    }


def copy_path(
    src: Annotated[str, ParamMeta(description="Source workspace-relative path")],
    dst: Annotated[str, ParamMeta(description="Destination workspace-relative path")],
    *,
    overwrite: Annotated[
        bool,
        ParamMeta(description="Allow replacing destination if it exists"),
    ] = False,
    _context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Copy a file tree within the workspace."""

    ctx = FileToolContext(_context)
    source = ctx.resolve_under_workspace(src)
    destination = ctx.resolve_under_workspace(dst)
    _check_attachments_not_modified(dst)

    if not source.exists():
        raise FileNotFoundError(f"Source does not exist: {src}")
    if destination.exists():
        if not overwrite:
            raise FileExistsError(f"Destination already exists: {dst}")
        _clear_destination(destination, overwrite=True)

    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)
    return {
        "path": ctx.to_workspace_relative(destination),
        "source": ctx.to_workspace_relative(source),
        "operation": "copy",
    }


def move_path(
    src: Annotated[str, ParamMeta(description="Source workspace-relative path")],
    dst: Annotated[str, ParamMeta(description="Destination workspace-relative path")],
    *,
    overwrite: Annotated[
        bool,
        ParamMeta(description="Allow replacing destination path"),
    ] = False,
    _context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Move files or directories, mirroring `mv` semantics across platforms."""

    ctx = FileToolContext(_context)
    source = ctx.resolve_under_workspace(src)
    destination = ctx.resolve_under_workspace(dst)
    _check_attachments_not_modified(src)
    _check_attachments_not_modified(dst)

    if not source.exists():
        raise FileNotFoundError(f"Source does not exist: {src}")
    if source == destination:
        return {
            "path": ctx.to_workspace_relative(destination),
            "operation": "move",
            "skipped": True,
        }
    _clear_destination(destination, overwrite)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(source, destination)
    return {
        "path": ctx.to_workspace_relative(destination),
        "source": ctx.to_workspace_relative(source),
        "operation": "move",
    }


def search_in_files(
    pattern: Annotated[str, ParamMeta(description="Plain text or regex pattern")],
    *,
    globs: Annotated[
        Optional[Sequence[str]],
        ParamMeta(description="Globs relative to the workspace root, e.g. ['src/**/*.ts', '*.md']"),
    ] = None,
    exclude_globs: Annotated[
        Optional[Sequence[str]],
        ParamMeta(description="Glob patterns to exclude"),
    ] = None,
    use_regex: Annotated[bool, ParamMeta(description="Treat pattern as regex")]=True,
    case_sensitive: Annotated[bool, ParamMeta(description="Match case when True")]=False,
    max_results: Annotated[int, ParamMeta(description="Stop after this many matches")]=200,
    before_context: Annotated[int, ParamMeta(description="Lines to include before match")]=2,
    after_context: Annotated[int, ParamMeta(description="Lines to include after match")]=2,
    include_hidden: Annotated[bool, ParamMeta(description="Search hidden files/folders")]=False,
    _context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Search text files of the workspace (dependency/build folders and binaries skipped)."""

    if max_results <= 0:
        raise ValueError("max_results must be positive")

    ctx = FileToolContext(_context)
    include_patterns = _normalize_globs(globs) or ["**/*"]
    exclude_patterns = _normalize_globs(exclude_globs)

    matches: List[Dict[str, Any]] = []
    searched_files = 0
    compiled_regex: Optional[re.Pattern[str]] = None
    literal = pattern if case_sensitive else pattern.lower()
    if use_regex:
        flags = re.MULTILINE
        if not case_sensitive:
            flags |= re.IGNORECASE
        compiled_regex = re.compile(pattern, flags)

    skipped: Dict[str, int] = {}
    searched_files = 0
    rg_hits = _rg_candidate_files(
        ctx.workspace_root, pattern, use_regex, case_sensitive, include_patterns, exclude_patterns, include_hidden
    )
    engine = "python"
    rg_searched: Optional[int] = None
    if rg_hits is not None:
        engine = "ripgrep"
        candidates: Iterable[Path] = rg_hits[0]
        rg_searched = rg_hits[1]
    else:
        candidates = _iter_candidate_files(
            ctx.workspace_root, include_patterns, exclude_patterns, include_hidden, skipped
        )
    for candidate in candidates:
        searched_files += 1
        try:
            lines = _read_file_lines_for_search(candidate)
        except OSError:
            continue
        if not lines:
            continue
        for match in _iter_line_matches(
            lines,
            compiled_regex,
            literal,
            pattern,
            case_sensitive,
            use_regex,
        ):
            before = _slice_context(lines, match["line_number"], before_context, before=True)
            after = _slice_context(lines, match["line_number"], after_context, before=False)
            matches.append(
                {
                    "file": ctx.to_workspace_relative(candidate),
                    "line": match["line_number"],
                    "column": match["column"],
                    "line_text": _clip_line(match["line_text"]),
                    "before": [_clip_line(line) for line in before],
                    "after": [_clip_line(line) for line in after],
                }
            )
            if len(matches) >= max_results:
                return _search_result(matches, True, rg_searched or searched_files, skipped, engine)

    return _search_result(matches, False, rg_searched or searched_files, skipped, engine)


def _rg_enabled() -> bool:
    return os.environ.get("AGENTDEV_SEARCH_RG", "1").strip().lower() not in {"0", "false", "off", "no"}


def _rg_candidate_files(
    root: Path,
    pattern: str,
    use_regex: bool,
    case_sensitive: bool,
    include_patterns: Sequence[str],
    exclude_patterns: Sequence[str],
    include_hidden: bool,
) -> Optional[tuple[List[Path], Optional[int]]]:
    """(files, files_searched) of files that contain a hit, found by ripgrep (honours .gitignore, no size cap).

    The caller still extracts the matches with the Python line matcher so the result format and limits are
    identical on both paths. Returns None (use the Python walker) when rg is missing, disabled or fails.
    """

    if not pattern or not _rg_enabled():
        return None
    rg = shutil.which("rg")
    if not rg:
        return None
    named = {part for pat in include_patterns for part in _clean_glob(pat).split("/")}
    skip_dirs = frozenset(name for name in _SKIP_DIRS if name not in named)
    cmd = [rg, "--files-with-matches", "--null", "--stats", "--no-messages", "--no-require-git", "--color", "never"]
    if include_hidden:
        cmd.append("--hidden")
    if not case_sensitive:
        cmd.append("--ignore-case")
    else:
        cmd.append("--case-sensitive")
    if not use_regex:
        cmd.append("--fixed-strings")
    for name in sorted(skip_dirs):
        cmd += ["--glob", f"!{name}/"]
    cmd += ["-e", pattern, "--", "."]
    try:
        proc = subprocess.run(
            cmd, cwd=str(root), capture_output=True, timeout=60, stdin=subprocess.DEVNULL, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode not in (0, 1):
        return None
    compiled = [_compile_glob(pat) for pat in include_patterns]
    found: List[Path] = []
    out = proc.stdout
    cut = out.rfind(b"\x00")
    stats = out[cut + 1 :].decode("utf-8", errors="replace")
    searched_match = re.search(r"(\d+) files searched", stats)
    searched = int(searched_match.group(1)) if searched_match else None
    names = out[:cut].split(b"\x00") if cut >= 0 else []
    for raw in names:
        if not raw:
            continue
        rel = raw.decode("utf-8", errors="replace").replace("\\", "/")
        while rel.startswith("./"):
            rel = rel[2:]
        parts = rel.split("/")
        if any(part in skip_dirs for part in parts[:-1]):
            continue
        if not any(regex.match(rel) for regex in compiled) or _is_excluded(rel, exclude_patterns):
            continue
        path = root / rel
        if path.suffix.lower() in _BINARY_EXTS or not path.is_file():
            continue
        found.append(path)
    found.sort(key=lambda item: item.relative_to(root).as_posix())
    return found, searched


# A match in minified code would otherwise send a whole 500 KB line to the model.
_MAX_MATCH_LINE_CHARS = 300


def _clip_line(line: str) -> str:
    if len(line) <= _MAX_MATCH_LINE_CHARS:
        return line
    return line[:_MAX_MATCH_LINE_CHARS] + f"... [+{len(line) - _MAX_MATCH_LINE_CHARS} chars]"


def _search_result(
    matches: List[Dict[str, Any]], limited: bool, searched_files: int, skipped: Dict[str, int], engine: str = "python"
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "matches": matches,
        "limited": limited,
        "engine": engine,
        "searched_files": searched_files,
    }
    if skipped.get("binary_or_large"):
        result["skipped_binary_or_large_files"] = skipped["binary_or_large"]
    if not matches and searched_files == 0:
        result["note"] = (
            "No file matched the globs. Globs are relative to the workspace root; '*.ts' matches at any depth, "
            "'src/**/*.ts' only under src/. Dependency/build folders are searched only when a glob names them."
        )
    return result


def _read_text_content(path: Path, encoding: str) -> tuple[str, str]:
    if encoding != "auto":
        return path.read_text(encoding=encoding), encoding

    raw = path.read_bytes()
    for candidate in _candidate_encodings():
        try:
            return raw.decode(candidate), candidate
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8"


def _candidate_encodings() -> List[str]:
    preferred = locale.getpreferredencoding(False) or ""
    ordered = [
        "utf-8-sig",
        "utf-8",
        preferred,
        "utf-16",
        "utf-16-le",
        "utf-16-be",
        "latin-1",
    ]
    seen: set[str] = set()
    result: List[str] = []
    for item in ordered:
        normalized = (item or "").lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(item)
    return result


_LINE_BREAK_RE = re.compile(r"\r\n|\r|\n")


def _detect_newline(text: str) -> str:
    if "\r\n" in text:
        return "\r\n"
    if "\r" in text and "\n" not in text:
        return "\r"
    return "\n"


def _split_lines(text: str) -> tuple[List[str], bool]:
    if not text:
        return [], False
    has_trailing = text.endswith(("\r\n", "\n", "\r"))
    return text.splitlines(), has_trailing


def _describe_segment_line_offsets(full_text: str, start_index: int, snippet: str) -> Dict[str, Any]:
    """Return 1-based line metadata (columns are 0-based) for a snippet extracted from full_text."""

    before_segment = full_text[:start_index]
    start_line = 1
    last_break_end = 0
    for match in _LINE_BREAK_RE.finditer(before_segment):
        start_line += 1
        last_break_end = match.end()
    start_column = start_index - last_break_end

    line_offsets: List[Dict[str, int]] = [
        {"line": start_line, "offset": 0, "column": start_column},
    ]
    line_number = start_line
    last_break_inside = 0
    for match in _LINE_BREAK_RE.finditer(snippet):
        last_break_inside = match.end()
        line_number += 1
        line_offsets.append({"line": line_number, "offset": match.end(), "column": 0})

    if snippet:
        if last_break_inside:
            end_column = len(snippet) - last_break_inside
        else:
            end_column = start_column + len(snippet)
    else:
        end_column = start_column

    return {
        "start_line": start_line,
        "start_column": start_column,
        "end_line": line_number,
        "end_column": end_column,
        "line_offsets": line_offsets,
    }


def _render_snippet_with_line_numbers(
    lines: Sequence[str],
    start_line: int,
    newline_style: str,
    preserve_trailing_newline: bool,
) -> str:
    numbered: List[str] = []
    for idx, line in enumerate(lines):
        body = line.rstrip("\r\n")
        numbered.append(f"{start_line + idx}:{body}")
    rendered = newline_style.join(numbered)
    if preserve_trailing_newline and numbered:
        rendered += newline_style
    return rendered


def _normalize_edits(edits: Sequence[Mapping[str, Any]]) -> List[TextEdit]:
    if not edits:
        raise ValueError("at least one edit instruction is required")
    normalized: List[TextEdit] = []
    for item in edits:
        if not isinstance(item, Mapping):
            raise ValueError("each edit entry must be a mapping object")
        try:
            start_line = int(item["start_line"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("start_line is required for each edit") from exc
        end_line_raw = item.get("end_line", start_line)
        try:
            end_line = int(end_line_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("end_line must be an integer") from exc
        if start_line < 1:
            raise ValueError("start_line must be >= 1")
        if end_line < start_line - 1:
            raise ValueError("end_line must be >= start_line - 1")
        replacement = item.get("replacement", "")
        if not isinstance(replacement, str):
            raise ValueError("replacement must be a string")
        normalized.append(
            TextEdit(
                start_line=start_line,
                end_line=end_line,
                replacement_lines=replacement.splitlines(),
            )
        )

    normalized.sort(key=lambda edit: (edit.start_line, edit.end_line))
    _validate_edit_ranges(normalized)
    return normalized


def _build_single_edit(
    start_line: int,
    end_line: Optional[int],
    replacement: Optional[str],
) -> List[Mapping[str, Any]]:
    effective_end = end_line if end_line is not None else start_line
    payload = {
        "start_line": start_line,
        "end_line": effective_end,
        "replacement": replacement if replacement is not None else "",
    }
    return [payload]


def _validate_edit_ranges(edits: Sequence[TextEdit]) -> None:
    previous_range_end = 0
    for edit in edits:
        effective_end = max(edit.end_line, edit.start_line - 1)
        if edit.start_line <= previous_range_end and previous_range_end > 0:
            raise ValueError("edit ranges overlap; merge them before calling apply_text_edits")
        previous_range_end = max(previous_range_end, effective_end)


def _apply_edits_in_place(lines: MutableSequence[str], edits: Sequence[TextEdit]) -> None:
    for edit in reversed(edits):
        current_line_count = len(lines)
        if edit.start_line > current_line_count + 1:
            raise ValueError("start_line is beyond the end of the file")
        start_idx = min(edit.start_line - 1, current_line_count)
        if start_idx > current_line_count:
            raise ValueError("start_line is beyond the end of the file")
        removal_count = max(edit.end_line - edit.start_line + 1, 0)
        if removal_count > 0 and edit.start_line <= current_line_count and edit.end_line > current_line_count:
            raise ValueError(
                f"end_line {edit.end_line} is beyond the end of the file ({current_line_count} lines); "
                "nothing was written. Re-read the file for the real line numbers."
            )
        if removal_count > 0:
            end_line = min(edit.end_line, len(lines))
            removal_count = max(end_line - edit.start_line + 1, 0)
        end_idx = start_idx + removal_count
        lines[start_idx:end_idx] = edit.replacement_lines


def _resolve_newline_choice(preference: str, detected: str) -> str:
    normalized = (preference or "").lower()
    if normalized == "lf":
        return "\n"
    if normalized == "crlf":
        return "\r\n"
    if normalized == "cr":
        return "\r"
    return detected or os.linesep


def _clear_destination(destination: Path, overwrite: bool) -> None:
    if not destination.exists():
        return
    if not overwrite:
        raise FileExistsError(f"Destination already exists: {destination}")
    if destination.is_dir():
        shutil.rmtree(destination)
    else:
        destination.unlink()


def _normalize_globs(patterns: Optional[Sequence[str]]) -> List[str]:
    if not patterns:
        return []
    if isinstance(patterns, str):  # a single glob passed as a string, not a list of characters
        patterns = [patterns]
    normalized: List[str] = []
    for raw in patterns:
        if not raw:
            continue
        normalized.append(str(raw))
    return normalized


def _translate_glob(fragment: str) -> str:
    out: List[str] = []
    i = 0
    while i < len(fragment):
        if fragment.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
            continue
        if fragment.startswith("**", i):
            out.append(".*")
            i += 2
            continue
        char = fragment[i]
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            end = fragment.find("]", i + 1)
            if end == -1:
                out.append(re.escape(char))
            else:
                body = fragment[i + 1 : end]
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append(f"[{body}]")
                i = end
        elif char == "{":
            end = fragment.find("}", i + 1)
            if end == -1:
                out.append(re.escape(char))
            else:
                options = fragment[i + 1 : end].split(",")
                out.append("(?:" + "|".join(_translate_glob(option) for option in options) + ")")
                i = end
        else:
            out.append(re.escape(char))
        i += 1
    return "".join(out)


def _clean_glob(pattern: str) -> str:
    text = pattern.replace("\\", "/").strip()
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def _compile_glob(pattern: str) -> re.Pattern[str]:
    """Glob over workspace-relative POSIX paths: ``**`` spans folders, ``{a,b}`` alternates, and a
    pattern without ``/`` (``*.tsx``) matches the file name at any depth, as in ripgrep/gitignore."""
    text = _clean_glob(pattern)
    if "/" not in text:
        text = "**/" + text
    flags = re.IGNORECASE if os.name == "nt" else 0
    return re.compile("^" + _translate_glob(text) + "$", flags)


def _glob_base(pattern: str) -> str:
    """Literal leading folders of a glob (``src/app`` for ``src/app/**/*.tsx``): where its walk can start."""
    parts = _clean_glob(pattern).split("/")
    literal: List[str] = []
    for part in parts[:-1]:
        if any(ch in part for ch in "*?[{"):
            break
        literal.append(part)
    return "/".join(literal)


def _looks_binary(path: Path) -> bool:
    if path.suffix.lower() in _BINARY_EXTS:
        return True
    try:
        with path.open("rb") as handle:
            head = handle.read(4096)
    except OSError:
        return True
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):  # UTF-16 text has NUL bytes but is text
        return False
    return b"\0" in head


def _iter_candidate_files(
    root: Path,
    include_patterns: Sequence[str],
    exclude_patterns: Sequence[str],
    include_hidden: bool,
    skipped: Optional[Dict[str, int]] = None,
) -> Iterable[Path]:
    """Text files matching the globs. Dependency/build folders are pruned unless a glob names them,
    and binary or very large files are skipped (counted in ``skipped``)."""
    compiled = [_compile_glob(pattern) for pattern in include_patterns]
    named = {part for pattern in include_patterns for part in _clean_glob(pattern).split("/")}
    skip_dirs = frozenset(name for name in _SKIP_DIRS if name not in named)
    bases = sorted({_glob_base(pattern) for pattern in include_patterns})
    starts: List[Path] = []
    if "" in bases:
        starts = [root]
    else:
        for base in bases:
            candidate = (root / base).resolve()
            if not candidate.is_dir() or not (root in candidate.parents or candidate == root):
                continue
            if any(parent in starts for parent in candidate.parents):
                continue
            starts.append(candidate)
    yielded: set[str] = set()
    for start in starts:
        for _current, _depth, _subdirs, files, _skipped_dirs in _walk_workspace(
            root, start, include_hidden=include_hidden, skip_dirs=skip_dirs
        ):
            for candidate in files:
                rel_key = candidate.relative_to(root).as_posix()
                if rel_key in yielded or not any(regex.match(rel_key) for regex in compiled):
                    continue
                if _is_excluded(rel_key, exclude_patterns):
                    continue
                yielded.add(rel_key)
                size = _file_size(candidate)
                if size is None or size > _MAX_SEARCH_FILE_BYTES or _looks_binary(candidate):
                    if skipped is not None:
                        skipped["binary_or_large"] = skipped.get("binary_or_large", 0) + 1
                    continue
                yield candidate


def _path_is_hidden(path: Path) -> bool:
    return any(part.startswith(".") for part in path.parts)


def _is_excluded(relative_posix: str, exclude_patterns: Sequence[str]) -> bool:
    for pattern in exclude_patterns:
        if fnmatch.fnmatch(relative_posix, pattern):
            return True
    return False


def _read_file_lines_for_search(path: Path) -> List[str]:
    raw, _ = _read_text_content(path, encoding="auto")
    return raw.splitlines()


def _iter_line_matches(
    lines: Sequence[str],
    compiled_regex: Optional[re.Pattern[str]],
    literal_lower: str,
    original_pattern: str,
    case_sensitive: bool,
    use_regex: bool,
) -> Iterable[Dict[str, Any]]:
    for idx, raw_line in enumerate(lines):
        line_number = idx + 1
        line_text = raw_line
        if use_regex and compiled_regex is not None:
            for match in compiled_regex.finditer(line_text):
                yield {
                    "line_number": line_number,
                    "column": match.start() + 1,
                    "line_text": line_text,
                }
        else:
            if not original_pattern:
                continue
            haystack = line_text if case_sensitive else line_text.lower()
            needle = original_pattern if case_sensitive else literal_lower
            start = haystack.find(needle)
            while start != -1:
                yield {
                    "line_number": line_number,
                    "column": start + 1,
                    "line_text": line_text,
                }
                start = haystack.find(needle, start + max(len(needle), 1))


def _slice_context(
    lines: Sequence[str],
    center_line: int,
    span: int,
    *,
    before: bool,
) -> List[str]:
    if span <= 0:
        return []
    if before:
        start_line = max(center_line - span, 1)
        end_line = center_line - 1
    else:
        start_line = center_line + 1
        end_line = min(center_line + span, len(lines))
    if end_line < start_line:
        return []
    start_idx = start_line - 1
    end_idx = end_line
    return list(lines[start_idx:end_idx])
