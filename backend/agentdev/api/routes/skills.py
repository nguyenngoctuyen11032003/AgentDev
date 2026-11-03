"""Shared skill library API: list, create (paste / .md upload), edit, delete, import."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from agentdev.api.services import skill_library
from agentdev.connections.security import require_local_origin
from agentdev.utils.exceptions import ValidationError


def _local_pages_only(request: Request) -> None:
    # Skills become agent instructions and import reads local folders: block other websites.
    require_local_origin(request)


router = APIRouter(prefix="/api/skills", tags=["skills"], dependencies=[Depends(_local_pages_only)])


class SkillSaveRequest(BaseModel):
    content: str = Field(..., description="SKILL.md text, with or without YAML frontmatter")
    name: Optional[str] = None
    description: Optional[str] = None
    overwrite: bool = False


class SkillImportRequest(BaseModel):
    names: List[str]
    source: Optional[str] = None
    overwrite: bool = False


def _bad_request(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail=str(exc))


def _disk_error(exc: OSError) -> HTTPException:
    """A file could not be written / moved / deleted: say so instead of a bare 500."""
    if isinstance(exc, PermissionError):
        return HTTPException(
            status_code=409,
            detail=f"Permission denied: a file in the skill folder is open in another program or read-only ({exc})",
        )
    return HTTPException(status_code=500, detail=f"Could not update the skill folder: {exc}")


@router.get("")
def list_skills():
    return {"skills": skill_library.list_skills()}


@router.get("/import-source")
def import_source(source: Optional[str] = None):
    return skill_library.list_import_source(source)


@router.post("/import")
def import_skills(payload: SkillImportRequest):
    try:
        return skill_library.import_skills(payload.names, source=payload.source, overwrite=payload.overwrite)
    except ValidationError as exc:
        raise _bad_request(exc) from exc
    except OSError as exc:
        raise _disk_error(exc) from exc


@router.get("/{name}")
def get_skill(name: str):
    try:
        return skill_library.get_skill(name)
    except ValidationError as exc:
        raise _bad_request(exc) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found") from exc


@router.post("", status_code=201)
def create_skill(payload: SkillSaveRequest):
    try:
        return skill_library.save_skill(
            payload.content, name=payload.name, description=payload.description, overwrite=payload.overwrite
        )
    except ValidationError as exc:
        raise _bad_request(exc) from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=f"Skill '{exc}' already exists") from exc
    except OSError as exc:
        raise _disk_error(exc) from exc


@router.put("/{name}")
def update_skill(name: str, payload: SkillSaveRequest):
    try:
        return skill_library.save_skill(
            payload.content, name=payload.name, description=payload.description, rename_from=name
        )
    except ValidationError as exc:
        raise _bad_request(exc) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found") from exc
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=f"Skill '{exc}' already exists") from exc
    except OSError as exc:
        raise _disk_error(exc) from exc


@router.delete("/{name}")
def delete_skill(name: str):
    try:
        skill_library.delete_skill(name)
    except ValidationError as exc:
        raise _bad_request(exc) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found") from exc
    except OSError as exc:
        raise _disk_error(exc) from exc
    return {"deleted": name}
