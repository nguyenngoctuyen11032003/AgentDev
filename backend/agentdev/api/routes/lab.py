"""Workflow Lab API: static readiness check, scenario evaluation runs, and the files those runs produced."""

import asyncio
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agentdev.api.services import lab_outputs
from agentdev.api.services.local_projects import open_on_machine
from agentdev.api.services.workflow_lab import (
    MAX_REPEATS,
    MAX_SCENARIOS,
    Scenario,
    get_lab_runner,
    static_check,
)
from agentdev.connections.security import require_local_origin
from agentdev.runtime.sdk import _resolve_yaml_path
from agentdev.utils.workspace_paths import validate_path_component


def _local_pages_only(request: Request) -> None:
    require_local_origin(request)


router = APIRouter(prefix="/api/lab", tags=["lab"], dependencies=[Depends(_local_pages_only)])


class CheckRequest(BaseModel):
    yaml_file: str


class ScenarioIn(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=20_000)
    criteria: str = Field("", max_length=5_000)
    name: str = Field("", max_length=120)
    max_seconds: Optional[int] = Field(None, ge=10, le=3600)
    max_tokens: Optional[int] = Field(None, ge=1000, le=2_000_000)


class EvaluateRequest(BaseModel):
    yaml_file: str
    scenarios: List[ScenarioIn]
    repeats: int = 1


def _workflow_path(yaml_file: str):
    name = (yaml_file or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="yaml_file is required")
    if not name.endswith((".yaml", ".yml")):
        name += ".yaml"
    try:
        validate_path_component(name, field="yaml_file")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = _resolve_yaml_path(name)
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"Workflow '{name}' not found")
    return name, path


@router.post("/check")
def check(payload: CheckRequest):
    name, path = _workflow_path(payload.yaml_file)
    return {"workflow": name, **static_check(path)}


@router.post("/evaluate", status_code=202)
def evaluate(payload: EvaluateRequest):
    name, path = _workflow_path(payload.yaml_file)
    scenarios = [Scenario(prompt=s.prompt.strip(), criteria=s.criteria.strip(), name=s.name.strip(),
                          max_seconds=s.max_seconds, max_tokens=s.max_tokens)
                 for s in payload.scenarios if s.prompt.strip()]
    if not scenarios:
        raise HTTPException(status_code=400, detail="Add at least one test scenario")
    if len(scenarios) > MAX_SCENARIOS:
        raise HTTPException(status_code=400, detail=f"At most {MAX_SCENARIOS} scenarios per run")
    repeats = max(1, min(int(payload.repeats or 1), MAX_REPEATS))
    try:
        config_status = static_check(path).get("status", "")
    except Exception:  # noqa: BLE001 - the check is advisory here; the run reports its own errors
        config_status = ""
    job = get_lab_runner().start(path, name, scenarios, repeats, config_status=config_status)
    return job.to_dict()


@router.get("/jobs")
def list_jobs(workflow: str, limit: int = 20):
    name = (workflow or "").strip()
    if name and not name.endswith((".yaml", ".yml")):
        name += ".yaml"
    return {"workflow": name, "jobs": get_lab_runner().list_jobs(name, max(1, min(limit, 100)))}


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    job = get_lab_runner().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Lab run not found")
    return job.to_dict()


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: str):
    job = get_lab_runner().cancel(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Lab run not found")
    return job.to_dict()


@router.post("/jobs/{job_id}/resume", status_code=202)
def resume(job_id: str):
    """Run again only the unfinished runs of a job a server restart (or a cancel) stopped."""
    runner = get_lab_runner()
    stored = runner.get(job_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Lab run not found")
    _, path = _workflow_path(stored.to_dict().get("workflow", ""))
    try:
        job = runner.resume(job_id, path)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return job.to_dict()


class GenerateRequest(BaseModel):
    yaml_file: str
    count: int = 4
    language: str = Field("Vietnamese", max_length=40)


@router.post("/generate")
def generate(payload: GenerateRequest):
    from agentdev.api.services.workflow_lab import generate_scenarios

    _, path = _workflow_path(payload.yaml_file)
    try:
        return {"scenarios": generate_scenarios(path, payload.count, payload.language)}
    except Exception as exc:  # noqa: BLE001 - shown to the user as a retryable message
        raise HTTPException(status_code=502, detail=str(exc) or exc.__class__.__name__) from exc


# ----------------------------------------------------------------------------- files a run produced


class OpenRequest(BaseModel):
    path: str = Field("", max_length=4096)
    reveal: bool = False


class CleanupRequest(BaseModel):
    older_than_days: int = Field(..., ge=0, le=36500)
    orphans_only: bool = False


def _outputs_call(func, *args):
    """Run a lab_outputs function, turning its errors into HTTP errors."""
    try:
        return func(*args)
    except lab_outputs.LabOutputsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _send_file(target) -> FileResponse:
    return FileResponse(target, media_type=lab_outputs.content_type(target), headers=lab_outputs.response_headers(target))


@router.get("/jobs/{job_id}/products")
def job_products(job_id: str):
    """What every run of a job produced (type, size, running preview), for the Lab's product overview."""
    return _outputs_call(lab_outputs.job_products, job_id)


@router.get("/jobs/{job_id}/runs/{run}/files")
def run_files(job_id: str, run: int):
    return _outputs_call(lab_outputs.list_files, job_id, run)


@router.get("/jobs/{job_id}/runs/{run}/file")
def run_file(job_id: str, run: int, path: str):
    return _send_file(_outputs_call(lab_outputs.run_file, job_id, run, path))


@router.get("/jobs/{job_id}/runs/{run}/site/{path:path}")
def run_site(job_id: str, run: int, path: str = ""):
    """The product served as a static site (iframe src of a "static" project), so relative assets load."""
    return _send_file(_outputs_call(lab_outputs.site_file, job_id, run, path))


@router.post("/jobs/{job_id}/runs/{run}/open")
async def run_open(job_id: str, run: int, payload: OpenRequest):
    target = _outputs_call(lab_outputs.open_target, job_id, run, payload.path)
    try:
        action = await asyncio.to_thread(open_on_machine, target, reveal=payload.reveal)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not open the file: {exc}") from exc
    return {"status": action, "path": str(target)}


@router.delete("/jobs/{job_id}/runs/{run}/outputs")
def delete_run_outputs(job_id: str, run: int):
    return _outputs_call(lab_outputs.delete_run_outputs, job_id, run)


@router.get("/storage")
def lab_storage():
    return lab_outputs.storage_stats()


class WorkflowCleanupRequest(BaseModel):
    workflow: str = Field(..., min_length=1, max_length=200)
    keep_job: str = Field("", max_length=64)


@router.get("/storage/suggestion")
def lab_storage_suggestion(workflow: str, keep_job: str = ""):
    """Offer to clean this workflow's old products after an evaluation (keeps it and the latest passing one)."""
    from agentdev.api.services import lab_cleanup

    return lab_cleanup.suggestion(workflow, keep_job)


@router.post("/storage/cleanup-workflow")
def lab_storage_cleanup_workflow(payload: WorkflowCleanupRequest):
    from agentdev.api.services import lab_cleanup

    return lab_cleanup.cleanup(payload.workflow, payload.keep_job)


@router.post("/storage/cleanup")
def lab_storage_cleanup(payload: CleanupRequest):
    return lab_outputs.cleanup_storage(payload.older_than_days, payload.orphans_only)
