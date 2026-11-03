"""Workflow assistant API: provider list, one chat turn, cancel."""

import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from agentdev.api.services import workflow_assistant as service
from agentdev.connections.security import require_local_origin

logger = logging.getLogger(__name__)


def _local_pages_only(request: Request) -> None:
    require_local_origin(request)


router = APIRouter(
    prefix="/api/workflow-assistant",
    tags=["workflow-assistant"],
    dependencies=[Depends(_local_pages_only)],
)


class MessageIn(BaseModel):
    role: Literal["user", "assistant"]
    # May be empty: an assistant turn that gave up has an empty reply. The last user message may not.
    content: str = Field(..., max_length=50_000)


class ChatRequest(BaseModel):
    vendor: str
    workflow: Optional[str] = None
    messages: List[MessageIn] = Field(..., min_length=1, max_length=200)
    pending_yaml: Optional[str] = Field(None, max_length=200_000)
    request_id: str = Field(..., min_length=1, max_length=64)

    @model_validator(mode="after")
    def _check_size_and_last_message(self) -> "ChatRequest":
        last = self.messages[-1]
        if last.role == "user" and not last.content.strip():
            raise ValueError("the last user message is empty")
        total = sum(len(m.content) for m in self.messages) + len(self.pending_yaml or "")
        if total > service.MAX_REQUEST_CHARS:
            raise ValueError(f"the request is too large (over {service.MAX_REQUEST_CHARS} characters)")
        return self


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
    except Exception:  # noqa: BLE001 - keep the {error, message} shape; the detail stays in the log
        logger.exception("Workflow assistant turn failed")
        return JSONResponse({"error": "internal", "message": "The assistant hit an unexpected error. "
                             "Details are in the server log."}, status_code=500)


@router.post("/cancel")
def cancel(body: CancelRequest) -> dict:
    return {"cancelled": service.cancel(body.request_id)}
