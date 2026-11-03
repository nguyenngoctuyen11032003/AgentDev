import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from agentdev.api.services.local_projects import opened_project_folder
from agentdev.api.state import ensure_known_session, get_websocket_manager
from agentdev.connections.security import require_local_origin
from agentdev.utils.exceptions import ValidationError
from agentdev.utils.structured_logger import get_server_logger, LogType

router = APIRouter()

@router.post("/api/uploads/{session_id}")
async def upload_attachment(session_id: str, file: UploadFile = File(...)):
    try:
        manager = ensure_known_session(session_id, require_connection=False)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    try:
        record = await manager.attachment_service.save_upload_file(session_id, file)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger = get_server_logger()
        logger.error(
            "Failed to save attachment",
            log_type=LogType.REQUEST,
            session_id=session_id,
            error=str(exc),
        )
        raise HTTPException(status_code=500, detail="Failed to store attachment")

    ref = record.ref
    return {
        "attachment_id": ref.attachment_id,
        "name": ref.name,
        "mime_type": ref.mime_type,
        "size": ref.size,
    }


@router.get("/api/uploads/{session_id}")
async def list_attachments(session_id: str):
    try:
        manager = ensure_known_session(session_id, require_connection=False)
        manifest = manager.attachment_service.list_attachment_manifests(session_id)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"attachments": manifest}


# ----------------------------------------------------------------------------
# Project (whole folder) uploads
#
# 1. POST /api/uploads/{sid}/projects                      {"name": "my-app"}
# 2. POST /api/uploads/{sid}/projects/{project_id}/files   multipart: files[] + paths[]
#    (repeat in batches; paths are relative to the project root)
# 3. POST /api/uploads/{sid}/projects/{project_id}/finalize
#    -> registers a Markdown overview as an attachment the agent receives;
#       the files themselves stay editable in code_workspace/projects/<id>/.
# ----------------------------------------------------------------------------


class CreateProjectRequest(BaseModel):
    name: Optional[str] = None


class FinalizeProjectRequest(BaseModel):
    # Workflow the session is using, so a draft session created here can be reopened
    yaml_file: Optional[str] = None


def _attachment_service(session_id: str):
    try:
        manager = ensure_known_session(session_id, require_connection=False)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return manager.attachment_service


def _project_failure(session_id: str, action: str, exc: Exception) -> HTTPException:
    if isinstance(exc, ValidationError):
        return HTTPException(status_code=400, detail=str(exc))
    get_server_logger().error(
        f"Failed to {action} project upload",
        log_type=LogType.REQUEST,
        session_id=session_id,
        error=str(exc),
    )
    return HTTPException(status_code=500, detail=f"Failed to {action} project upload")


@router.post("/api/uploads/{session_id}/projects")
async def create_project_upload(session_id: str, payload: CreateProjectRequest):
    service = _attachment_service(session_id)
    try:
        return service.create_project(session_id, payload.name)
    except Exception as exc:
        raise _project_failure(session_id, "create", exc)


class CloneProjectRequest(BaseModel):
    source_session_id: str
    project_id: str
    yaml_file: Optional[str] = None


def _register_project(session_id: str, yaml_file: Optional[str], record) -> dict:
    """List the session under its project (even as a draft) and describe the attachment."""
    ref = record.ref
    get_websocket_manager().session_store.register_project(
        session_id,
        yaml_file,
        {
            "name": (ref.name or record.extra.get("project_id") or "").rstrip("/"),
            "attachment_id": ref.attachment_id,
            "project_id": record.extra.get("project_id"),
            "workspace_path": record.extra.get("workspace_path"),
            "local_path": record.extra.get("local_path"),
            "file_count": record.extra.get("file_count"),
        },
    )
    return {
        "attachment_id": ref.attachment_id,
        "name": ref.name,
        "mime_type": ref.mime_type,
        "size": ref.size,
        "kind": "project",
        "project_id": record.extra.get("project_id"),
        "workspace_path": record.extra.get("workspace_path"),
        "local_path": record.extra.get("local_path"),
        "file_count": record.extra.get("file_count"),
        "total_size": record.extra.get("total_size"),
        "skipped": record.extra.get("skipped"),
    }


@router.post("/api/uploads/{session_id}/projects/clone")
async def clone_project_upload(session_id: str, request: CloneProjectRequest):
    """Start a session from a project's latest state in an earlier session (no re-upload)."""
    service = _attachment_service(session_id)
    try:
        record = service.clone_project(request.source_session_id, request.project_id, session_id)
    except Exception as exc:
        raise _project_failure(session_id, "clone", exc)
    return _register_project(session_id, request.yaml_file, record)


class OpenLocalProjectRequest(BaseModel):
    path: str
    yaml_file: Optional[str] = None


@router.post("/api/uploads/{session_id}/projects/open-local", dependencies=[Depends(require_local_origin)])
async def open_local_project(session_id: str, request: OpenLocalProjectRequest):
    """Open a folder on this machine in place: the agents work directly in it (nothing is copied)."""
    service = _attachment_service(session_id)
    session = get_websocket_manager().session_store.get_session(session_id)
    current = opened_project_folder(session) if session else None
    try:
        record = await asyncio.to_thread(
            service.open_local_project,
            session_id,
            request.path,
            current_folder=str(current) if current else None,
        )
    except Exception as exc:
        raise _project_failure(session_id, "open", exc)
    return _register_project(session_id, request.yaml_file, record)


@router.post("/api/uploads/{session_id}/projects/{project_id}/files")
async def upload_project_files(
    session_id: str,
    project_id: str,
    files: List[UploadFile] = File(...),
    paths: List[str] = Form(...),
):
    service = _attachment_service(session_id)
    try:
        return await service.save_project_files(session_id, project_id, files, paths)
    except Exception as exc:
        raise _project_failure(session_id, "store", exc)


@router.post("/api/uploads/{session_id}/projects/{project_id}/finalize")
async def finalize_project_upload(
    session_id: str, project_id: str, request: Optional[FinalizeProjectRequest] = None
):
    service = _attachment_service(session_id)
    try:
        record = service.finalize_project(session_id, project_id)
    except Exception as exc:
        raise _project_failure(session_id, "finalize", exc)
    # List the session in the sidebar under this project, even before it is launched
    return _register_project(session_id, request.yaml_file if request else None, record)
