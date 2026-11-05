"""What a Lab run produced: list, serve, open and delete the files of a run, and clean up old runs.

Every run of a Lab job writes into its own graph folder ``storage/warehouse/lab_<workflow>_<ts>/``; the
agents' product is the ``code_workspace/`` inside it (when the run made one). The Lab page lets the user browse
and preview that product and delete results they no longer need. All file access here is confined to the run's
folder: the folder itself must be a direct ``lab_*`` child of the warehouse, and every requested path is
resolved and checked to stay inside it, so a crafted path or a symlink an agent left behind can never reach
AgentDev's own files. Nothing is ever deleted automatically: only on an explicit request.
"""

from __future__ import annotations

import contextlib
import json
import mimetypes
import os
import re
import shutil
import stat
import time
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Union

MAX_FILES = 2000
MAX_TEXT_BYTES = 2 * 1024 * 1024
CODE_WORKSPACE = "code_workspace"
RUN_DIR_PREFIX = "lab_"

# Folders that are tooling or caches, never what the user asked the agents to make.
SKIP_DIR_NAMES = frozenset({
    "node_modules", ".venv", "venv", ".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
})
SKIP_DIR_PATHS = frozenset({".next/cache", "dist/.vite"})  # nested caches, matched at the end of a relative path
# Files the engine writes next to the product in the graph folder (only hidden when there is no code_workspace).
_INTERNAL_FILES = frozenset({"execution_logs.json", "node_outputs.yaml", "workflow_summary.yaml"})
_INTERNAL_PATTERN = re.compile(r"token_usage_.*\.json$")

# HTML (and SVG, which can carry scripts) is shown in a sandbox: scripts may run but get an opaque origin, so
# they cannot call AgentDev's API with the user's page or read its storage.
SANDBOX_CSP = "sandbox allow-scripts allow-forms allow-popups"

_KINDS: dict[str, tuple[str, ...]] = {
    "markdown": (".md", ".markdown", ".mdx"),
    "html": (".html", ".htm"),
    "pdf": (".pdf",),
    "image": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico", ".avif"),
    "video": (".mp4", ".webm", ".mov", ".m4v", ".ogv", ".mkv", ".avi"),
    "audio": (".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac", ".opus"),
    "text": (".txt", ".log", ".csv", ".tsv", ".rst", ".text"),
    "code": (
        ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".vue", ".svelte", ".css", ".scss", ".sass", ".less",
        ".json", ".jsonc", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env", ".xml", ".sql", ".sh", ".bash",
        ".ps1", ".bat", ".cmd", ".java", ".kt", ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php",
        ".swift", ".dart", ".lua", ".r", ".pl", ".graphql", ".proto", ".gradle", ".lock", ".gitignore",
        ".dockerignore", ".editorconfig", ".prettierrc", ".eslintrc", ".babelrc", ".npmrc", ".nvmrc",
    ),
}
_EXT_KIND = {ext: kind for kind, exts in _KINDS.items() for ext in exts}
_CODE_NAMES = frozenset({"dockerfile", "makefile", "procfile", "license", "readme", "requirements.txt"})
TEXT_KINDS = frozenset({"markdown", "text", "code", "html"})

# Windows reads MIME types from the registry, which is often wrong (.js as text/plain, .svg missing).
_MIME = {
    ".html": "text/html", ".htm": "text/html", ".css": "text/css", ".js": "text/javascript",
    ".mjs": "text/javascript", ".cjs": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml",
    ".md": "text/markdown", ".markdown": "text/markdown", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp", ".ico": "image/x-icon",
    ".avif": "image/avif", ".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime",
    ".m4v": "video/mp4", ".ogv": "video/ogg", ".mp3": "audio/mpeg", ".wav": "audio/wav", ".ogg": "audio/ogg",
    ".m4a": "audio/mp4", ".flac": "audio/flac", ".pdf": "application/pdf", ".wasm": "application/wasm",
    ".txt": "text/plain", ".csv": "text/csv", ".xml": "application/xml", ".woff": "font/woff",
    ".woff2": "font/woff2", ".ttf": "font/ttf",
}


