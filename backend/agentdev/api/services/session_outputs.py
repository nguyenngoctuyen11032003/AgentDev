"""What a chat session (the Run page) produced: list, serve and open its files, and try its app.

A session writes its results to one folder (its *output location*):

- the project folder the user opened for the session (agents work in it in place), else
- the session's own ``storage/warehouse/session_<id>/code_workspace``.

This module gives that folder the same browsing / serving / "Chạy thử" the Lab gives a run, reusing the Lab's
helpers (``lab_outputs``) and preview manager (``app_preview``). All file access is confined to the folder: every
requested path is resolved and checked to stay inside it. The session folder must be a ``session_*`` child of
the warehouse (not a link). An opened project lives outside the warehouse, so its preview is started with that
folder as the explicitly allowed root, under a key of its own per session; the warehouse rule of the Lab is not
loosened. Nothing here deletes anything.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any, Callable

from agentdev.api.services import lab_outputs, product_archive
from agentdev.api.services.lab_outputs import LabOutputsError
from agentdev.utils.workspace_paths import is_link

# An opened project can be a large repository: stop walking after this many files (the totals then say "at
# least"). The listing itself shows at most lab_outputs.MAX_FILES.
MAX_SCAN = 20_000
SESSION_DIR_PREFIX = "session_"
PREVIEW_KEY_PREFIX = "session:"


def _default_session_lookup(session_id: str) -> Any:
    from agentdev.api.state import get_websocket_manager

    return get_websocket_manager().session_store.get_session(session_id)


# Replaced in tests; returns the live session object (or None when the server does not hold it).
session_lookup: Callable[[str], Any] = _default_session_lookup


def _session_dir_name(session_id: str) -> str:
    from agentdev.utils.exceptions import ValidationError
    from agentdev.utils.workspace_paths import session_directory_name

    try:
        return session_directory_name(session_id)
    except (ValidationError, ValueError) as exc:
        raise LabOutputsError(400, "Invalid session id") from exc


def output_location(session_id: str) -> dict[str, Any]:
    """``{"kind": "project"|"session", "root": Path}`` of where this session's results are written.

    Same rule as ``GET /api/sessions/{id}/output-location``: the opened project, else the session's workspace.
    The session folder is checked to be a direct ``session_*`` child of the warehouse that is not a link.
    """
    name = _session_dir_name(session_id)  # validates the id before anything else
    from agentdev.api.services.local_projects import opened_project_folder

    session = None
    with contextlib.suppress(Exception):
        session = session_lookup(session_id)
    project = opened_project_folder(session) if session is not None else None
    if project is not None:
        try:
            root = Path(project).resolve()
        except (OSError, ValueError) as exc:
            raise LabOutputsError(404, "The opened project folder is not available") from exc
        return {"kind": "project", "root": root}

    warehouse = lab_outputs.warehouse_root().resolve()
    session_dir = warehouse / name
    if is_link(session_dir):
        raise LabOutputsError(403, "The session folder is a link; refusing to follow it")
    root = session_dir / lab_outputs.CODE_WORKSPACE
    if is_link(root):
        raise LabOutputsError(403, "The session workspace is a link; refusing to follow it")
    resolved = root.resolve()
    if resolved.parent.parent != warehouse or not resolved.parent.name.startswith(SESSION_DIR_PREFIX):
        raise LabOutputsError(403, "The session workspace is outside the warehouse")
    return {"kind": "session", "root": resolved}


def session_dir_id(session_id: str) -> str:
    """``session_id`` once checked to be a valid id (raises LabOutputsError(400) otherwise)."""
    _session_dir_name(session_id)
    return session_id


def _existing_root(session_id: str) -> Path:
    root = output_location(session_id)["root"]
    if not root.is_dir():
        raise LabOutputsError(404, "Nothing has been written for this session yet")
    return root


# ----------------------------------------------------------------------------------- listing


# Inside the session workspace: what the user attached (inputs, not product) and where a project the user
# cloned into the session lives (``projects/<name>/``: the app to run is there, not at the root).
INPUT_DIRS = frozenset({"attachments"})
CLONED_PROJECTS = "projects"


def _hidden(kind: str) -> frozenset[str]:
    return INPUT_DIRS if kind == "session" else frozenset()


def app_dir(root: Path, kind: str) -> tuple[str, dict[str, Any]]:
    """(folder of the app relative to ``root``, its project info): ``root`` itself when it is runnable (or holds
    nothing runnable anywhere), else the first runnable ``projects/<name>/`` of a session workspace."""
    project = lab_outputs.detect_project(root)
    if project.get("can_preview") or kind != "session":
        return "", project
    cloned = root / CLONED_PROJECTS
    try:
        candidates = sorted((c for c in cloned.iterdir() if c.is_dir() and not is_link(c)), key=lambda c: c.name.lower())
    except OSError:
        candidates = []
    for candidate in candidates:
        found = lab_outputs.detect_project(candidate)
        if found.get("can_preview"):
            rel = f"{CLONED_PROJECTS}/{candidate.name}"
            return rel, {**found, "entry": f"{rel}/{found['entry']}" if found.get("entry") else rel}
    return "", project


def _with_dir(project: dict[str, Any], rel: str) -> dict[str, Any]:
    return {**project, "dir": rel}


def list_files(session_id: str) -> dict[str, Any]:
    location = output_location(session_id)
    root: Path = location["root"]
    if not root.is_dir():
        listing = lab_outputs.empty_listing(str(root))
    else:
        rel, project = app_dir(root, location["kind"])
        listing = lab_outputs.list_dir(root, max_scan=MAX_SCAN, hide_top=_hidden(location["kind"]),
                                       project=_with_dir(project, rel))
        product_archive.describe(listing, root)
    listing["location"] = location["kind"]
    return listing


def archive(session_id: str) -> tuple[Path, str]:
    """(temporary zip, download file name) of the session's product, without dependency folders or inputs."""
    location = output_location(session_id)
    root = _existing_root(session_id)
    top = product_archive.slug(product_archive.project_name(root))
    return product_archive.build_archive(root, top, hide_top=_hidden(location["kind"])), f"{top}.zip"


