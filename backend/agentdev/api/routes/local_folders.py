"""Browse folders on this machine for the in-app "Open folder" picker."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from agentdev.api.services.local_projects import create_folder, list_folders, list_locations
from agentdev.connections.security import require_local_origin
from agentdev.utils.exceptions import ValidationError


def _local_pages_only(request: Request) -> None:
    # CORS is open, so without this any website could read this machine's folder names.
    require_local_origin(request)


router = APIRouter(prefix="/api/local-folders", tags=["local-folders"], dependencies=[Depends(_local_pages_only)])


@router.get("")
def browse(path: Optional[str] = None):
    """No ``path``: starting locations (home folders, drives). Otherwise its sub-folders."""
    if not path:
        return {"locations": list_locations()}
    try:
        return list_folders(path)
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


class CreateFolderBody(BaseModel):
    parent: str
    name: str


@router.post("")
def create(body: CreateFolderBody):
    """Make a new empty folder inside ``parent`` so a project can start from scratch."""
    try:
        return list_folders(str(create_folder(body.parent, body.name)))
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