class LabOutputsError(Exception):
    """A request the routes turn into an HTTP error (``status_code`` + a message for the user)."""

    def __init__(self, status_code: int, detail: str, code: str = "", params: dict[str, Any] | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.code = code  # stable id the frontend translates (the message stays for older clients / logs)
        self.params = dict(params or {})

    def http_detail(self) -> dict[str, Any]:
        """HTTP ``detail`` body: ``message`` is what older clients show, ``code``/``params`` let the UI translate."""
        return {"message": self.detail, "code": self.code or "lab_error", "params": self.params}


# ----------------------------------------------------------------------------------- jobs and run folders


def warehouse_root() -> Path:
    """Read at call time so a redirected storage dir (and tests) are honoured."""
    from agentdev import paths

    return Path(paths.WAREHOUSE_DIR)


def _runner() -> Any:
    from agentdev.api.services import workflow_lab

    return workflow_lab.get_lab_runner()


def _job_status(job: Any) -> str:
    status = getattr(job, "status", None)
    if status is None:
        status = (job.to_dict() or {}).get("status", "")
    return str(status or "")


def is_running(job: Any) -> bool:
    return _job_status(job) in ("queued", "running")


def _job_results(job: Any) -> list[dict[str, Any]]:
    """The runs of ``job`` in the order GET /api/lab/jobs/{id} returns them (that order is the run index)."""
    lock = getattr(job, "lock", None)
    if lock is not None and isinstance(getattr(job, "results", None), list):
        with lock:
            results = [dict(r) for r in job.results]
    else:
        results = [dict(r) for r in (job.to_dict() or {}).get("results") or []]
    return sorted(results, key=lambda r: (r.get("repeat", 0), r.get("scenario", 0)))


def _get_job(job_id: str) -> Any:
    job = _runner().get(job_id)
    if job is None:
        raise LabOutputsError(404, "Lab run not found", "lab_job_not_found", {"job_id": job_id})
    return job


def checked_run_dir(raw: Any) -> Path | None:
    """``raw`` as a run folder when it is a direct ``lab_*`` child of the warehouse (not a link), else None.

    A job file is plain JSON on disk: its ``output_dir`` is not trusted to point anywhere else.
    """
    if not raw or not isinstance(raw, str):
        return None
    try:
        root = warehouse_root().resolve()
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
            return None
        resolved = path.resolve()
    except (OSError, ValueError):
        return None
    if resolved.parent != root or not resolved.name.startswith(RUN_DIR_PREFIX):
        return None
    return resolved


RunRef = Union[int, str]
_RUN_REF = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def valid_run_ref(run: Any) -> bool:
    """A run reference from a URL: a run's ``run_id`` or (legacy) its position, plain URL-safe text only."""
    return isinstance(run, int) and run >= 0 or isinstance(run, str) and bool(_RUN_REF.match(run))


def run_key(result: dict[str, Any], index: int) -> str:
    """Stable key of one run: its ``run_id`` when the job records one, else (old jobs) its position."""
    run_id = result.get("run_id")
    return str(run_id) if run_id not in (None, "") else str(index)


def _find_run(results: list[dict[str, Any]], run: RunRef) -> tuple[int, dict[str, Any]] | None:
    """The run that ``run`` names: a matching ``run_id`` first, else a position (old jobs, old clients).

    Positions shift when a job is resumed (errored runs are dropped and re-run) or while parallel runs are
    added, so the UI keys runs by ``run_id``; the position fallback keeps jobs without ids working."""
    text = str(run)
    for index, result in enumerate(results):
        run_id = result.get("run_id")
        if run_id not in (None, "") and str(run_id) == text:
            return index, result
    if isinstance(run, int) or text.isdigit():
        index = int(text)
        if 0 <= index < len(results):
            return index, results[index]
    return None


def _run_not_found(job_id: str, run: RunRef) -> LabOutputsError:
    return LabOutputsError(404, "Run not found in this Lab job", "lab_run_not_found",
                           {"job_id": job_id, "run": str(run)})


def canonical_run_key(job_id: str, run: RunRef) -> str:
    """The stable key (``run_id``, or position for old jobs) of the run ``run`` names. Raises 404 when unknown."""
    results = _job_results(_get_job(job_id))
    found = _find_run(results, run) if valid_run_ref(run) else None
    if found is None:
        raise _run_not_found(job_id, run)
    index, result = found
    return run_key(result, index)


def resolve_run_dir(job_id: str, run: RunRef) -> Path | None:
    """The graph folder of run ``run`` (a ``run_id``, or a legacy position) of job ``job_id``.

    Raises ``LabOutputsError(404)`` when the job or the run does not exist. Returns None when the run recorded
    no usable folder (it failed before starting, or the path is outside the warehouse). The folder may no
    longer exist on disk (deleted): callers check ``is_dir()``.
    """
    job = _get_job(job_id)
    results = _job_results(job)
    found = _find_run(results, run) if valid_run_ref(run) else None
    if found is None:
        raise _run_not_found(job_id, run)
    index, result = found
    recorded = checked_run_dir(result.get("output_dir"))
    if recorded is not None:
        return recorded
    return inferred_run_dirs(job).get(index)


# Lab graph folders are named ``lab_<workflow>_<YYYYmmddHHMMSS>_<6 hex>_<YYYYmmddHHMMSS>`` (session, then turn).
_SESSION_NAME = re.compile(r"^lab_(?P<stem>.+)_(?P<start>\d{14})_[0-9a-f]{6}_\d{14}$")


def inferred_run_dirs(job: Any, referenced: set[str] | None = None) -> dict[int, Path]:
    """Folders of failed runs that recorded none (older versions dropped ``output_dir`` on an error or timeout).

    The job's unreferenced sessions of the same workflow that started inside its time window are matched, in
    start order, to its failed runs without a folder (runs start in the same order). Only an exact count match
    is trusted: when another job ran the same workflow at the same time the pairing is ambiguous, so nothing is
    inferred. Each folder returned is the session's last turn.
    """
    if is_running(job):
        return {}
    data = job.to_dict() or {}
    stem = Path(str(data.get("workflow") or "")).stem
    started, finished = data.get("started_at"), data.get("finished_at")
    if not stem or not started or not finished:
        return {}
    results = _job_results(job)
    missing = [i for i, r in enumerate(results)
               if r.get("status") == "error" and checked_run_dir(r.get("output_dir")) is None]
    if not missing:
        return {}
    if referenced is None:
        referenced = _recorded_sessions()
    low = datetime.fromtimestamp(float(started) - 5).strftime("%Y%m%d%H%M%S")
    high = datetime.fromtimestamp(float(finished)).strftime("%Y%m%d%H%M%S")
    sessions: dict[str, list[Path]] = {}
    for folder in _lab_dirs():
        match = _SESSION_NAME.match(folder.name)
        if not match or match["stem"] != stem or not low <= match["start"] <= high:
            continue
        key = session_key(folder.name)
        if key not in referenced:
            sessions.setdefault(key, []).append(folder)
    if len(sessions) != len(missing):
        return {}
    ordered = sorted(sessions.values(), key=lambda turns: min(t.name for t in turns))
    return {index: max(turns, key=lambda t: t.name) for index, turns in zip(missing, ordered)}


def job_products(job_id: str) -> dict[str, Any]:
    """One line per run for the Lab's product overview: what it made and whether it can be opened or run."""
    job = _get_job(job_id)
    results = _job_results(job)
    inferred = inferred_run_dirs(job)
    manager = _preview_manager()
    runs: list[dict[str, Any]] = []
    for index, result in enumerate(results):
        run_dir = checked_run_dir(result.get("output_dir")) or inferred.get(index)
        key = run_key(result, index)
        entry: dict[str, Any] = {"run": index, "run_id": key, "scenario": result.get("scenario", 0), "repeat": result.get("repeat", 1),
                                 "status": result.get("status", ""), "available": False, "inferred": index in inferred,
                                 "file_count": 0, "total_bytes": 0, "kinds": {}, "project": _no_project(),
                                 "preview": None}
        if run_dir is not None and run_dir.is_dir():
            root = product_dir(run_dir)
            is_graph_dir = root == run_dir
            kinds: dict[str, int] = {}
            for rel, size in _walk(root):
                if _is_internal(rel, is_graph_dir):
                    continue
                entry["file_count"] += 1
                entry["total_bytes"] += size
                kind = file_kind(rel.rsplit("/", 1)[-1])
                kinds[kind] = kinds.get(kind, 0) + 1
            entry.update(available=entry["file_count"] > 0, kinds=kinds, project=detect_project(root))
            if manager is not None:
                with contextlib.suppress(Exception):
                    status = manager.status(job_id, key)
                    if status.get("status") in ("installing", "starting", "running"):
                        entry["preview"] = {k: status.get(k) for k in ("status", "url", "frameable")}
        runs.append(entry)
    return {"job_id": job_id, "runs": runs}


def product_dir(run_dir: Path) -> Path:
    """Where the agents' product is: ``code_workspace/`` when the run made one, else the graph folder."""
    workspace = Path(run_dir) / CODE_WORKSPACE
    try:
        if workspace.is_dir() and not workspace.is_symlink():
            return workspace
    except OSError:
        pass
    return Path(run_dir)


# ----------------------------------------------------------------------------------- listing


def file_kind(name: str) -> str:
    lowered = name.lower()
    suffix = Path(lowered).suffix
    if suffix in _EXT_KIND:
        return _EXT_KIND[suffix]
    if lowered in _CODE_NAMES or (lowered.startswith(".") and not suffix):
        return "code"
    if lowered.startswith((".env", "dockerfile")):
        return "code"
    return "binary"


def content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    mime = _MIME.get(suffix) or mimetypes.guess_type(path.name)[0]
    if not mime:
        mime = "text/plain" if file_kind(path.name) in TEXT_KINDS else "application/octet-stream"
    if mime.startswith("text/") or mime in ("application/json", "application/xml", "image/svg+xml"):
        mime += "; charset=utf-8"
    return mime


def _is_internal(rel: str, is_graph_dir: bool) -> bool:
    if not is_graph_dir or "/" in rel:
        return False
    return rel in _INTERNAL_FILES or bool(_INTERNAL_PATTERN.match(rel))


def _skip_dir(rel: str, name: str) -> bool:
    return name in SKIP_DIR_NAMES or any(rel == p or rel.endswith("/" + p) for p in SKIP_DIR_PATHS)


def _walk(root: Path) -> Iterable[tuple[str, int]]:
    """(relative posix path, size) of every product file under ``root``, sorted, not following links and not
    descending into tooling folders (node_modules, .venv, caches)."""
    pending: list[tuple[Path, str]] = [(root, "")]
    while pending:
        current, prefix = pending.pop()
        try:
            with os.scandir(current) as scanner:
                entries = sorted(scanner, key=lambda e: e.name.lower())
        except OSError:
            continue
        subdirs: list[tuple[Path, str]] = []
        for entry in entries:
            try:
                if entry.is_symlink() or (hasattr(entry, "is_junction") and entry.is_junction()):
                    continue
                rel = f"{prefix}{entry.name}"
                if entry.is_dir(follow_symlinks=False):
                    if not _skip_dir(rel, entry.name):
                        subdirs.append((Path(entry.path), rel + "/"))
                elif entry.is_file(follow_symlinks=False):
                    yield rel, entry.stat(follow_symlinks=False).st_size
            except OSError:
                continue
        pending.extend(reversed(subdirs))


def empty_listing(root: str = "") -> dict[str, Any]:
    """The listing of a product folder that does not exist (deleted, or nothing written yet)."""
    return {"available": False, "root": root, "total_bytes": 0, "file_count": 0, "truncated": False, "files": [],
            "project": _no_project()}


def list_dir(root: Path, *, is_graph_dir: bool = False, max_scan: int | None = None,
             hide_top: frozenset[str] = frozenset(), project: dict[str, Any] | None = None) -> dict[str, Any]:
    """Every product file under ``root`` (at most ``MAX_FILES`` listed) with totals and the project type.

    ``max_scan`` stops counting after that many files (a large opened project); ``scan_capped`` then says the
    totals are a lower bound. ``hide_top`` names top-level folders that are not product (inputs). ``project``
    replaces the detection at ``root`` when the caller found the app elsewhere.
    """
    files: list[dict[str, Any]] = []
    total = count = 0
    capped = False
    for rel, size in _walk(root):
        if _is_internal(rel, is_graph_dir) or (hide_top and rel.split("/", 1)[0] in hide_top):
            continue
        if max_scan is not None and count >= max_scan:
            capped = True
            break
        total += size
        count += 1
        if len(files) < MAX_FILES:
            files.append({"path": rel, "size": size, "kind": file_kind(rel.rsplit("/", 1)[-1])})
    listing = {"available": True, "root": str(root), "total_bytes": total, "file_count": count,
               "truncated": count > len(files) or capped, "files": files,
               "project": project if project is not None else detect_project(root)}
    if capped:
        listing["scan_capped"] = True
    return listing


def summarize_dir(root: Path, *, is_graph_dir: bool = False, max_scan: int | None = None,
                  hide_top: frozenset[str] = frozenset(), project: dict[str, Any] | None = None) -> dict[str, Any]:
    """Counts of what ``root`` holds (no file list): for a one-line product summary. Options as ``list_dir``."""
    count = total = 0
    kinds: dict[str, int] = {}
    capped = False
    for rel, size in _walk(root):
        if _is_internal(rel, is_graph_dir) or (hide_top and rel.split("/", 1)[0] in hide_top):
            continue
        if max_scan is not None and count >= max_scan:
            capped = True
            break
        count += 1
        total += size
        kind = file_kind(rel.rsplit("/", 1)[-1])
        kinds[kind] = kinds.get(kind, 0) + 1
    return {"available": count > 0, "file_count": count, "total_bytes": total, "kinds": kinds,
            "project": project if project is not None else detect_project(root), "scan_capped": capped}


def list_files(job_id: str, run_index: RunRef) -> dict[str, Any]:
    run_dir = resolve_run_dir(job_id, run_index)
    if run_dir is None or not run_dir.is_dir():
        return empty_listing(str(run_dir) if run_dir else "")
    root = product_dir(run_dir)
    listing = list_dir(root, is_graph_dir=root == run_dir)
    found = _find_run(_job_results(_get_job(job_id)), run_index)
    listing["inferred"] = found is None or not checked_run_dir(found[1].get("output_dir"))
    return listing


# ----------------------------------------------------------------------------------- project type


def _no_project(summary: str = "Không có ứng dụng để chạy thử") -> dict[str, Any]:
    return {"type": "none", "can_preview": False, "entry": "", "summary": summary}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        if path.is_file() and path.stat().st_size < 1024 * 1024:
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        pass
    return {}


def _read_head(path: Path, limit: int = 64 * 1024) -> str:
    try:
        if path.is_file():
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                return handle.read(limit)
    except OSError:
        pass
    return ""


_NODE_LABELS = (("next", "Next.js"), ("nuxt", "Nuxt"), ("vite", "Vite"), ("react-scripts", "Create React App"),
                ("@angular/core", "Angular"), ("svelte", "Svelte"), ("vue", "Vue"), ("react", "React"),
                ("express", "Express"), ("fastify", "Fastify"), ("koa", "Koa"), ("@nestjs/core", "NestJS"))


def _node_labels(package: dict[str, Any]) -> list[str]:
    deps = {**(package.get("dependencies") or {}), **(package.get("devDependencies") or {})}
    labels: list[str] = []
    for dep, label in _NODE_LABELS:
        if dep in deps and label not in labels:
            labels.append(label)
    return labels[:3]


def _node_runnable(package: dict[str, Any]) -> bool:
    scripts = package.get("scripts") or {}
    deps = {**(package.get("dependencies") or {}), **(package.get("devDependencies") or {})}
    return bool(isinstance(scripts, dict) and (scripts.get("dev") or scripts.get("start"))) or "vite" in deps


_PY_WEB = (("fastapi", "FastAPI"), ("flask", "Flask"), ("django", "Django"), ("streamlit", "Streamlit"),
           ("gradio", "Gradio"), ("uvicorn", "Uvicorn"))
_PY_ENTRIES = ("main.py", "app.py", "server.py", "manage.py", "run.py", "wsgi.py", "asgi.py")


def _find_index_html(root: Path) -> str:
    """``index.html`` at the root, else the shallowest one at most two folders down (outside tooling dirs)."""
    if (root / "index.html").is_file():
        return "index.html"
    for rel, _size in _walk(root):
        if rel.count("/") > 2:
            continue
        if rel.rsplit("/", 1)[-1].lower() == "index.html":
            return rel
    return ""


def detect_project(directory: Path) -> dict[str, Any]:
    """What kind of app the product is, and whether "Chạy thử" can start it.

    Returns ``{"type": "static|node|python|none", "can_preview", "entry", "summary"}``. The order matters: a
    package.json means a Node app even when it also ships an index.html (Vite keeps one at the root).
    """
    root = Path(directory)
    if not root.is_dir():
        return _no_project()
    package_path = root / "package.json"
    if package_path.is_file():
        package = _read_json(package_path)
        labels = _node_labels(package)
        summary = "Ứng dụng Node" + (f" ({' + '.join(labels)})" if labels else "")
        return {"type": "node", "can_preview": _node_runnable(package), "entry": "package.json", "summary": summary}
    for client, server in (("client", "server"), ("frontend", "backend"), ("web", "api")):
        parts = [name for name in (client, server) if (root / name / "package.json").is_file()]
        if parts:
            packages = [_read_json(root / name / "package.json") for name in parts]
            labels: list[str] = []
            for package in packages:
                labels += [label for label in _node_labels(package) if label not in labels]
            summary = f"Ứng dụng Node ({' + '.join(labels[:3]) or ' + '.join(parts)})"
            return {"type": "node", "can_preview": any(_node_runnable(p) for p in packages),
                    "entry": f"{parts[0]}/package.json", "summary": summary}
    requirements = " ".join(_read_head(root / name).lower() for name in ("requirements.txt", "pyproject.toml"))
    for entry in _PY_ENTRIES:
        source = _read_head(root / entry)
        if not source and not (root / entry).is_file():
            continue
        text = (requirements + " " + source).lower()
        frameworks = [label for key, label in _PY_WEB if re.search(rf"\b{re.escape(key)}\b", text)]
        if frameworks:
            return {"type": "python", "can_preview": True, "entry": entry,
                    "summary": f"Ứng dụng Python ({' + '.join(frameworks[:2])})"}
    index = _find_index_html(root)
    if index:
        return {"type": "static", "can_preview": True, "entry": index, "summary": "Trang web tĩnh (HTML)"}
    if requirements.strip() or any((root / name).is_file() for name in _PY_ENTRIES):
        entry = next((name for name in _PY_ENTRIES if (root / name).is_file()), "")
        return {"type": "python", "can_preview": False, "entry": entry,
                "summary": "Mã Python (không phải ứng dụng web)"}
    return _no_project()


# ----------------------------------------------------------------------------------- one file


def resolve_product_file(root: Path, relative_path: str, *, allow_dir: bool = False) -> Path:
    """``relative_path`` inside ``root``: refuses absolute paths, ``..``, and links that lead outside."""
    text = (relative_path or "").strip().replace("\\", "/")
    if "\x00" in text:
        raise LabOutputsError(400, "Invalid path", "lab_path_invalid")
    candidate = Path(text) if text else Path(".")
    if candidate.is_absolute() or candidate.drive or text.startswith("/") or any(p == ".." for p in candidate.parts):
        raise LabOutputsError(400, "Path must be relative to the run's folder", "lab_path_not_relative")
    root_resolved = Path(root).resolve()
    try:
        target = (root_resolved / candidate).resolve()
    except (OSError, ValueError) as exc:
        raise LabOutputsError(400, "Invalid path", "lab_path_invalid") from exc
    if target != root_resolved and root_resolved not in target.parents:
        raise LabOutputsError(400, "Path is outside the run's folder", "lab_path_outside")
    if target.is_dir():
        if not allow_dir:
            raise LabOutputsError(400, "This path is a folder", "lab_path_is_folder")
    elif not target.is_file():
        raise LabOutputsError(404, "File not found", "lab_file_not_found")
    return target


def _existing_product(job_id: str, run_index: RunRef) -> Path:
    run_dir = resolve_run_dir(job_id, run_index)
    if run_dir is None or not run_dir.is_dir():
        raise LabOutputsError(404, "The files of this run were deleted or never created", "lab_run_files_missing")
    return product_dir(run_dir)


def response_headers(path: Path) -> dict[str, str]:
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "no-store"}
    if path.suffix.lower() in (".html", ".htm", ".svg", ".xhtml", ".xml"):
        headers["Content-Security-Policy"] = SANDBOX_CSP
    return headers


