import asyncio

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from agentdev.api.models import WorkflowRequest
from agentdev.api.services.workflow_run_service import (
    RUN_IN_PROGRESS_CODE,
    RUN_IN_PROGRESS_MESSAGE,
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
    service = manager.workflow_run_service
    # Check and claim in one synchronous step (reserve_launch also refuses a run in progress): a double
    # click or a second tab must not start a second run (the first spawned task has not set ``starting`` yet).
    token = service.reserve_launch(request.session_id)
    if token is None:
        # Not a run failure: the client should wait for the current run (or cancel it).
        return JSONResponse(
            status_code=409,
            content={"detail": RUN_IN_PROGRESS_MESSAGE, "code": RUN_IN_PROGRESS_CODE},
        )
    try:
        task = _spawn(
            service.start_workflow(
                request.session_id,
                request.yaml_file,
                request.task_prompt,
                manager,
                attachments=request.attachments,
                log_level=log_level,
                mode=request.mode,
                launch_token=token,
            )
        )
        # Whatever happens to the task (finished, failed, cancelled before it ever ran), the
        # claim goes with it; the token keeps a late callback from freeing a newer claim.
        if hasattr(task, "add_done_callback"):
            task.add_done_callback(lambda _t, sid=request.session_id: service.release_launch(sid, token))

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
        service.release_launch(request.session_id, token)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        service.release_launch(request.session_id, token)
        logger = get_server_logger()
        logger.log_exception(exc, "Failed to start workflow execution")
        raise WorkflowExecutionError(f"Failed to start workflow: {exc}")
