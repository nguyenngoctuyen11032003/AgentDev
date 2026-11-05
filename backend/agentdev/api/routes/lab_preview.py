"""Lab app preview ("Chạy thử"): start, inspect, keep alive and stop a run's web app / site.

``{run}`` is the run's stable ``run_id`` (positions shift after a resume); a position still works for old jobs.
Errors carry ``detail = {message, code, params}``: ``code`` is stable so the UI can translate it.
"""

from typing import Any, Callable, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from agentdev.api.services.app_preview import PreviewError, get_preview_manager
from agentdev.api.services.lab_outputs import valid_run_ref
from agentdev.connections.security import require_local_origin
from agentdev.utils.workspace_paths import validate_path_component


def _local_pages_only(request: Request) -> None:
    require_local_origin(request)


router = APIRouter(prefix="/api/lab", tags=["lab"], dependencies=[Depends(_local_pages_only)])


def _key(job_id: str, run: str) -> tuple:
    if not valid_run_ref(run):
        raise HTTPException(status_code=400, detail={"message": "Invalid run", "code": "preview_run_invalid",
                                                     "params": {}})
    try:
        validate_path_component(job_id, field="job_id")
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"message": "Invalid job id", "code": "preview_job_invalid",
                                                     "params": {}}) from exc
    return job_id, run


async def _call(fn: Callable[..., Dict[str, Any]], *args: Any) -> Dict[str, Any]:
    try:
        return await run_in_threadpool(fn, *args)
    except PreviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.http_detail()) from exc


@router.post("/jobs/{job_id}/runs/{run}/preview", dependencies=[Depends(require_local_origin)])
async def start_preview(job_id: str, run: str) -> Dict[str, Any]:
    return await _call(get_preview_manager().start, *_key(job_id, run))


@router.get("/jobs/{job_id}/runs/{run}/preview")
async def preview_status(job_id: str, run: str) -> Dict[str, Any]:
    return await _call(get_preview_manager().status, *_key(job_id, run))


@router.post("/jobs/{job_id}/runs/{run}/preview/heartbeat", dependencies=[Depends(require_local_origin)])
async def preview_heartbeat(job_id: str, run: str) -> Dict[str, Any]:
    """The page still shows this preview: reset its idle timer. -> {status, alive, idle_seconds}"""
    return await _call(get_preview_manager().heartbeat, *_key(job_id, run))


@router.delete("/jobs/{job_id}/runs/{run}/preview", dependencies=[Depends(require_local_origin)])
async def stop_preview(job_id: str, run: str) -> Dict[str, Any]:
    return await _call(get_preview_manager().stop, *_key(job_id, run))