def viewer_file(root: Path, relative_path: str) -> Path:
    """The file of ``root`` to send for the viewer; text over 2 MB is refused (the viewer would freeze on it)."""
    target = resolve_product_file(root, relative_path)
    if file_kind(target.name) in TEXT_KINDS and target.stat().st_size > MAX_TEXT_BYTES:
        raise LabOutputsError(413, "This text file is too large to show (over 2 MB); open it on the machine",
                              "lab_file_too_large", {"max_bytes": MAX_TEXT_BYTES})
    return target


def site_file_in(root: Path, relative_path: str) -> Path:
    """A file of ``root`` served as a static site: a folder (or the root) gives its index.html."""
    target = resolve_product_file(root, relative_path, allow_dir=True)
    if target.is_dir():
        index = target / "index.html"
        if not index.is_file():
            raise LabOutputsError(404, "No index.html in this folder", "lab_site_no_index")
        target = index
    return target


def run_file(job_id: str, run_index: RunRef, relative_path: str) -> Path:
    """The file to send for the viewer; text over 2 MB is refused (the viewer would freeze on it)."""
    return viewer_file(_existing_product(job_id, run_index), relative_path)


def site_file(job_id: str, run_index: RunRef, relative_path: str) -> Path:
    """A file of the product served as a static site: a folder (or the root) gives its index.html."""
    return site_file_in(_existing_product(job_id, run_index), relative_path)


