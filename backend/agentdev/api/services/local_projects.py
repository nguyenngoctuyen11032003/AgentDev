"""Browse folders on this machine and collect a project from one, server side.

The backend runs on the user's own machine, so a project folder can be read straight
from disk instead of through the browser's folder picker (whose permission prompt
cannot be styled). Listing only returns folder names; files are read when a project
is imported. The filters mirror ``frontend/src/utils/projectFiles.js``: dependency /
build / VCS folders plus whatever the project's own ``.gitignore`` files exclude.
"""

from __future__ import annotations

import os
import re
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

from agentdev.utils.exceptions import ValidationError
from agentdev.utils.workspace_paths import is_link

_MAX_LISTED_FOLDERS = 2000
_GITIGNORE = ".gitignore"


# ---------------------------------------------------------------- .gitignore
# Same subset of the syntax as the frontend: comments, `!` negation, trailing `/`
# (folders only), leading or inner `/` (anchored), `*`, `?`, `**` and `[...]`.
# The last matching rule wins, like git.


@dataclass(frozen=True)
class _Rule:
    regex: re.Pattern
    negate: bool
    dir_only: bool


def _glob_to_regex(glob: str) -> str:
    out = []
    i = 0
    while i < len(glob):
        char = glob[i]
        if char == "*":
            if glob[i + 1 : i + 2] == "*":
                if glob[i + 2 : i + 3] == "/":
                    out.append("(?:.*/)?")
                    i += 2
                else:
                    out.append(".*")
                    i += 1
            else:
                out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            end = glob.find("]", i + 1)
            if end == -1:
                out.append(r"\[")
            else:
                body = glob[i + 1 : end]
                body = "^" + body[1:] if body.startswith("!") else body
                out.append("[" + body.replace("\\", "\\\\") + "]")
                i = end
        elif char == "\\" and i + 1 < len(glob):
            out.append(re.escape(glob[i + 1]))
            i += 1
        else:
            out.append(re.escape(char))
        i += 1
    return "".join(out)


def parse_gitignore(text: str, base: str = "") -> List[_Rule]:
    """Parse one .gitignore; ``base`` is its folder relative to the project root."""
    rules: List[_Rule] = []
    for raw in (text or "").splitlines():
        line = re.sub(r"(?<!\\)\s+$", "", raw)
        if not line or line.startswith("#"):
            continue
        negate = line.startswith("!")
        if negate:
            line = line[1:]
        dir_only = line.endswith("/")
        line = line.rstrip("/")
        anchored = "/" in line
        line = line.lstrip("/")
        if not line:
            continue
        prefix = re.escape(base) + "/" if base else ""
        try:
            regex = re.compile(f"^{prefix}{'' if anchored else '(?:.*/)?'}{_glob_to_regex(line)}$")
        except re.error:
            continue  # a pattern git would also not match anything with
        rules.append(_Rule(regex, negate, dir_only))
    return rules


def is_git_ignored(rules: List[_Rule], path: str, is_dir: bool) -> bool:
    ignored = False
    for rule in rules:
        if rule.dir_only and not is_dir:
            continue
        if rule.regex.match(path):
            ignored = not rule.negate
    return ignored


def opened_project_folder(session) -> Optional[Path]:
    """The folder a session opened in place (agents work in it directly), if any."""
    for project in getattr(session, "projects", None) or []:
        local_path = project.get("local_path") if isinstance(project, dict) else None
        if local_path:
            return Path(local_path)
    return None


# ---------------------------------------------------------------- browsing


def _resolve_folder(raw: str) -> Path:
    text = (raw or "").strip()
    if not text:
        raise ValidationError("Folder path is required", field="path")
    path = Path(os.path.expanduser(text))
    if not path.is_absolute():
        raise ValidationError("Folder path must be absolute", field="path")
    try:
        path = path.resolve()
    except OSError as exc:
        raise ValidationError(f"Folder not found: {text}", field="path") from exc
    if not path.is_dir():
        raise ValidationError(f"Folder not found: {text}", field="path")
    return path


