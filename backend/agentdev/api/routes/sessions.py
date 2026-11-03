import re
from typing import List, Optional
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from agentdev.api.services.session_review import VERDICTS, build_digest, clean_review
from agentdev.api.services.session_store import SessionStatus
from agentdev.api.settings import WARE_HOUSE_DIR
from agentdev.api.state import get_websocket_manager
from agentdev.utils.exceptions import ResourceNotFoundError, SecurityError, ValidationError
from agentdev.utils.structured_logger import get_server_logger, LogType
from agentdev.utils.workspace_paths import (
    is_link,
    iter_tree_without_links,
    resolve_workspace_path,
    session_directory_name,
)

router = APIRouter()

_SESSION_ID_RE = re.compile(r"^[a-zA-Z0-9_-]+$")
_ACTIVE_STATUSES = {SessionStatus.RUNNING, SessionStatus.WAITING_FOR_INPUT, SessionStatus.CANCELLING}


class SessionUpdateRequest(BaseModel):
    # Either field may be sent alone: rename, or switch a draft's workflow
    title: Optional[str] = Field(None, max_length=120)
    yaml_file: Optional[str] = Field(None, max_length=255)


def _require_session_id(session_id: str) -> None:
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=400, detail="Invalid session_id")


@router.get("/api/sessions")
async def list_sessions():
    """Every saved or live workflow session, newest first (for the session sidebar)."""
    store = get_websocket_manager().session_store
    return {"sessions": store.list_summaries()}


@router.patch("/api/sessions/{session_id}")
async def update_session(session_id: str, request: SessionUpdateRequest):
    _require_session_id(session_id)
    store = get_websocket_manager().session_store
    result = {"session_id": session_id}

    if request.yaml_file is not None:
        yaml_file = request.yaml_file.strip()
        if not yaml_file or "/" in yaml_file or "\\" in yaml_file or not yaml_file.lower().endswith((".yaml", ".yml")):
            raise HTTPException(status_code=400, detail="Invalid workflow file")
        session = store.restore_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        # A launched session keeps the workflow it ran with
        if session.status != SessionStatus.IDLE:
            raise HTTPException(status_code=409, detail="Only a session that has not been launched can change its workflow")
        session.yaml_file = yaml_file
        store.touch(session)
        result["yaml_file"] = yaml_file

    if request.title is not None:
        title = request.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Title cannot be empty")
        live = store.get_session(session_id)
        if live:
            live.title = title
        meta = store.history.rename(session_id, title) if store.history else None
        if not live and not meta:
            raise HTTPException(status_code=404, detail="Session not found")
        result["title"] = title

    if len(result) == 1:
        raise HTTPException(status_code=400, detail="Nothing to update")
    return result


class SessionReviewRequest(BaseModel):
    verdict: str = Field("pending", max_length=16)
    rating: int = Field(0, ge=0, le=5)
    tags: List[str] = Field(default_factory=list, max_length=12)
    feedback: str = Field("", max_length=4000)
    rework_session_id: Optional[str] = Field(None, max_length=120)


@router.get("/api/sessions/{session_id}/digest")
async def session_digest(session_id: str):
    """What a run delivered (task, each agent's hand-over, changed files, summary) for review."""
    _require_session_id(session_id)
    store = get_websocket_manager().session_store
    if not store.history or not store.history.has(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    messages = store.history.load_messages(session_id, 0)
    return {
        "session_id": session_id,
        "digest": build_digest(messages),
        "review": store.history.get_review(session_id),
    }


@router.put("/api/sessions/{session_id}/review")
async def save_session_review(session_id: str, request: SessionReviewRequest):
    """The user's final check of the delivered work: approve, or send it back with feedback."""
    _require_session_id(session_id)
    if request.verdict not in VERDICTS:
        raise HTTPException(status_code=400, detail="Invalid verdict")
    if request.rework_session_id and not _SESSION_ID_RE.match(request.rework_session_id):
        raise HTTPException(status_code=400, detail="Invalid rework_session_id")
    store = get_websocket_manager().session_store
    live = store.get_session(session_id)
    if live and live.status in _ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="The run is still in progress")
    if not store.history:
        raise HTTPException(status_code=404, detail="Session not found")
    review = clean_review(request.model_dump(), store.history.get_review(session_id))
    if not store.history.save_review(session_id, review):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "review": review}


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str):
    _require_session_id(session_id)
    store = get_websocket_manager().session_store
    live = store.get_session(session_id)
    if live and live.status in _ACTIVE_STATUSES:
        raise HTTPException(status_code=409, detail="Cancel the running workflow before deleting it")
    if not store.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "deleted": True}


@router.get("/api/sessions/{session_id}/download")
async def download_session(session_id: str):
    try:
        if not re.match(r"^[a-zA-Z0-9_-]+$", session_id):
            logger = get_server_logger()
            logger.log_security_event(
                "INVALID_SESSION_ID_FORMAT",
                f"Invalid session_id format: {session_id}",
                details={"received_session_id": session_id},
            )
            raise ValidationError(
                "Invalid session_id: only letters, digits, underscores, and hyphens are allowed",
                field="session_id",
            )

        dir_name = session_directory_name(session_id)
        session_path = resolve_workspace_path(WARE_HOUSE_DIR, dir_name)

        if not session_path.exists() or not session_path.is_dir():
            raise ResourceNotFoundError(
                "Session directory not found",
                resource_type="session",
                resource_id=session_id,
            )

        if is_link(WARE_HOUSE_DIR / dir_name):
            raise SecurityError("Session downloads must not follow symbolic links")
        entries = [session_path]
        for path in iter_tree_without_links(session_path):
            if is_link(path):
                continue
            if not path.resolve().is_relative_to(session_path):
                raise SecurityError("Session downloads must not follow symbolic links")
            if path.is_file() or path.is_dir():
                entries.append(path)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp_file:
            zip_path = Path(tmp_file.name)

        try:
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in entries:
                    archive.write(path, arcname=str(Path(dir_name) / path.relative_to(session_path)))
        except Exception as exc:
            if zip_path.exists():
                zip_path.unlink()
            logger = get_server_logger()
            logger.log_exception(exc, f"Failed to create zip archive for session: {session_id}")
            raise HTTPException(status_code=500, detail="Failed to create zip archive")

        logger = get_server_logger()
        logger.info(
            "Session download prepared",
            log_type=LogType.WORKFLOW,
            session_id=session_id,
            archive_path=str(zip_path),
        )

        def cleanup_zip():
            if zip_path.exists():
                zip_path.unlink()

        return FileResponse(
            path=zip_path,
            filename=f"{dir_name}.zip",
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={dir_name}.zip"},
            background=BackgroundTask(cleanup_zip),
        )
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except SecurityError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Session directory not found")
    except HTTPException:
        raise
    except Exception as exc:
        logger = get_server_logger()
        logger.log_exception(exc, f"Unexpected error during session download: {session_id}")
        raise HTTPException(status_code=500, detail="Failed to download session")