def open_target(job_id: str, run_index: RunRef, relative_path: str) -> Path:
    """The file or folder to open on the machine (empty path = the product folder)."""
    return resolve_product_file(_existing_product(job_id, run_index), relative_path, allow_dir=True)


# ----------------------------------------------------------------------------------- previews (optional)


def _preview_manager() -> Any:
    """The app-preview manager when that module is installed; this module works without it."""
    try:
        from agentdev.api.services.app_preview import get_preview_manager
    except ImportError:
        return None
    try:
        return get_preview_manager()
    except Exception:  # noqa: BLE001 - a broken preview manager must not block deleting files
        return None


def _stop_previews(run_dir: Path) -> None:
    manager = _preview_manager()
    if manager is None or not hasattr(manager, "stop_for_dir"):
        return
    for path in {run_dir, product_dir(run_dir)}:
        # Best effort: the delete that follows reports what could not go.
        with contextlib.suppress(Exception):
            manager.stop_for_dir(path)


def _has_live_preview(run_dir: Path) -> bool:
    manager = _preview_manager()
    if manager is None or not hasattr(manager, "has_live_preview"):
        return False
    for path in {run_dir, product_dir(run_dir)}:
        try:
            if manager.has_live_preview(path):
                return True
        except Exception:  # noqa: BLE001 - unknown state: keep the folder
            return True
    return False


