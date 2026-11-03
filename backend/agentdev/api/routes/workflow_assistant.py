"""Workflow assistant API: provider list, one chat turn, cancel."""

from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from agentdev.api.services import workflow_assistant as service
from agentdev.connections.security import require_local_origin


def _local_pages_only(request: Request) -> None:
    require_local_origin(request)


router = APIRouter(
    prefix="/api/workflow-assistant",
    tags=["workflow-assistant"],
    dependencies=[Depends(_local_pages_only)],
)


class MessageIn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=50_000)


class ChatRequest(BaseModel):
    vendor: str
    workflow: Optional[str] = None
    messages: List[MessageIn] = Field(..., min_length=1, max_length=200)
    pending_yaml: Optional[str] = Field(None, max_length=200_000)
    request_id: str = Field(..., min_length=1, max_length=64)


class CancelRequest(BaseModel):
    request_id: str = Field(..., min_length=1, max_length=64)


@router.get("/providers")
def get_providers() -> dict:
    return {"providers": service.list_providers()}


@router.post("/chat")
async def chat(body: ChatRequest):
    try:
        # run_turn sets its cancel scope in the calling thread, so it must run whole inside one worker.
        return await run_in_threadpool(
            service.run_turn,
            vendor=body.vendor,
            workflow=body.workflow,
            messages=[m.model_dump() for m in body.messages],
            pending_yaml=body.pending_yaml,
            request_id=body.request_id,
        )
    except service.AssistantError as exc:
        status = 400 if exc.code == "bad_request" else 200
        return JSONResponse({"error": exc.code, "message": str(exc)}, status_code=status)


@router.post("/cancel")
def cancel(body: CancelRequest) -> dict:
    return {"cancelled": service.cancel(body.request_id)}
