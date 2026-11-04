import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from agentdev.api.models import WorkflowRequest
from agentdev.api.services.workflow_run_service import (
    RUN_IN_PROGRESS_CODE,
    RUN_IN_PROGRESS_MESSAGE,
    run_in_progress,
)
from agentdev.api.state import ensure_known_session
from agentdev.utils.exceptions import ValidationError, WorkflowExecutionError
from agentdev.utils.structured_logger import get_server_logger, LogType

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


@router.post("/api/workflow/execute")
async def execute_workflow(request: WorkflowRequest):
    try:
        manager = ensure_known_session(request.session_id, require_connection=True)
        # log_level = LogLevel(request.log_level) if request.log_level else None
        log_level = None
    except ValueError:
        raise HTTPException(status_code=400, detail="log_level must be either DEBUG or INFO")
    if run_in_progress(manager.session_store.get_session(request.session_id)):
        # Not a run failure: the client should wait for the current run (or cancel it).
        return JSONResponse(
            status_code=409,
            content={"detail": RUN_IN_PROGRESS_MESSAGE, "code": RUN_IN_PROGRESS_CODE},
        )
    try:
        _spawn(
            manager.workflow_run_service.start_workflow(
                request.session_id,
                request.yaml_file,
                request.task_prompt,
                manager,
                attachments=request.attachments,
                log_level=log_level,
                mode=request.mode,
            )
        )

        logger = get_server_logger()
        logger.info(
            "Workflow execution started",
            log_type=LogType.WORKFLOW,
            session_id=request.session_id,
            yaml_file=request.yaml_file,
            task_prompt_length=len(request.task_prompt or ""),
        )

        return {
            "status": "started",
            "session_id": request.session_id,
            "message": "Workflow execution started",
        }
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger = get_server_logger()
        logger.log_exception(exc, "Failed to start workflow execution")
        raise WorkflowExecutionError(f"Failed to start workflow: {exc}")