# ----------------------------------------------------------------------------------- delete and storage


def dir_size(path: Path) -> int:
    total = 0
    pending = [Path(path)]
    while pending:
        current = pending.pop()
        try:
            with os.scandir(current) as scanner:
                for entry in scanner:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                        else:
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


def _make_writable_and_retry(func: Any, path: str, _exc: BaseException) -> None:
    """``shutil.rmtree`` error handler: git objects and npm files are often read-only on Windows."""
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        pass


def _remove_tree(path: Path) -> int:
    """Delete ``path`` (never following links out of it); returns the bytes freed."""
    before = dir_size(path)
    try:
        if path.is_symlink():
            path.unlink()
            return 0
        shutil.rmtree(path, onexc=_make_writable_and_retry)
    except OSError:
        pass
    after = dir_size(path) if path.exists() else 0
    return max(0, before - after)


_TS_SUFFIX = re.compile(r"_\d{14}$")


def session_key(name: str) -> str:
    """The Lab session a graph folder belongs to: a run approving a plan takes two turns, each in its own
    ``<session>_<timestamp>`` folder, and only the last one is recorded in the job."""
    return os.path.normcase(_TS_SUFFIX.sub("", name))


def _lab_dirs() -> list[Path]:
    root = warehouse_root()
    try:
        entries = list(os.scandir(root))
    except OSError:
        return []
    dirs = []
    for entry in entries:
        try:
            if (entry.name.startswith(RUN_DIR_PREFIX) and not entry.is_symlink()
                    and entry.is_dir(follow_symlinks=False)):
                dirs.append(Path(entry.path).resolve())
        except OSError:
            continue
    return dirs


