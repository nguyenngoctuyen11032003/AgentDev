"""Workflow Lab API: static readiness check and scenario evaluation runs."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

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
    scenarios = [Scenario(prompt=s.prompt.strip(), criteria=s.criteria.strip(), name=s.name.strip())
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
