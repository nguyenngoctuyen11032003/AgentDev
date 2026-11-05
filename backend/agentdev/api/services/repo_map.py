"""Compact repo map for the project overview (ADR 0003).

A folder tree that only shows structure and file counts, plus the top-level symbols (functions, classes,
exports) of the few "hot" files, capped in characters. It replaces the flat 160-line file tree that the lead
and members re-read on every model call. Result is cached by the paths, sizes and mtimes of the files.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ENV_FLAG = "AGENTDEV_REPO_MAP"

MAX_MAP_CHARS = 3600
_TREE_BUDGET_CHARS = 1800
_HOT_FILES = 8
_SYMBOLS_PER_FILE = 8
_MAX_SYMBOL_FILE_BYTES = 200_000
_MAX_DIRS_PER_LEVEL = 12
_MAX_ROOT_FILES = 10
_CACHE_SIZE = 16
# Below this many files the exact file tree is already small and names every path; the map adds nothing.
MIN_FILES_FOR_MAP = 60

_ENTRY_STEMS = {"main", "app", "index", "server", "cli", "__main__", "manage", "program", "lib", "mod"}
_DOC_STEMS = {"readme"}
_MANIFESTS = {"package.json", "pyproject.toml", "cargo.toml", "go.mod", "pom.xml", "build.gradle", "requirements.txt"}

_CORE_DIRS = {"src", "lib", "core", "app", "api", "server", "services", "internal", "cmd"}
_TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs", "e2e", "fixtures", "docs", "examples"}

_PY = re.compile(r"^(?:async\s+)?(?:def|class)\s+(\w+)", re.M)
_JS = re.compile(
    r"^(?:export\s+(?:default\s+)?)?(?:async\s+)?(?:function\*?|class)\s+(\w+)"
    r"|^export\s+(?:const|let|var)\s+(\w+)",
    re.M,
)
_GO = re.compile(r"^func\s+(?:\([^)]*\)\s*)?(\w+)|^type\s+(\w+)\s+(?:struct|interface)", re.M)
_RS = re.compile(r"^(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:fn|struct|enum|trait)\s+(\w+)", re.M)
_JAVA = re.compile(r"^(?:public\s+|final\s+|abstract\s+)*(?:class|interface|enum|record)\s+(\w+)", re.M)

_SYMBOL_PATTERNS: Dict[str, re.Pattern[str]] = {
    ".py": _PY,
    ".js": _JS, ".jsx": _JS, ".ts": _JS, ".tsx": _JS, ".mjs": _JS, ".cjs": _JS, ".vue": _JS, ".svelte": _JS,
    ".go": _GO,
    ".rs": _RS,
    ".java": _JAVA, ".kt": _JAVA, ".cs": _JAVA,
}

_cache: "OrderedDict[str, str]" = OrderedDict()
_cache_lock = threading.Lock()


def repo_map_enabled() -> bool:
    return os.environ.get(ENV_FLAG, "1").strip().lower() not in {"0", "false", "off", "no"}


def _plural(n: int) -> str:
    return f"{n} file" if n == 1 else f"{n} files"


def _build_tree(rels: Sequence[str]) -> Dict[str, Any]:
    tree: Dict[str, Any] = {}
    for rel in rels:
        parts = [p for p in rel.split("/") if p]
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part + "/", {})
        if parts:
            node[parts[-1]] = None
    return tree


def _count_files(node: Dict[str, Any]) -> int:
    return sum(_count_files(child) if isinstance(child, dict) else 1 for child in node.values())


def _render_tree(tree: Dict[str, Any], max_depth: int) -> List[str]:
    def render(node: Dict[str, Any], depth: int) -> List[str]:
        indent = "  " * depth
        lines: List[str] = []
        dirs = sorted((k for k, v in node.items() if isinstance(v, dict)), key=lambda k: (-_count_files(node[k]), k.lower()))
        shown = dirs[:_MAX_DIRS_PER_LEVEL]
        for name in sorted(shown, key=str.lower):
            child = node[name]
            lines.append(f"{indent}{name} ({_plural(_count_files(child))})")
            if depth + 1 < max_depth:
                lines.extend(render(child, depth + 1))
        if len(dirs) > len(shown):
            rest = dirs[len(shown):]
            lines.append(f"{indent}... +{len(rest)} folders ({_plural(sum(_count_files(node[k]) for k in rest))})")
        if depth == 0:
            files = sorted((k for k, v in node.items() if v is None), key=str.lower)
            lines.extend(f"{indent}{name}" for name in files[:_MAX_ROOT_FILES])
            if len(files) > _MAX_ROOT_FILES:
                lines.append(f"{indent}... +{len(files) - _MAX_ROOT_FILES} more files")
        return lines

    return render(tree, 0)


def _fit_tree(tree: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for depth in range(4, 0, -1):
        lines = _render_tree(tree, depth)
        if sum(len(line) + 1 for line in lines) <= _TREE_BUDGET_CHARS:
            return lines
    return lines


def _hot_score(rel: str, mtime: float, newest: float, oldest: float) -> float:
    name = rel.rsplit("/", 1)[-1].lower()
    stem = name.rsplit(".", 1)[0]
    depth = rel.count("/")
    score = 0.0
    if name in _MANIFESTS:
        score += 3
    if stem in _ENTRY_STEMS:
        score += 3
    if stem in _DOC_STEMS:
        score += 1
    score += max(0.0, 2.0 - depth * 0.5)  # shallow files first
    parts = rel.lower().split("/")[:-1]
    if any(part in _CORE_DIRS for part in parts):
        score += 1.5
    if any(part in _TEST_DIRS for part in parts) or stem.startswith("test_") or ".test" in name or ".spec" in name:
        score -= 3
    span = newest - oldest
    if span > 3600:  # a fresh upload or checkout stamps every file alike; only real edit history counts
        score += 2.0 * (mtime - oldest) / span  # recently edited files are where the work happens
    return score


def extract_symbols(path: Path, limit: int = _SYMBOLS_PER_FILE) -> List[str]:
    pattern = _SYMBOL_PATTERNS.get(path.suffix.lower())
    if pattern is None:
        return []
    try:
        if path.stat().st_size > _MAX_SYMBOL_FILE_BYTES:
            return []
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    names: List[str] = []
    for match in pattern.finditer(text):
        name = next((g for g in match.groups() if g), None)
        if name and name not in names and not name.startswith("_"):
            names.append(name)
        if len(names) >= limit:
            break
    return names


def _signature(entries: Sequence[Tuple[Path, str]]) -> Tuple[str, Dict[str, Tuple[int, int]]]:
    digest = hashlib.sha1()
    stats: Dict[str, Tuple[int, int]] = {}
    for path, rel in sorted(entries, key=lambda e: e[1]):
        try:
            st = path.stat()
            stat_pair = (st.st_mtime_ns, st.st_size)
        except OSError:
            stat_pair = (0, 0)
        stats[rel] = stat_pair
        digest.update(f"{rel}\0{stat_pair[0]}\0{stat_pair[1]}\n".encode("utf-8", "replace"))
    return digest.hexdigest(), stats


def build_repo_map(
    entries: Sequence[Tuple[Path, str]],
    *,
    max_chars: int = MAX_MAP_CHARS,
    use_cache: bool = True,
) -> List[str]:
    """Return the map as lines. ``entries`` are ``(absolute_path, posix_relative_path)`` pairs."""

    if not entries:
        return []
    key, stats = _signature(entries)
    if use_cache:
        with _cache_lock:
            hit = _cache.get(key)
            if hit is not None:
                _cache.move_to_end(key)
                return hit.split("\n")

    by_rel = {rel: path for path, rel in entries}
    mtimes = {rel: stats[rel][0] / 1e9 for rel in by_rel}
    newest, oldest = max(mtimes.values()), min(mtimes.values())
    ranked = sorted(
        (rel for rel, path in by_rel.items() if path.suffix.lower() in _SYMBOL_PATTERNS),
        key=lambda r: (-_hot_score(r, mtimes[r], newest, oldest), r),
    )

    lines = _fit_tree(_build_tree(list(by_rel)))
    used = sum(len(line) + 1 for line in lines)
    symbol_lines: List[str] = []
    for rel in ranked:
        if len(symbol_lines) >= _HOT_FILES:
            break
        names = extract_symbols(by_rel[rel])
        if not names:
            continue
        line = f"{rel}: {', '.join(names)}"
        if used + len(line) + 1 > max_chars:
            break
        symbol_lines.append(line)
        used += len(line) + 1
    if symbol_lines:
        lines = [*lines, "", "Top-level symbols of the main files:", *symbol_lines]

    text = "\n".join(lines)
    if use_cache:
        with _cache_lock:
            _cache[key] = text
            while len(_cache) > _CACHE_SIZE:
                _cache.popitem(last=False)
    return lines


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def render_overview_tree(
    entries: Sequence[Tuple[Path, str]], legacy_tree: List[str]
) -> Tuple[str, List[str]]:
    """(heading, lines) for the overview.

    The repo map is used only when enabled and smaller than the legacy tree, so a prompt never grows.
    """

    if repo_map_enabled() and len(entries) >= MIN_FILES_FOR_MAP:
        mapped = build_repo_map(entries)
        if mapped and sum(len(x) + 1 for x in mapped) < sum(len(x) + 1 for x in legacy_tree):
            return "Repo map (folders with file counts, then main symbols)", mapped
    return "Folder tree", legacy_tree
