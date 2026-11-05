import asyncio
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from fastapi.responses import FileResponse

from agentdev.paths import WAREHOUSE_DIR
from agentdev.utils.workspace_paths import session_directory_name
from agentdev.api.services.local_projects import open_on_machine, opened_project_folder, resolve_project_file
from agentdev.api.state import get_websocket_manager
from agentdev.connections.security import require_local_origin
from agentdev.utils.exceptions import ValidationError
from agentdev.utils.attachments import encode_file_to_data_uri

router = APIRouter()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


def _split_csv(value: Optional[str]) -> Optional[List[str]]:
    if not value:
        return None
    parts = [part.strip() for part in value.split(",")]
    filtered = [part for part in parts if part]
    return filtered or None


def _get_session_and_queue(session_id: str):
    manager = get_websocket_manager()
    session = manager.session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    queue = session.artifact_queue
    if queue is None:
        raise HTTPException(status_code=404, detail="Artifact stream not available")
    return manager, queue


@router.get("/api/sessions/{session_id}/artifact-events")
async def poll_artifact_events(
    session_id: str,
    wait_seconds: float = Query(25.0, ge=0.0, le=60.0),
    after: Optional[int] = Query(None, ge=0),
    include_mime: Optional[str] = Query(None),
    include_ext: Optional[str] = Query(None),
    max_size: Optional[int] = Query(None, gt=0),
    limit: int = Query(25, ge=1, le=100),
):
    manager, queue = _get_session_and_queue(session_id)
    include_mime_list = _split_csv(include_mime)
    include_ext_list = _split_csv(include_ext)

    events, next_cursor, timed_out = await asyncio.to_thread(
        queue.wait_for_events,
        after=after,
        include_mime=include_mime_list,
        include_ext=include_ext_list,
        max_size=max_size,
        limit=limit,
        timeout=wait_seconds,
    )

    payload = {
        "events": [event.to_dict() for event in events],
        "next_cursor": next_cursor,
        "timed_out": timed_out,
        "has_more": queue.last_sequence > (next_cursor or 0),
    }
    return payload


@router.get("/api/sessions/{session_id}/artifacts/{artifact_id}")
async def get_artifact(
    session_id: str,
    artifact_id: str,
    mode: str = Query("meta", pattern="^(meta|stream)$"),
    download: bool = Query(False),
):
    manager, _ = _get_session_and_queue(session_id)
    store = manager.attachment_service.get_attachment_store(session_id)
    record = store.get(artifact_id)
    if not record:
        raise HTTPException(status_code=404, detail="Artifact not found")

    ref = record.ref
    if mode == "stream":
        local_path = ref.local_path
        if not local_path:
            raise HTTPException(status_code=404, detail="Artifact content unavailable")
        path = Path(local_path)
        if not path.is_file():
            raise HTTPException(status_code=404, detail="Artifact file missing")
        media_type = ref.mime_type or "application/octet-stream"
        # FileResponse closes the file itself and encodes non-ASCII names (RFC 5987),
        # which a hand-built header cannot (a Vietnamese filename made it a 500).
        return FileResponse(
            path,
            media_type=media_type,
            filename=ref.name or path.name,
            content_disposition_type="attachment" if download else "inline",
        )

    data_uri = ref.data_uri
    if not data_uri and ref.local_path and (ref.size or 0) <= MAX_FILE_SIZE:
        local_path = Path(ref.local_path)
        if local_path.exists():
            # Up to 20 MB read + base64: not on the event loop
            data_uri = await asyncio.to_thread(
                encode_file_to_data_uri, local_path, ref.mime_type or "application/octet-stream"
            )
    return {
        "artifact_id": artifact_id,
        "name": ref.name,
        "mime_type": ref.mime_type,
        "size": ref.size,
        "sha256": ref.sha256,
        "data_uri": data_uri,
        "local_path": ref.local_path,
        "extra": record.extra,
    }


class OpenLocalFileRequest(BaseModel):
    relative_path: str
    reveal: bool = False


@router.post("/api/sessions/{session_id}/local-files/open", dependencies=[Depends(require_local_origin)])
async def open_local_file(session_id: str, body: OpenLocalFileRequest):
    """Open a file of the session's opened project on this machine (default app or file manager).

    Only paths inside the project folder registered for the session are accepted.
    """
    manager = get_websocket_manager()
    session = manager.session_store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    root = opened_project_folder(session)
    if root is None:
        raise HTTPException(status_code=404, detail="This session has no opened project folder")
    try:
        target = resolve_project_file(root, body.relative_path)
        action = await asyncio.to_thread(open_on_machine, target, reveal=body.reveal)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not open the file: {exc}") from exc
    return {"status": action, "path": str(target)}


def _output_location(session_id: str) -> dict:
    """Where this session's results land: the opened project, else the session's own workspace."""
    manager = get_websocket_manager()
    session = manager.session_store.get_session(session_id)
    root = opened_project_folder(session) if session else None
    if root is not None:
        return {"kind": "project", "path": str(root)}
    try:
        folder = WAREHOUSE_DIR / session_directory_name(session_id) / "code_workspace"
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"kind": "session", "path": str(folder)}


@router.get("/api/sessions/{session_id}/output-location", dependencies=[Depends(require_local_origin)])
async def get_output_location(session_id: str):
    """Tell the chat where code, videos and other deliverables are saved for this session."""
    return _output_location(session_id)


@router.post("/api/sessions/{session_id}/output-location/open", dependencies=[Depends(require_local_origin)])
async def open_output_location(session_id: str):
    """Show the output folder in the file manager (created first when nothing has been written yet)."""
    location = _output_location(session_id)
    target = Path(location["path"])
    try:
        await asyncio.to_thread(target.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(open_on_machine, target, reveal=True)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not open the folder: {exc}") from exc
    return location