def list_locations() -> List[Dict[str, str]]:
    """Starting points for the picker: home folders, then drives (Windows) or ``/``."""
    home = Path.home()
    locations = [{"kind": "home", "name": home.name or str(home), "path": str(home)}]
    for kind, name in (("desktop", "Desktop"), ("documents", "Documents"), ("downloads", "Downloads")):
        candidate = home / name
        if candidate.is_dir():
            locations.append({"kind": kind, "name": name, "path": str(candidate)})
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.isdir(drive):
                locations.append({"kind": "drive", "name": f"{letter}:", "path": drive})
    else:
        locations.append({"kind": "drive", "name": "/", "path": "/"})
    return locations


def list_folders(raw_path: str) -> Dict[str, object]:
    """Sub-folders of one folder (names only, never file contents)."""
    path = _resolve_folder(raw_path)
    folders: List[Dict[str, str]] = []
    truncated = False
    try:
        with os.scandir(path) as entries:
            for entry in entries:
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                if len(folders) >= _MAX_LISTED_FOLDERS:
                    truncated = True
                    break
                folders.append({"name": entry.name, "path": entry.path})
    except PermissionError as exc:
        raise ValidationError(f"No permission to open {path}", field="path") from exc
    except OSError as exc:
        raise ValidationError(f"Cannot open {path}", field="path") from exc
    # Visible folders first, then hidden ones, each alphabetically
    folders.sort(key=lambda item: (item["name"].startswith("."), item["name"].lower()))
    parent = path.parent if path.parent != path else None
    return {
        "path": str(path),
        "name": path.name or str(path),
        "parent": str(parent) if parent else None,
        "folders": folders,
        "truncated": truncated,
    }


# ---------------------------------------------------------------- collection


@dataclass
class ScanResult:
    root: Path
    files: List[Tuple[Path, str]] = field(default_factory=list)  # (absolute, relative posix)
    skipped: int = 0  # dependency / build / VCS folders and OS junk
    gitignored: int = 0
    unreadable: List[str] = field(default_factory=list)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def scan_project(
    raw_path: str,
    *,
    ignored_dirs: frozenset,
    ignored_files: frozenset,
    max_files: Optional[int] = None,
) -> ScanResult:
    """Walk a project folder, skipping ignored folders without even listing them."""
    root = _resolve_folder(raw_path)
    result = ScanResult(root=root)

    def walk(folder: Path, prefix: str, parent_rules: List[_Rule]) -> Iterator[None]:
        try:
            with os.scandir(folder) as it:
                entries = sorted(it, key=lambda e: e.name)
        except OSError:
            if not prefix:
                raise ValidationError(f"Cannot open {folder}", field="path")
            result.unreadable.append(f"{prefix}/")
            return
        rules = parent_rules
        if any(e.name == _GITIGNORE for e in entries):
            rules = [*parent_rules, *parse_gitignore(_read_text(folder / _GITIGNORE), prefix)]
        for entry in entries:
            rel = f"{prefix}/{entry.name}" if prefix else entry.name
            try:
                if is_link(entry):
                    result.skipped += 1
                    continue
                is_dir = entry.is_dir()
            except OSError:
                result.unreadable.append(rel)
                continue
            if is_dir:
                if entry.name in ignored_dirs:
                    result.skipped += 1
                elif is_git_ignored(rules, rel, True):
                    result.gitignored += 1
                else:
                    yield from walk(Path(entry.path), rel, rules)
            elif entry.name in ignored_files:
                result.skipped += 1
            elif is_git_ignored(rules, rel, False):
                result.gitignored += 1
            else:
                result.files.append((Path(entry.path), rel))
                if max_files is not None and len(result.files) > max_files:
                    raise ValidationError(
                        f"Project exceeds the limit of {max_files} files", field="path"
                    )
                yield

    for _ in walk(root, "", []):
        pass
    return result


# ------------------------------------------------- files shown / opened in place
# A run inside an opened project edits the real files, so they are not re-listed in the
# chat as downloads. Only when the user explicitly asks to see a file is it listed, and
# then it is opened on this machine instead of copied.

