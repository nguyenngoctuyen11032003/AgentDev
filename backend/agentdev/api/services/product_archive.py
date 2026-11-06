"""A product folder as the user sees it: its project name and a downloadable .zip.

The name heads the file tree of "Sản phẩm" (like a code editor's explorer). The archive holds what the agents
made, never what can be re-installed or must stay on this machine: dependency and tooling folders
(``node_modules``, ``.venv``, ``.git``, caches: see ``lab_outputs.SKIP_DIR_NAMES``), the engine's own log files,
input folders the caller hides, and real ``.env`` files (they may hold secrets; ``.env.example`` is kept).
"""

from __future__ import annotations

import json
import re
import tempfile
import unicodedata
import zipfile
from pathlib import Path

from agentdev.api.services import lab_outputs

NAME_MAX = 60
# Folder names that say nothing about the project (AgentDev's own workspace folders).
_GENERIC_DIRS = re.compile(r"^(code_workspace|workspace|session_.*|lab_.*|output|outputs|src|app)$", re.IGNORECASE)
# package.json names a scaffold leaves behind.
_GENERIC_PACKAGES = re.compile(r"^(@[\w-]+/)?(app|my-app|vite-project|client|server|frontend|backend|web|api|root|"
                               r"project|demo|test)$", re.IGNORECASE)
_HEADING = re.compile(r"^#\s+(.+?)\s*#*\s*$", re.MULTILINE)
_TITLE = re.compile(r"<title[^>]*>\s*([^<]{1,200}?)\s*</title>", re.IGNORECASE)
_HTML_DIRS = ("", "client", "frontend", "web", "public", "site")
_SECRET_FILE = re.compile(r"^\.env(\..+)?$", re.IGNORECASE)
_SAFE_ENV = re.compile(r"^\.env\.(example|sample|template|dist)$", re.IGNORECASE)


def _read(path: Path, limit: int = 64 * 1024) -> str:
    try:
        with open(path, "rb") as handle:
            return handle.read(limit).decode("utf-8", errors="ignore")
    except OSError:
        return ""


def _clean(text: str) -> str:
    text = re.sub(r"[`*_\[\]]", "", text or "").strip()
    return text[:NAME_MAX].strip()


def _readme_title(root: Path) -> str:
    for name in ("README.md", "readme.md", "Readme.md"):
        match = _HEADING.search(_read(root / name))
        if match:
            return _clean(match.group(1))
    return ""


def _package_name(root: Path) -> str:
    try:
        data = json.loads(_read(root / "package.json") or "{}")
    except ValueError:
        return ""
    name = data.get("name") if isinstance(data, dict) else None
    if isinstance(name, str) and name.strip() and not _GENERIC_PACKAGES.match(name.strip()):
        return _clean(name)
    return ""


def _html_title(root: Path) -> str:
    for folder in _HTML_DIRS:
        match = _TITLE.search(_read(root / folder / "index.html"))
        if match and match.group(1).strip():
            return _clean(match.group(1))
    return ""


def project_name(root: Path) -> str:
    """A short human name for the product folder: the folder's own name when it is a real project folder, else
    the root README title, package.json name, or the web page title. Empty when nothing names it."""
    root = Path(root)
    if root.name and not _GENERIC_DIRS.match(root.name):
        return _clean(root.name)
    for finder in (_readme_title, _package_name, _html_title):
        name = finder(root)
        if name:
            return name
    return ""


def slug(name: str, fallback: str = "san-pham") -> str:
    """ASCII file-name form of ``name`` ("Quản lý cửa hàng" -> "quan-ly-cua-hang")."""
    text = (name or "").replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return text[:NAME_MAX].strip("-") or fallback


def archived(rel: str, *, is_graph_dir: bool = False, hide_top: frozenset[str] = frozenset()) -> bool:
    """Whether the product file ``rel`` (from ``lab_outputs._walk``, which already skips tooling folders) goes
    into the archive."""
    name = rel.rsplit("/", 1)[-1]
    if _SECRET_FILE.match(name) and not _SAFE_ENV.match(name):
        return False
    if hide_top and rel.split("/", 1)[0] in hide_top:
        return False
    return not lab_outputs._is_internal(rel, is_graph_dir)


def build_archive(root: Path, top: str, *, is_graph_dir: bool = False,
                  hide_top: frozenset[str] = frozenset()) -> Path:
    """Zip the product under ``root`` into a temporary file (the caller deletes it), every entry inside the
    folder ``top/``. Raises ``LabOutputsError(404)`` when there is nothing to put in it."""
    root = Path(root)
    if not root.is_dir():
        raise lab_outputs.LabOutputsError(404, "The product folder no longer exists", "lab_outputs_gone")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as handle:
        target = Path(handle.name)
    count = 0
    try:
        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for rel, _size in lab_outputs._walk(root):
                if not archived(rel, is_graph_dir=is_graph_dir, hide_top=hide_top):
                    continue
                try:
                    archive.write(root / rel, arcname=f"{top}/{rel}")
                except OSError:
                    continue  # vanished or locked while zipping: leave it out
                count += 1
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    if not count:
        target.unlink(missing_ok=True)
        raise lab_outputs.LabOutputsError(404, "The product folder has no files to download", "lab_archive_empty")
    return target


def describe(listing: dict, root: Path, answer: str = "") -> dict:
    """Add the product's ``name`` and ``login`` (demo account of an app behind a login, see lab_login) to a
    file listing of ``root``."""
    from agentdev.api.services.lab_login import login_info

    listing["name"] = project_name(root) if listing.get("available") else ""
    try:
        listing["login"] = login_info(answer, root) if listing.get("available") else None
    except Exception:  # noqa: BLE001 - a scan problem must not break the file list
        listing["login"] = None
    return listing


def lab_run_archive(job_id: str, run: lab_outputs.RunRef) -> tuple[Path, str]:
    """(temporary zip, download file name) of one Lab run's product."""
    run_dir = lab_outputs.resolve_run_dir(job_id, run)
    if run_dir is None or not run_dir.is_dir():
        raise lab_outputs.LabOutputsError(404, "The product folder no longer exists", "lab_outputs_gone")
    root = lab_outputs.product_dir(run_dir)
    top = slug(project_name(root))
    return build_archive(root, top, is_graph_dir=root == run_dir), f"{top}.zip"


def archive_response(path: Path, filename: str):
    """Send a temporary zip and delete it once sent."""
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    return FileResponse(path, filename=filename, media_type="application/zip",
                        background=BackgroundTask(path.unlink, missing_ok=True))