def _sibling_turn_dirs(run_dir: Path) -> list[Path]:
    key = session_key(run_dir.name)
    return [d for d in _lab_dirs() if d != run_dir and session_key(d.name) == key]


def delete_run_outputs(job_id: str, run_index: RunRef) -> dict[str, Any]:
    """Delete the folder of one run (and the earlier turn folders of the same run); the run entry stays."""
    job = _get_job(job_id)
    if is_running(job):
        raise LabOutputsError(409, "This Lab job is still running; stop it before deleting its files",
                              "lab_job_running")
    run_dir = resolve_run_dir(job_id, run_index)
    if run_dir is None or not run_dir.is_dir():
        return {"deleted": False, "freed_bytes": 0}
    targets = [run_dir, *_sibling_turn_dirs(run_dir)]
    freed = 0
    for target in targets:
        _stop_previews(target)
        freed += _remove_tree(target)
    return {"deleted": not run_dir.exists(), "freed_bytes": freed}


def _all_jobs() -> list[Any]:
    """Every job: the ones in memory (running) and every stored job file."""
    runner = _runner()
    jobs: dict[str, Any] = dict(getattr(runner, "_jobs", {}) or {})
    try:
        folder = runner._dir()
        names = [p.stem for p in Path(folder).glob("*.json")]
    except (AttributeError, OSError):
        names = []
    for job_id in names:
        if job_id not in jobs:
            job = runner.get(job_id)
            if job is not None:
                jobs[job_id] = job
    return list(jobs.values())