def summary(session_id: str) -> dict[str, Any]:
    """One line for the Run page: what the session made, and whether it can be run (and is running)."""
    location = output_location(session_id)
    root: Path = location["root"]
    if root.is_dir():
        rel, project = app_dir(root, location["kind"])
        data = lab_outputs.summarize_dir(root, max_scan=MAX_SCAN, hide_top=_hidden(location["kind"]),
                                         project=_with_dir(project, rel))
    else:
        data = {"available": False, "file_count": 0, "total_bytes": 0, "kinds": {},
                "project": _with_dir(lab_outputs.detect_project(root), ""), "scan_capped": False}
    data.update(location=location["kind"], root=str(root), preview=None)
    manager = _preview_manager()
    if manager is not None and data["project"].get("can_preview"):
        with contextlib.suppress(Exception):
            status = manager.status_key(preview_key(session_id))
            if status.get("status") in ("installing", "starting", "running"):
                data["preview"] = {k: status.get(k) for k in ("status", "url", "frameable")}
    return data


# ----------------------------------------------------------------------------------- one file


def file(session_id: str, relative_path: str) -> Path:
    return lab_outputs.viewer_file(_existing_root(session_id), relative_path)


def site_file(session_id: str, relative_path: str) -> Path:
    return lab_outputs.site_file_in(_existing_root(session_id), relative_path)


def open_target(session_id: str, relative_path: str) -> Path:
    """The file or folder to open on the machine (empty path = the output folder, created when missing)."""
    location = output_location(session_id)
    root: Path = location["root"]
    if not (relative_path or "").strip() and location["kind"] == "session":
        root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise LabOutputsError(404, "Nothing has been written for this session yet")
    return lab_outputs.resolve_product_file(root, relative_path, allow_dir=True)


# ----------------------------------------------------------------------------------- preview ("Chạy thử")


def preview_key(session_id: str) -> tuple[str, int]:
    return f"{PREVIEW_KEY_PREFIX}{session_id}", 0


def site_base(session_id: str) -> str:
    return f"/api/sessions/{session_id}/outputs/site/"


def _preview_manager() -> Any:
    try:
        from agentdev.api.services.app_preview import get_preview_manager

        return get_preview_manager()
    except Exception:  # noqa: BLE001 - previews are optional
        return None


def _refuse_broad_folder(root: Path) -> None:
    """Never run a dev server from a drive root or the home folder (an opened "project" can be anything)."""
    from agentdev.api.services.app_preview import PreviewError

    if root.parent == root or root == Path.home().resolve():
        raise PreviewError("Thư mục này quá rộng để chạy thử; hãy mở đúng thư mục dự án.", 403)


def preview_start(session_id: str) -> dict[str, Any]:
    from agentdev.api.services.app_preview import PreviewError, get_preview_manager

    try:
        location = output_location(session_id)
    except LabOutputsError as exc:
        raise PreviewError(exc.detail, exc.status_code) from exc
    root: Path = location["root"]
    if not root.is_dir():
        raise PreviewError("Phiên này chưa tạo file nào để chạy thử.", 404)
    allowed = None
    if location["kind"] == "project":
        _refuse_broad_folder(root)
        allowed = root  # checked above: the folder the user opened for this very session
    rel, _project = app_dir(root, location["kind"])
    app_root = lab_outputs.resolve_product_file(root, rel, allow_dir=True) if rel else root
    base = site_base(session_id) + (f"{rel}/" if rel else "")
    return get_preview_manager().start_dir(preview_key(session_id), app_root, base, allowed_root=allowed)


def preview_status(session_id: str) -> dict[str, Any]:
    from agentdev.api.services.app_preview import get_preview_manager

    _session_dir_name(session_id)

    def root_for() -> Path:
        location = output_location(session_id)
        rel, _project = app_dir(_existing_root(session_id), location["kind"])
        return location["root"] / rel if rel else location["root"]

    return get_preview_manager().status_key(preview_key(session_id), root_for)


def preview_stop(session_id: str) -> dict[str, Any]:
    from agentdev.api.services.app_preview import get_preview_manager

    _session_dir_name(session_id)
    return get_preview_manager().stop_key(preview_key(session_id))