NOISE_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", "node_modules", ".next", ".nuxt", ".cache", ".idea", ".vscode",
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", "venv", "env",
        "dist", "build", "out", "target", "coverage", ".turbo", ".parcel-cache", ".gradle",
        ".playwright-cli", "logs", "log", "tmp", "temp", "trace", "traces", ".terraform",
    }
)
NOISE_NAMES = frozenset(
    {
        "current", "log", "lock", "manifest", "identity", "options", "log.old", ".ds_store",
        "thumbs.db", "desktop.ini", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
        "poetry.lock", "cargo.lock",
    }
)
NOISE_EXTS = frozenset(
    {
        ".sst", ".meta", ".log", ".ldb", ".wal", ".db", ".sqlite", ".sqlite3", ".lock", ".tmp",
        ".bak", ".swp", ".pyc", ".pyo", ".class", ".o", ".obj", ".so", ".dll", ".exe", ".bin",
        ".map", ".trace", ".pid", ".cache", ".idx", ".pack",
    }
)
_NOISE_NAME_PREFIXES = ("manifest-", "options-", "~$", ".#")
# Never launched by "open": a double click would run them.
_RUNNABLE_EXTS = frozenset(
    {".exe", ".bat", ".cmd", ".com", ".msi", ".ps1", ".vbs", ".vbe", ".jar", ".scr", ".lnk", ".reg",
     ".sh", ".command", ".app", ".dll", ".hta", ".wsf"}
)

_SHOW_FILE_INTENT = re.compile(
    r"(cho\s+(tôi|mình|em|anh|chị)?\s*xem|xem\s+(lại\s+)?(file|tệp|tập tin|ảnh|hình)|hiển thị|hiện\s+(file|tệp|ảnh|hình)|"
    r"mở\s+(file|tệp|tập tin|ảnh|hình)|đưa\s+(file|tệp)|gửi\s+(lại\s+)?(file|tệp|ảnh)|đính kèm|"
    r"\bshow\b|\bdisplay\b|\bopen\s+(the\s+)?(file|image|picture|screenshot)|\bpreview\b|\battach\b|\bsend me\b)",
    re.IGNORECASE,
)


def is_noise_path(relative_path: str) -> bool:
    """Internal / generated / binary files that are never worth showing in the chat."""
    parts = [p for p in re.split(r"[\\/]+", relative_path or "") if p and p != "."]
    if not parts:
        return True
    name = parts[-1].lower()
    if any(part.lower() in NOISE_DIRS for part in parts[:-1]):
        return True
    if any(part.startswith(".") and part.lower() != ".github" for part in parts[:-1]):
        return True
    if name in NOISE_NAMES or name.startswith(_NOISE_NAME_PREFIXES):
        return True
    if name.endswith(".log") or re.search(r"\.log\.\d+$", name):
        return True
    return Path(name).suffix in NOISE_EXTS


def wants_files_shown(text: Optional[str]) -> bool:
    """True when the user explicitly asks to see / open / get a file."""
    return bool(text and _SHOW_FILE_INTENT.search(text))


def mentioned_in(text: Optional[str], relative_path: str) -> bool:
    lowered = (text or "").lower()
    rel = (relative_path or "").replace("\\", "/").lower()
    return bool(rel and (rel in lowered or rel.rsplit("/", 1)[-1] in lowered))


def resolve_project_file(root: Path, relative_path: str) -> Path:
    """The file ``relative_path`` inside ``root``; refuses traversal, absolute paths and noise files."""
    text = (relative_path or "").strip()
    if not text or "\x00" in text:
        raise ValidationError("File path is required", field="path")
    candidate = Path(text.replace("\\", "/"))
    if candidate.is_absolute() or candidate.drive or any(part == ".." for part in candidate.parts):
        raise ValidationError("Path must be relative to the project folder", field="path")
    root_resolved = root.resolve()
    target = (root_resolved / candidate).resolve()
    try:
        rel = target.relative_to(root_resolved).as_posix()
    except ValueError:
        raise ValidationError("Path is outside the project folder", field="path") from None
    if not target.exists():
        raise ValidationError("File not found in the project folder", field="path")
    if target.is_file() and is_noise_path(rel):
        raise ValidationError("This file cannot be opened from the chat", field="path")
    return target


def open_on_machine(target: Path, *, reveal: bool = False) -> str:
    """Open ``target`` with the default app, or show it in the file manager. Returns the action taken."""
    import subprocess
    import sys

    reveal = reveal or target.is_dir() or target.suffix.lower() in _RUNNABLE_EXTS
    if sys.platform.startswith("win"):
        if reveal:
            subprocess.Popen(["explorer", f"/select,{target}"] if target.is_file() else ["explorer", str(target)])
            return "revealed"
        os.startfile(str(target))  # type: ignore[attr-defined]  # noqa: S606
        return "opened"
    if sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(target)] if reveal else ["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target.parent if reveal else target)])
    return "revealed" if reveal else "opened"
