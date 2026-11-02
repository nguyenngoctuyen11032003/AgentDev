"""Pre-flight check of connection references in workflow YAML."""

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agentdev.connections.validation import check_workflow_connections

router = APIRouter(prefix="/api/connections", tags=["connections"])


class CheckBody(BaseModel):
    yaml_content: str


@router.post("/check")
def check_connections(body: CheckBody):
    try:
        doc = yaml.safe_load(body.yaml_content)
    except yaml.YAMLError:
        raise HTTPException(status_code=422, detail="Invalid YAML")
    if not isinstance(doc, dict):
        raise HTTPException(status_code=422, detail="Invalid YAML")
    problems = check_workflow_connections(doc)
    return {"ok": not problems, "problems": problems}
