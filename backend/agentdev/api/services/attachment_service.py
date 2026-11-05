"""Attachment helpers shared by HTTP routes and executors."""

import logging
import mimetypes
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import UploadFile

from agentdev.paths import WAREHOUSE_DIR
from agentdev.entity.messages import MessageBlock, MessageBlockType
from agentdev.utils.attachments import AttachmentStore, AttachmentRecord
from agentdev.api.services.repo_map import render_overview_tree
from agentdev.utils.exceptions import SecurityError, ValidationError
from agentdev.utils.workspace_paths import (
    is_link,
    iter_tree_without_links,
    resolve_workspace_path,
    session_directory_name,
    validate_path_component,
)

# Uploaded project folders live in ``<session>/code_workspace/projects/<project_id>/``
# so agents can read *and* edit them with the regular file tools (unlike
# ``attachments/``, which is read-only for tools).
PROJECTS_DIRNAME = "projects"

# Dependency / build / VCS folders that are never worth sending to an agent.
# The web UI filters these before uploading; the backend enforces it again.
IGNORED_PROJECT_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", "node_modules", "bower_components", ".venv", "venv",
        "env", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
        "dist", "build", "out", ".next", ".nuxt", ".svelte-kit", ".turbo", ".parcel-cache",
        ".cache", "coverage", ".gradle", ".idea", "target", "Pods", "DerivedData",
    }
)
IGNORED_PROJECT_FILES = frozenset({".DS_Store", "Thumbs.db", "desktop.ini"})

_PROJECT_FAILED_REPORT_LIMIT = 20

# The project overview goes into the lead's prompt (and is re-read by every model call of its loop),
# so its folder tree is a map, not an inventory: at most this many lines, folders first, big or
# media-only folders summarised in one line, and deeper levels folded when the tree is too big.
_OVERVIEW_TREE_LINES = 160
_OVERVIEW_DIR_FILES = 15
_OVERVIEW_MAX_DEPTH = 6
_MEDIA_EXTS = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".bmp", ".ico", ".svg", ".tif", ".tiff",
        ".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".mp4", ".mov", ".webm", ".mkv",
        ".glb", ".gltf", ".fbx", ".obj", ".ktx2", ".hdr", ".exr", ".woff", ".woff2", ".ttf", ".otf",
        ".pdf", ".zip", ".sha256",
    }
)