def _recorded_sessions() -> set[str]:
    """Sessions some job recorded as a run's folder (not counting inferred ones)."""
    recorded: set[str] = set()
    for job in _all_jobs():
        for result in _job_results(job):
            run_dir = checked_run_dir(result.get("output_dir"))
            if run_dir is not None:
                recorded.add(session_key(run_dir.name))
    return recorded


def _references() -> tuple[set[str], set[str], float | None]:
    """(sessions referenced by any job, sessions of running jobs, start time of the oldest running job)."""
    referenced: set[str] = set()
    running: set[str] = set()
    oldest_running: float | None = None
    for job in _all_jobs():
        live = is_running(job)
        if live:
            started = getattr(job, "started_at", None) or (job.to_dict() or {}).get("started_at") or time.time()
            oldest_running = started if oldest_running is None else min(oldest_running, float(started))
        for result in _job_results(job):
            run_dir = checked_run_dir(result.get("output_dir"))
            if run_dir is None:
                continue
            key = session_key(run_dir.name)
            referenced.add(key)
            if live:
                running.add(key)
    recorded = set(referenced)
    for job in _all_jobs():
        with contextlib.suppress(Exception):
            referenced.update(session_key(d.name) for d in inferred_run_dirs(job, recorded).values())
    return referenced, running, oldest_running


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()


