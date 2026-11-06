"""What a chat session produced (Run page "Sản phẩm"): browse, serve, open its files and try its app.

The same API as the Lab's ``/api/lab/jobs/{job}/runs/{run}/...`` routes, for the session's output folder (its
opened project, else ``storage/warehouse/session_<id>/code_workspace``).
"""

import asyncio
from typing import Any, Callable, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from agentdev.api.services import git_checkpoint, lab_outputs, product_accounts, session_outputs
from agentdev.api.services.app_preview import PreviewError
from agentdev.api.services.product_archive import archive_response
from agentdev.api.services.local_projects import open_on_machine
from agentdev.connections.security import require_local_origin


def _local_pages_only(request: Request) -> None:
    require_local_origin(request)


router = APIRouter(prefix="/api/sessions/{session_id}/outputs", tags=["session-outputs"],
                   dependencies=[Depends(_local_pages_only)])


class OpenRequest(BaseModel):
    path: str = Field("", max_length=4096)
    reveal: bool = False


class UndoRequest(BaseModel):
    paths: list[str] | None = Field(None, max_length=500)  # None = every file the run changed


async def _call(func: Callable[..., Any], *args: Any) -> Any:
    """Run a (blocking: it walks folders) service function off the event loop, mapping its errors to HTTP."""
    try:
        return await run_in_threadpool(func, *args)
    except lab_outputs.LabOutputsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    except PreviewError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


def _send_file(target) -> FileResponse:
    return FileResponse(target, media_type=lab_outputs.content_type(target),
                        headers=lab_outputs.response_headers(target))


@router.get("/summary")
async def outputs_summary(session_id: str) -> Dict[str, Any]:
    """Counts, project type and running preview: the one-line "Sản phẩm" summary of the Run page."""
    return await _call(session_outputs.summary, session_id)


@router.get("/files")
async def outputs_files(session_id: str) -> Dict[str, Any]:
    return await _call(session_outputs.list_files, session_id)


@router.get("/file")
async def outputs_file(session_id: str, path: str):
    return _send_file(await _call(session_outputs.file, session_id, path))


@router.get("/archive")
async def outputs_archive(session_id: str):
    """The session's product as a .zip (no node_modules, .venv, .git, caches, .env or attachments)."""
    path, filename = await _call(session_outputs.archive, session_id)
    return archive_response(path, filename)


class AccountsRequest(BaseModel):
    accounts: list = Field(default_factory=list, max_length=product_accounts.MAX_ACCOUNTS)


@router.get("/accounts")
async def outputs_accounts(session_id: str) -> Dict[str, Any]:
    """Test accounts the user saved for this session's app ("Tài khoản dùng thử")."""
    key = product_accounts.session_key(await _call(session_outputs.session_dir_id, session_id))
    return {"accounts": await run_in_threadpool(product_accounts.load, key)}


@router.put("/accounts")
async def outputs_accounts_save(session_id: str, payload: AccountsRequest) -> Dict[str, Any]:
    key = product_accounts.session_key(await _call(session_outputs.session_dir_id, session_id))
    try:
        return {"accounts": await run_in_threadpool(product_accounts.save, key, payload.accounts)}
    except product_accounts.AccountsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/site/{path:path}")
async def outputs_site(session_id: str, path: str = ""):
    """The output folder served as a static site (iframe src of a "static" project), so relative assets load."""
    return _send_file(await _call(session_outputs.site_file, session_id, path))


@router.post("/open")
async def outputs_open(session_id: str, payload: OpenRequest) -> Dict[str, Any]:
    target = await _call(session_outputs.open_target, session_id, payload.path)
    try:
        action = await asyncio.to_thread(open_on_machine, target, reveal=payload.reveal)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not open the file: {exc}") from exc
    return {"status": action, "path": str(target)}


@router.post("/preview")
async def outputs_preview_start(session_id: str) -> Dict[str, Any]:
    return await _call(session_outputs.preview_start, session_id)


@router.get("/preview")
async def outputs_preview_status(session_id: str) -> Dict[str, Any]:
    return await _call(session_outputs.preview_status, session_id)


@router.delete("/preview")
async def outputs_preview_stop(session_id: str) -> Dict[str, Any]:
    return await _call(session_outputs.preview_stop, session_id)


@router.get("/changes")
async def outputs_changes(session_id: str) -> Dict[str, Any]:
    """Files the latest run turn changed in a git workspace (hidden checkpoint), with diffs and undo state."""
    return await _call(git_checkpoint.changes, session_id)


@router.post("/changes/undo")
async def outputs_changes_undo(session_id: str, payload: UndoRequest | None = None) -> Dict[str, Any]:
    paths = payload.paths if payload else None
    return await _call(git_checkpoint.undo, session_id, paths)


@router.post("/changes/keep-branch")
async def outputs_changes_keep_branch(session_id: str) -> Dict[str, Any]:
    return await _call(git_checkpoint.keep_branch, session_id)