def _ext_summary(names: List[str], top: int = 3) -> str:
    counts: Dict[str, int] = {}
    for name in names:
        ext = Path(name).suffix.lower() or "no ext"
        counts[ext] = counts.get(ext, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    parts = [f"{count} {ext}" for ext, count in ranked[:top]]
    if len(ranked) > top:
        parts.append(f"{sum(count for _, count in ranked[top:])} other")
    return ", ".join(parts)


def _count(n: int) -> str:
    return f"{n} file" if n == 1 else f"{n} files"


def render_project_tree(relative_files: List[str], *, max_lines: int = _OVERVIEW_TREE_LINES) -> List[str]:
    """Indented folder tree of ``relative_files`` (POSIX paths) that fits in ``max_lines``.

    Folders come before files so the structure (``src/``, ``app/``...) is visible even in a huge
    project; a folder with many files lists a few and counts the rest; a folder holding only media
    is one line; when the tree is still too big, deeper levels are folded into ``name/ (N files)``.
    """
    tree: Dict[str, Any] = {}
    for rel in relative_files:
        parts = [part for part in rel.split("/") if part]
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part + "/", {})
        if parts:
            node[parts[-1]] = None

    def all_files(node: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        for name, child in node.items():
            out.extend(all_files(child) if isinstance(child, dict) else [name])
        return out

    def render(node: Dict[str, Any], depth: int, fold_depth: int) -> List[str]:
        lines: List[str] = []
        indent = "  " * depth
        dirs = sorted((k for k, v in node.items() if isinstance(v, dict)), key=str.lower)
        files = sorted((k for k, v in node.items() if v is None), key=str.lower)
        if len(dirs) > _OVERVIEW_DIR_FILES:
            hidden = dirs[_OVERVIEW_DIR_FILES - 5 :]
            dirs = dirs[: _OVERVIEW_DIR_FILES - 5]
        else:
            hidden = []
        for name in dirs:
            child = node[name]
            inner = all_files(child)
            media_only = bool(inner) and all(Path(f).suffix.lower() in _MEDIA_EXTS for f in inner)
            if depth + 1 >= fold_depth or media_only:
                lines.append(f"{indent}{name} ({_count(len(inner))}: {_ext_summary(inner)})" if inner else f"{indent}{name}")
            else:
                lines.append(f"{indent}{name}")
                lines.extend(render(child, depth + 1, fold_depth))
        if hidden:
            inner = [f for name in hidden for f in all_files(node[name])]
            lines.append(f"{indent}... +{len(hidden)} more folders ({_count(len(inner))})")
        shown = files if len(files) <= _OVERVIEW_DIR_FILES else files[: _OVERVIEW_DIR_FILES - 5]
        lines.extend(f"{indent}{name}" for name in shown)
        if len(shown) < len(files):
            rest = files[len(shown):]
            lines.append(f"{indent}... +{len(rest)} more files ({_ext_summary(rest)})")
        return lines

    lines: List[str] = []
    for fold_depth in range(_OVERVIEW_MAX_DEPTH, 0, -1):
        lines = render(tree, 0, fold_depth)
        if len(lines) <= max_lines:
            return lines
    total = len(relative_files)
    return lines[: max_lines - 1] + [f"... (tree cut; {total} files in total, list folders with the file tools)"]


def _fs_path(path: Path) -> Path:
    """Return a path usable for file I/O beyond Windows' 260-char MAX_PATH.

    Uploaded projects are nested under ``<warehouse>/session_<uuid>/code_workspace/
    projects/<id>/`` (~150 chars before the project's own relative path), so deep
    source trees easily exceed MAX_PATH when long-path support is disabled in the
    OS. The ``\\\\?\\`` extended-length prefix lifts that limit; elsewhere this is
    a no-op.
    """
    if os.name != "nt":
        return path
    text = os.path.abspath(path)
    if text.startswith("\\\\?\\"):
        return Path(text)
    if text.startswith("\\\\"):
        return Path("\\\\?\\UNC\\" + text[2:])
    return Path("\\\\?\\" + text)


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


class AttachmentService:
    """Handles attachment lifecycle per session."""

    def __init__(self, *, root: Path | str | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        # Resolved at call time (not as a default arg) so the module-level
        # ``WAREHOUSE_DIR`` can be redirected, e.g. by tests.
        self.attachments_root = Path(root) if root is not None else WAREHOUSE_DIR
        self.attachments_root.mkdir(parents=True, exist_ok=True)
        env_flag = os.environ.get("MAC_AUTO_CLEAN_ATTACHMENTS", "0").strip().lower()
        self.clean_on_cleanup = env_flag in {"1", "true", "yes"}
        self.max_project_files = _env_int("MAC_PROJECT_MAX_FILES", 5000)
        self.max_project_bytes = _env_int("MAC_PROJECT_MAX_MB", 300) * 1024 * 1024
        # Opening in place copies nothing; the cap only stops a whole drive being picked by mistake.
        self.max_open_folder_files = _env_int("MAC_OPEN_FOLDER_MAX_FILES", 50000)

    def prepare_session_workspace(self, session_id: str) -> Path:
        return self._session_attachments_path(session_id, create=True)

    def cleanup_session(self, session_id: str) -> None:
        attachment_dir = self._session_attachments_path(session_id, create=False)
        if not attachment_dir:
            return
        if self.clean_on_cleanup:
            shutil.rmtree(attachment_dir, ignore_errors=True)
            self.logger.info("Cleaned attachment directory for session %s", session_id)
        else:
            self.logger.info(
                "Attachment cleanup disabled; preserved files for session %s", session_id
            )

    def get_attachment_store(self, session_id: str) -> AttachmentStore:
        path = self.prepare_session_workspace(session_id)
        return AttachmentStore(path)

    @staticmethod
    def _safe_upload_filename(raw: Optional[str]) -> str:
        """Reduce a client-supplied upload filename to a safe basename.

        The multipart ``filename`` is attacker-controlled. Joining it onto the
        temporary upload directory verbatim allows path traversal (e.g.
        ``../../../etc/cron.d/x``): the write target escapes the temp dir and the
        cleanup step then unlinks the same traversed path, yielding arbitrary
        file write and delete. Normalise both POSIX and Windows separators and
        keep only the final path component so the write stays confined.
        """
        candidate = os.path.basename((raw or "").replace("\\", "/")).strip()
        if not candidate or candidate in {".", ".."}:
            return "upload.bin"
        return candidate

    async def save_upload_file(self, session_id: str, upload: UploadFile) -> AttachmentRecord:
        self._session_attachments_path(session_id, create=False)
        filename = self._safe_upload_filename(upload.filename)
        temp_dir = Path(tempfile.mkdtemp(prefix="mac_upload_"))
        temp_path = temp_dir / filename
        try:
            with temp_path.open("wb") as buffer:
                while True:
                    chunk = await upload.read(1024 * 1024)
                    if not chunk:
                        break
                    buffer.write(chunk)
            store = self.get_attachment_store(session_id)
            mime_type = upload.content_type or mimetypes.guess_type(filename)[0]
            record = store.register_file(
                temp_path,
                kind=MessageBlockType.from_mime_type(mime_type),
                display_name=filename,
                mime_type=mime_type,
                extra={
                    "source": "user_upload",
                    "origin": "web_upload",
                    "session_id": session_id,
                },
            )
            return record
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            try:
                temp_dir.rmdir()
            except OSError:
                pass

    def build_attachment_blocks(
        self,
        session_id: str,
        attachment_ids: List[str],
        *,
        target_store: Optional[AttachmentStore] = None,
    ) -> List[MessageBlock]:
        if not attachment_ids:
            return []
        source_store = self.get_attachment_store(session_id)
        source_root = source_store.root.resolve()
        target_root = target_store.root.resolve() if target_store else None
        blocks: List[MessageBlock] = []
        for attachment_id in attachment_ids:
            record = source_store.get(attachment_id)
            if not record:
                continue
            if target_store:
                copy_required = target_root != source_root
                record = target_store.ingest_record(record, copy_file=copy_required)
            blocks.append(record.as_message_block())
        return blocks

    def list_attachment_manifests(self, session_id: str) -> Dict[str, Any]:
        store = self.get_attachment_store(session_id)
        return store.export_manifest()

    def resolve_uploaded_paths(self, session_id: str, attachments: List[str]) -> List[str]:
        """Accept only registered uploads belonging to the specified session."""
        root = self._session_attachments_path(session_id, create=False)
        if root is None:
            raise SecurityError("Attachment upload session does not exist")
        manifest = root / "attachments_manifest.json"
        if is_link(manifest):
            raise SecurityError("Attachment manifest must not be a symbolic link")
        store = AttachmentStore(root)
        uploaded = {}
        for attachment_id in store.export_manifest():
            record = store.get(attachment_id)
            if (
                record.extra.get("origin") == "web_upload"
                and record.extra.get("session_id") == session_id
                and record.ref.local_path
            ):
                uploaded[attachment_id] = Path(record.ref.local_path)

        paths = []
        for value in attachments:
            try:
                source = uploaded.get(value)
                if source is None:
                    requested = Path(value).expanduser().resolve()
                    source = next((path for path in uploaded.values() if path.resolve() == requested), None)
                if source is None:
                    raise SecurityError("Attachment must reference a registered upload in attachment_session_id")
                resolved = source.resolve()
                if is_link(source) or not resolved.is_relative_to(root) or not resolved.is_file():
                    raise SecurityError("Attachment source must stay inside its upload session")
                paths.append(str(resolved))
            except (OSError, RuntimeError, ValueError) as exc:
                raise SecurityError("Invalid uploaded attachment source") from exc
        return paths

    # ------------------------------------------------------------------
    # Project (folder) uploads
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_project_name(raw: Optional[str]) -> str:
        """Turn a client folder name into one safe directory name."""
        name = os.path.basename((raw or "").replace("\\", "/").rstrip("/")).strip()
        name = "-".join(name.split())  # no spaces: easier paths for agents and tools
        name = "".join(ch if (ch.isalnum() or ch in "-_.") else "_" for ch in name).strip(".")
        return (name or "project")[:80]

    @staticmethod
    def _safe_project_relative_path(raw: Optional[str]) -> Optional[Path]:
        """Validate a client-supplied relative path inside a project.

        Returns ``None`` for entries that should be skipped (ignored folders /
        OS junk). Raises ``ValidationError`` for anything that could escape the
        project root (absolute paths, drive prefixes, ``..``).
        """
        normalized = (raw or "").replace("\\", "/").strip()
        if not normalized or normalized.startswith("/"):
            raise ValidationError("Project file path must be relative", field="paths")
        parts = [part for part in normalized.split("/") if part not in {"", "."}]
        if not parts:
            raise ValidationError("Project file path is empty", field="paths")
        for part in parts:
            if part == ".." or ":" in part or any(ord(ch) < 32 for ch in part):
                raise ValidationError(f"Invalid project file path: {raw}", field="paths")
        if any(part in IGNORED_PROJECT_DIRS for part in parts[:-1]) or parts[-1] in IGNORED_PROJECT_FILES:
            return None
        return Path(*parts)

    def _session_workspace_path(self, session_id: str) -> Path:
        session_dir_name = session_directory_name(session_id)
        current = self.attachments_root
        for part in (session_dir_name, "code_workspace"):
            current = current / part
            if is_link(current):
                raise ValidationError("Upload session paths must not contain symbolic links", field="session_id")
        path = resolve_workspace_path(self.attachments_root, session_dir_name, "code_workspace")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _projects_root(self, session_id: str) -> Path:
        root = self._session_workspace_path(session_id) / PROJECTS_DIRNAME
        if is_link(root):
            raise ValidationError("Projects directory must not be a symbolic link", field="project_id")
        root.mkdir(parents=True, exist_ok=True)
        return root

    def _project_root(self, session_id: str, project_id: str) -> Path:
        validate_path_component(project_id, field="project_id")
        projects_root = self._projects_root(session_id)
        path = projects_root / project_id
        if is_link(path) or not path.is_dir():
            raise ValidationError("Unknown project upload", field="project_id")
        return path

    def create_project(self, session_id: str, name: Optional[str]) -> Dict[str, Any]:
        """Reserve a fresh ``projects/<id>/`` folder for an upload."""
        projects_root = self._projects_root(session_id)
        base = self._safe_project_name(name)
        candidate, counter = base, 2
        while (projects_root / candidate).exists():
            candidate = f"{base}_{counter}"
            counter += 1
        (projects_root / candidate).mkdir()
        return {"project_id": candidate, "workspace_path": f"{PROJECTS_DIRNAME}/{candidate}"}

    @staticmethod
    def _project_usage(project_root: Path) -> tuple[int, int]:
        count = size = 0
        for path in iter_tree_without_links(project_root):
            if path.is_file() and not is_link(path):
                count += 1
                size += path.stat().st_size
        return count, size

    async def save_project_files(
        self,
        session_id: str,
        project_id: str,
        files: List[UploadFile],
        paths: List[str],
    ) -> Dict[str, Any]:
        """Store one batch of files, keeping their folder structure."""
        if len(files) != len(paths):
            raise ValidationError("Each uploaded file needs exactly one relative path", field="paths")
        project_root = _fs_path(self._project_root(session_id, project_id))
        resolved_root = project_root.resolve()
        file_count, total_size = self._project_usage(project_root)

        saved = skipped = 0
        failed: List[str] = []
        for upload, raw_path in zip(files, paths):
            relative = self._safe_project_relative_path(raw_path)
            if relative is None:
                skipped += 1
                continue
            if file_count + 1 > self.max_project_files:
                raise ValidationError(
                    f"Project exceeds the limit of {self.max_project_files} files", field="files"
                )
            target = project_root / relative
            # Every existing ancestor must be a real directory inside the project.
            for ancestor in [target, *target.parents]:
                if ancestor == project_root:
                    break
                if is_link(ancestor):
                    raise ValidationError("Project paths must not contain symbolic links", field="paths")
            written = 0
            replaced = 0
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.parent.resolve().is_relative_to(resolved_root):
                    raise ValidationError("Project file path escapes the project folder", field="paths")
                replaced = target.stat().st_size if target.is_file() else 0
                with target.open("wb") as buffer:
                    while True:
                        chunk = await upload.read(1024 * 1024)
                        if not chunk:
                            break
                        written += len(chunk)
                        if total_size - replaced + written > self.max_project_bytes:
                            raise ValidationError(
                                f"Project exceeds the size limit of {self.max_project_bytes // (1024 * 1024)} MB",
                                field="files",
                            )
                        buffer.write(chunk)
            except ValidationError:
                target.unlink(missing_ok=True)
                raise
            except OSError as exc:
                # One unwritable file (locked, reserved name such as "con", ...)
                # must not abort the whole project; report it back instead.
                self.logger.warning("Skipped project file %s: %s", relative.as_posix(), exc)
                try:
                    target.unlink(missing_ok=True)
                except OSError:
                    pass
                if replaced:
                    file_count -= 1
                    total_size -= replaced
                failed.append(relative.as_posix())
                continue
            total_size += written - replaced
            if not replaced:
                file_count += 1
            saved += 1

        return {
            "saved": saved,
            "skipped": skipped,
            "failed": len(failed),
            "failed_paths": failed[:_PROJECT_FAILED_REPORT_LIMIT],
            "file_count": file_count,
            "total_size": total_size,
        }

    def clone_project(
        self, source_session_id: str, source_project_id: str, target_session_id: str
    ) -> AttachmentRecord:
        """Copy a project folder from an earlier session into another session.

        Used for "new session in this project": the new session starts from the
        project's latest state (including edits the agent made earlier) without the
        user having to pick and upload the folder again.
        """
        validate_path_component(source_session_id, field="source_session_id")
        validate_path_component(source_project_id, field="project_id")
        if source_session_id == target_session_id:
            raise ValidationError("Source and target session must differ", field="source_session_id")
        source_dir = (
            self.attachments_root
            / session_directory_name(source_session_id)
            / "code_workspace"
            / PROJECTS_DIRNAME
            / source_project_id
        )
        for ancestor in [source_dir, *source_dir.parents]:
            if ancestor == self.attachments_root:
                break
            if is_link(ancestor):
                raise ValidationError("Project paths must not contain symbolic links", field="project_id")
        if not source_dir.is_dir():
            raise ValidationError("The project no longer exists in that session", field="project_id")
        source_root = _fs_path(self._project_root(source_session_id, source_project_id))

        created = self.create_project(target_session_id, source_project_id)
        target_root = _fs_path(self._project_root(target_session_id, created["project_id"]))
        resolved_source = source_root.resolve()
        file_count = total_size = 0
        for path in iter_tree_without_links(source_root):
            if is_link(path) or not path.is_file():
                continue
            relative = path.relative_to(source_root)
            if any(part in IGNORED_PROJECT_DIRS for part in relative.parts[:-1]):
                continue
            if not path.resolve().is_relative_to(resolved_source):
                continue
            file_count += 1
            total_size += path.stat().st_size
            if file_count > self.max_project_files or total_size > self.max_project_bytes:
                shutil.rmtree(target_root, ignore_errors=True)
                raise ValidationError("Project exceeds the upload limits", field="project_id")
            target = target_root / relative
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
            except OSError as exc:
                self.logger.warning("Skipped project file %s while cloning: %s", relative.as_posix(), exc)
        if file_count == 0:
            shutil.rmtree(target_root, ignore_errors=True)
            raise ValidationError("The project in that session has no files", field="project_id")
        return self.finalize_project(target_session_id, created["project_id"])

    def finalize_project(self, session_id: str, project_id: str) -> AttachmentRecord:
        """Register a Markdown overview of the uploaded project as an attachment.

        The agent receives this overview (folder tree + workspace location)
        instead of every file; it then reads/edits the real files with the file
        tools under ``projects/<project_id>/``.
        """
        project_root = _fs_path(self._project_root(session_id, project_id))
        workspace_path = f"{PROJECTS_DIRNAME}/{project_id}"
        file_count, total_size = self._project_usage(project_root)
        if file_count == 0:
            raise ValidationError("Project upload contains no files", field="project_id")

        project_entries = [
            (path, path.relative_to(project_root).as_posix())
            for path in iter_tree_without_links(project_root)
            if not is_link(path) and path.is_file()
        ]
        tree_heading, tree_lines = render_overview_tree(
            project_entries, render_project_tree([rel for _path, rel in project_entries])
        )

        size_mb = total_size / (1024 * 1024)
        overview = "\n".join(
            [
                f"# Project: {project_id}",
                "",
                "The user attached a whole project folder. It is available in your code workspace at:",
                "",
                f"    {workspace_path}/",
                "",
                f"- Files: {file_count} ({size_mb:.2f} MB)",
                "- Use the file tools (list_directory, read_text_file_snippet, read_file_segment, "
                "save_file, apply_text_edits, ...) with paths relative to the code workspace, "
                f"e.g. `{workspace_path}/README.md`.",
                "- Dependency/build folders (node_modules, .git, dist, build, .venv, ...) were not uploaded.",
                "",
                f"## {tree_heading}",
                "",
                "```",
                f"{project_id}/",
                *("  " + line for line in tree_lines),
                "```",
                "",
            ]
        )

        return self._register_overview(
            session_id,
            overview,
            display_name=f"{project_id}/",
            extra={
                "source": "user_upload",
                "origin": "web_upload",
                "session_id": session_id,
                "kind": "project",
                "project_id": project_id,
                "workspace_path": workspace_path,
                "file_count": file_count,
                "total_size": total_size,
            },
        )

    def _register_overview(
        self, session_id: str, overview: str, *, display_name: str, extra: Dict[str, Any]
    ) -> AttachmentRecord:
        temp_dir = Path(tempfile.mkdtemp(prefix="mac_project_"))
        # Short fixed name: the stored copy lives under attachments/<32-hex id>/,
        # and long names push Windows paths past MAX_PATH (260).
        temp_path = temp_dir / "PROJECT.md"
        try:
            temp_path.write_text(overview, encoding="utf-8")
            store = self.get_attachment_store(session_id)
            return store.register_file(
                temp_path,
                kind=MessageBlockType.FILE,
                display_name=display_name,
                mime_type="text/markdown",
                extra=extra,
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def open_local_project(self, session_id: str, folder: str, *, current_folder: Optional[str] = None) -> AttachmentRecord:
        """Open a folder on this machine in place, like "Open Folder" in an editor.

        Nothing is copied: the run uses the folder itself as the agents' code workspace,
        so their edits land in the real project. The agent receives a Markdown overview.
        """
        from agentdev.api.services.local_projects import scan_project

        scan = scan_project(
            folder,
            ignored_dirs=IGNORED_PROJECT_DIRS,
            ignored_files=IGNORED_PROJECT_FILES,
            max_files=self.max_open_folder_files,
        )
        root = scan.root
        if current_folder and Path(current_folder).resolve() != root:
            raise ValidationError(
                "This session already has a project folder open; start a new session for another folder",
                field="path",
            )
        total_size = 0
        for path, _rel in scan.files:
            try:
                total_size += path.stat().st_size
            except OSError:
                pass

        tree_heading, tree_lines = render_overview_tree(
            list(scan.files), render_project_tree([rel for _path, rel in scan.files])
        )

        name = root.name or str(root)
        size_mb = total_size / (1024 * 1024)
        overview = "\n".join(
            [
                f"# Project: {name}",
                "",
                "The user opened this project folder for you to work on. Your code workspace IS the",
                "project root, so every change you make is saved directly in the user's project.",
                "",
                f"- Files: {len(scan.files)} ({size_mb:.2f} MB)",
                "- Use the file tools (list_directory, read_file_segment, save_file, apply_text_edits, ...)",
                "  with paths relative to the project root, e.g. `README.md` or `src/main.py`.",
                f"  Do NOT prefix paths with the folder name (`{name}/...` does not exist); list the",
                "  root with `.` and use the tree below as paths from the root.",
                "- Change only what the task needs; do not delete or rewrite unrelated files.",
                "- Dependency/build folders (node_modules, .git, dist, build, .venv, ...) and",
                "  .gitignore'd files are left out of this overview.",
                "",
                f"## {tree_heading}",
                "",
                "```",
                f"./  (project root, the folder named {name})",
                *("  " + line for line in tree_lines),
                "```",
                "",
                *(
                    [
                        "The folder is currently empty: this is a brand-new project.",
                        "Build it from scratch by creating the files and folders the task needs.",
                        "",
                    ]
                    if not scan.files
                    else []
                ),
            ]
        )
        return self._register_overview(
            session_id,
            overview,
            display_name=f"{name}/",
            extra={
                "source": "local_folder",
                "origin": "local_folder",
                "session_id": session_id,
                "kind": "project",
                "project_id": name,
                "workspace_path": ".",
                "local_path": str(root),
                "file_count": len(scan.files),
                "total_size": total_size,
                "skipped": scan.skipped + scan.gitignored,
            },
        )

    def _session_attachments_path(self, session_id: str, *, create: bool = True) -> Optional[Path]:
        session_dir_name = session_directory_name(session_id)
        current = self.attachments_root
        for part in (session_dir_name, "code_workspace", "attachments"):
            current = current / part
            if is_link(current):
                raise ValidationError("Upload session paths must not contain symbolic links", field="session_id")
        path = resolve_workspace_path(
            self.attachments_root, session_dir_name, "code_workspace", "attachments"
        )
        if create:
            path.mkdir(parents=True, exist_ok=True)
            return path
        return path if path.exists() else None
