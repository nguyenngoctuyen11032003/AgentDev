"""Workflow assistant API: provider list, one chat turn, cancel, saved sessions."""

import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator

from agentdev.api.services import assistant_sessions as sessions
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
    # A model of the vendor's account (from the connection's model list); empty = the account default.
    model: Optional[str] = Field(None, max_length=120, pattern=r"^[A-Za-z0-9._:/@\[\]-]*$")
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
            model=body.model or None,
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


# ---------------------------------------------------------------------------- saved sessions


class SessionIn(BaseModel):
    workflow: Optional[str] = Field(None, max_length=140)
    title: str = Field("", max_length=500)
    messages: List[dict] = Field(default_factory=list, max_length=2000)
    pending_message_id: Optional[str] = Field(None, max_length=64)
    vendor: Optional[str] = Field(None, max_length=40)
    model: Optional[str] = Field(None, max_length=120)


def _session_error(exc: sessions.SessionError) -> JSONResponse:
    status = 404 if exc.code == "not_found" else 400
    return JSONResponse({"error": exc.code, "message": str(exc)}, status_code=status)


@router.get("/sessions")
def list_sessions(workflow: Optional[str] = None, all: bool = False):  # noqa: A002 - query name
    try:
        return {"sessions": sessions.list_sessions(workflow, all_workflows=all)}
    except sessions.SessionError as exc:
        return _session_error(exc)


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    try:
        return sessions.get_session(session_id)
    except sessions.SessionError as exc:
        return _session_error(exc)


@router.put("/sessions/{session_id}")
def save_session(session_id: str, body: SessionIn):
    try:
        return sessions.save_session(session_id, workflow=body.workflow, title=body.title,
                                     messages=body.messages, pending_message_id=body.pending_message_id,
                                     vendor=body.vendor, model=body.model)
    except sessions.SessionError as exc:
        return _session_error(exc)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    try:
        return {"deleted": sessions.delete_session(session_id)}
    except sessions.SessionError as exc:
        return _session_error(exc)