def storage_stats() -> dict[str, Any]:
    dirs = _lab_dirs()
    referenced, _running, _oldest = _references()
    mtimes = [_mtime(d) for d in dirs]
    return {
        "total_bytes": sum(dir_size(d) for d in dirs),
        "run_dirs": len(dirs),
        "oldest": _iso(min(mtimes)) if mtimes else None,
        "orphan_dirs": sum(1 for d in dirs if session_key(d.name) not in referenced),
    }


def cleanup_storage(older_than_days: int, orphans_only: bool) -> dict[str, Any]:
    """Delete ``lab_*`` folders older than ``older_than_days`` (by mtime); with ``orphans_only`` only those no
    job refers to. Never touches a running job's folders, a folder a running job may be writing right now
    (newer than its start, not yet recorded) or a folder with a live preview."""
    referenced, running, oldest_running = _references()
    cutoff = time.time() - max(0, int(older_than_days)) * 86400
    deleted = freed = 0
    for path in _lab_dirs():
        key = session_key(path.name)
        mtime = _mtime(path)
        if key in running or mtime > cutoff:
            continue
        if orphans_only and key in referenced:
            continue
        if key not in referenced and oldest_running is not None and mtime >= oldest_running - 5:
            continue  # may be the in-progress run of a running job
        if _has_live_preview(path):
            continue
        freed += _remove_tree(path)
        if not path.exists():
            deleted += 1
    return {"deleted": deleted, "freed_bytes": freed}


# ------------------------------------------------------------------------------------- automatic retention

DEFAULT_OUTPUT_RETENTION_DAYS = 14
DEFAULT_JOBS_PER_WORKFLOW = 100


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


def auto_prune() -> dict[str, Any]:
    """Housekeeping run after every finished Lab job (never raises).

    * Product folders (``warehouse/lab_*``, the big part) older than ``AGENTDEV_LAB_OUTPUT_RETENTION_DAYS``
      (default 14, 0 = keep forever) are deleted. The job record stays, so scores and history survive.
    * Job records (``lab_jobs/*.json``, a few KB each) beyond the newest ``AGENTDEV_LAB_JOBS_PER_WORKFLOW``
      per workflow (default 100, 0 = unlimited) are deleted.
    Running jobs and live previews are never touched (see ``cleanup_storage``)."""
    result: dict[str, Any] = {"deleted": 0, "freed_bytes": 0, "jobs_deleted": 0}
    try:
        days = _env_int("AGENTDEV_LAB_OUTPUT_RETENTION_DAYS", DEFAULT_OUTPUT_RETENTION_DAYS)
        if days > 0:
            result.update(cleanup_storage(days, False))
        cap = _env_int("AGENTDEV_LAB_JOBS_PER_WORKFLOW", DEFAULT_JOBS_PER_WORKFLOW)
        if cap > 0:
            result["jobs_deleted"] = _prune_job_records(cap)
    except Exception:  # noqa: BLE001 - housekeeping must never break a finished job
        pass
    return result


def _prune_job_records(keep: int) -> int:
    runner = _runner()
    folder = Path(runner._dir())
    live = {job_id for job_id, job in dict(getattr(runner, "_jobs", {}) or {}).items() if is_running(job)}
    by_workflow: dict[str, list[tuple[float, str]]] = {}
    for path in folder.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("id") and data["id"] not in live \
                and data.get("status") not in ("queued", "running"):
            by_workflow.setdefault(str(data.get("workflow")), []).append((float(data.get("started_at") or 0), path.name))
    deleted = 0
    for items in by_workflow.values():
        items.sort(reverse=True)  # newest first: the baseline (latest ready job) is always among the kept ones
        for _started, name in items[keep:]:
            try:
                (folder / name).unlink()
                deleted += 1
            except OSError:
                pass
    return deleted
