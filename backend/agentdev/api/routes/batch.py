import asyncio

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from agentdev.entity.enums import LogLevel
from agentdev.api.services.batch_parser import parse_batch_file
from agentdev.api.services.batch_run_service import BatchRunService
from agentdev.api.state import ensure_known_session
from agentdev.utils.exceptions import SecurityError, ValidationError

MAX_BATCH_UPLOAD_BYTES = 10 * 1024 * 1024
_BACKGROUND_TASKS: set = set()


def _spawn(coro):
    """Keep a strong reference so the event loop cannot garbage-collect a running task."""
    task = asyncio.create_task(coro)
    if not hasattr(task, "add_done_callback"):
        return task
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


router = APIRouter()

MAX_PARALLEL = 50  # same upper bound as the Batch run page's settings


@router.post("/api/workflows/batch")
async def execute_batch(
    file: UploadFile = File(...),
    session_id: str = Form(...),
    yaml_file: str = Form(...),
    max_parallel: int = Form(5),
    log_level: str | None = Form(None),
):
    try:
        manager = ensure_known_session(session_id, require_connection=True)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if not 1 <= max_parallel <= MAX_PARALLEL:
        raise HTTPException(status_code=400, detail=f"max_parallel must be between 1 and {MAX_PARALLEL}")

    # Reject an unknown / unsafe workflow now instead of failing every row in the background.
    try:
        BatchRunService._resolve_yaml_path(yaml_file)
    except (ValidationError, SecurityError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        content = await file.read(MAX_BATCH_UPLOAD_BYTES + 1)
        if len(content) > MAX_BATCH_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Batch file is too large (max 10 MB)")
        tasks, file_base = parse_batch_file(content, file.filename or "batch.csv")
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    resolved_level = None
    if log_level:
        try:
            resolved_level = LogLevel(log_level)
        except ValueError:
            raise HTTPException(status_code=400, detail="log_level must be either DEBUG or INFO")

    service = BatchRunService()
    _spawn(
        service.run_batch(
            session_id,
            yaml_file,
            tasks,
            manager,
            max_parallel=max_parallel,
            file_base=file_base,
            log_level=resolved_level,
        )
    )

    return {
        "status": "accepted",
        "session_id": session_id,
        "batch_id": session_id,
        "task_count": len(tasks),
    }
