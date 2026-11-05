"""Lab app preview ("Chạy thử"): start, inspect and stop a run's web app / site."""

from typing import Any, Callable, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from agentdev.api.services.app_preview import PreviewError, get_preview_manager
from agentdev.connections.security import require_local_origin
from agentdev.utils.workspace_paths import validate_path_component


def _local_pages_only(request: Request) -> None:
    require_local_origin(request)


router = APIRouter(prefix="/api/lab", tags=["lab"], dependencies=[Depends(_local_pages_only)])


def _key(job_id: str, run: int) -> tuple:
    if run < 0:
        raise HTTPException(status_code=400, detail="Invalid run index")
    try:
        validate_path_component(job_id, field="job_id")
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid job id") from exc
    return job_id, run


async def _call(fn: Callable[..., Dict[str, Any]], *args: Any) -> Dict[str, Any]:
    try:
        return await run_in_threadpool(fn, *args)
    except PreviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/jobs/{job_id}/runs/{run}/preview", dependencies=[Depends(require_local_origin)])
async def start_preview(job_id: str, run: int) -> Dict[str, Any]:
    return await _call(get_preview_manager().start, *_key(job_id, run))


@router.get("/jobs/{job_id}/runs/{run}/preview")
async def preview_status(job_id: str, run: int) -> Dict[str, Any]:
    return await _call(get_preview_manager().status, *_key(job_id, run))


@router.delete("/jobs/{job_id}/runs/{run}/preview", dependencies=[Depends(require_local_origin)])
async def stop_preview(job_id: str, run: int) -> Dict[str, Any]:
    return await _call(get_preview_manager().stop, *_key(job_id, run))
