from fastapi import APIRouter, HTTPException
from typing import Any

import yaml

from agentdev.api.models import (
    WorkflowCopyRequest,
    WorkflowMergeRequest,
    WorkflowRenameRequest,
    WorkflowUpdateContentRequest,
    WorkflowUploadContentRequest,
)
from agentdev.api.services.workflow_storage import (
    copy_workflow,
    persist_workflow,
    rename_workflow,
    validate_workflow_content,
    validate_workflow_filename,
)
from agentdev.api.services.workflow_yaml_merge import merge_workflow_document
from agentdev.api.settings import YAML_DIR
from agentdev.utils.exceptions import (
    ResourceConflictError,
    ResourceNotFoundError,
    SecurityError,
    ValidationError,
    WorkflowExecutionError,
)
from agentdev.utils.structured_logger import get_server_logger, LogType

router = APIRouter()


def _persist_workflow_from_content(
    filename: str,
    content: str,
    *,
    allow_overwrite: bool,
    action: str,
    success_message: str,
):
    try:
        safe_filename, yaml_content = validate_workflow_content(filename.strip(), content)
        save_path = YAML_DIR / safe_filename

        if save_path.exists() and not allow_overwrite:
            raise HTTPException(status_code=409, detail="Workflow already exists; use the update API to overwrite")

        if not save_path.exists() and allow_overwrite:
            raise HTTPException(status_code=404, detail="Workflow file not found")

        persist_workflow(safe_filename, content, yaml_content, action=action, directory=YAML_DIR)
        return {
            "status": "success",
            "filename": safe_filename,
            "message": success_message.format(filename=safe_filename),
        }
    except ValidationError:
        raise
    except HTTPException:
        raise
    except Exception as exc:
        logger = get_server_logger()
        logger.log_exception(exc, f"Unexpected error during workflow {action}")
        raise WorkflowExecutionError(f"Failed to {action} workflow: {exc}")


@router.get("/api/workflows")
async def list_workflows(include_descriptions: bool = False):
    if not YAML_DIR.exists():
        return {"workflows": [], **({"descriptions": {}} if include_descriptions else {})}
    names = sorted(file.name for file in YAML_DIR.glob("*.y*ml") if file.suffix in (".yaml", ".yml"))
    if not include_descriptions:
        return {"workflows": names}
    # One request for the workflow list page instead of one /desc call per file
    descriptions: dict[str, str] = {}
    for name in names:
        try:
            graph = (yaml.safe_load((YAML_DIR / name).read_text(encoding="utf-8")) or {}).get("graph") or {}
            description = graph.get("description") if isinstance(graph, dict) else None
        except Exception:
            description = None
        descriptions[name] = description.strip() if isinstance(description, str) else ""
    return {"workflows": names, "descriptions": descriptions}


@router.get("/api/workflows/{filename}/args")
async def get_workflow_args(filename: str):
    try:
        safe_filename = validate_workflow_filename(filename, require_yaml_extension=True)
        file_path = YAML_DIR / safe_filename

        if not file_path.exists() or not file_path.is_file():
            raise ResourceNotFoundError(
                "Workflow file not found",
                resource_type="workflow",
                resource_id=safe_filename,
            )

        # Load and validate YAML content
        raw_content = file_path.read_text(encoding="utf-8")
        _, yaml_content = validate_workflow_content(safe_filename, raw_content)

        args: list[dict[str, Any]] = []
        if isinstance(yaml_content, dict):
            graph = yaml_content.get("graph") or {}
            if isinstance(graph, dict):
                raw_args = graph.get("args") or []
                if isinstance(raw_args, list):
                    if len(raw_args) == 0:
                        raise ResourceNotFoundError(
                            "Workflow file does not have args",
                            resource_type="workflow",
                            resource_id=safe_filename,
                        )
                    for item in raw_args:
                        # Each item is expected to be like: { arg_name: [ {key: value}, ... ] }
                        if not isinstance(item, dict) or len(item) != 1:
                            continue
                        (arg_name, spec_list), = item.items()
                        if not isinstance(arg_name, str):
                            continue

                        arg_info: dict[str, Any] = {"name": arg_name}
                        if isinstance(spec_list, list):
                            for spec in spec_list:
                                if isinstance(spec, dict):
                                    for key, value in spec.items():
                                        # Later entries override earlier ones if duplicated
                                        arg_info[str(key)] = value
                        args.append(arg_info)

        logger = get_server_logger()
        logger.info(
            "Workflow args retrieved",
            log_type=LogType.WORKFLOW,
            filename=safe_filename,
            args_count=len(args),
        )

        return {"args": args}
    except ValidationError as exc:
        # 参数或文件名等校验错误
        raise HTTPException(
            status_code=400,
            detail={"message": str(exc)},
        )
    except SecurityError as exc:
        # 安全相关错误（例如路径遍历）
        raise HTTPException(
            status_code=400,
            detail={"message": str(exc)},
        )
    except ResourceNotFoundError as exc:
        # 文件不存在
        raise HTTPException(
            status_code=404,
            detail={"message": str(exc)},
        )
    except Exception as exc:
        logger = get_server_logger()
        logger.log_exception(exc, f"Unexpected error retrieving workflow args: {filename}")
        # 兜底错误
        raise HTTPException(
            status_code=500,
            detail={"message": f"Failed to retrieve workflow args: {exc}"},
        )


@router.get("/api/workflows/{filename}/desc")
async def get_workflow_desc(filename: str):
    try:
        safe_filename = validate_workflow_filename(filename, require_yaml_extension=True)
        file_path = YAML_DIR / safe_filename

        if not file_path.exists() or not file_path.is_file():
            raise ResourceNotFoundError(
                "Workflow file not found",
                resource_type="workflow",
                resource_id=safe_filename,
            )

        # Load and validate YAML content
        raw_content = file_path.read_text(encoding="utf-8")
        _, yaml_content = validate_workflow_content(safe_filename, raw_content)

        desc = ""
        if isinstance(yaml_content, dict):
            graph = yaml_content.get("graph") or {}
            if isinstance(graph, dict):
                desc = graph.get("description") or ""
                if len(desc) == 0:
                        raise ResourceNotFoundError(
                            "Workflow file does not have args",
                            resource_type="workflow",
                            resource_id=safe_filename,
                        )
        logger = get_server_logger()
        logger.info(
            "Workflow description retrieved",
            log_type=LogType.WORKFLOW,
            filename=safe_filename,
        )
        return {"description": desc}
    except ValidationError as exc:
        # 参数或文件名等校验错误
        raise HTTPException(
            status_code=400,
            detail={"message": str(exc)},
        )
    except SecurityError as exc:
        # 安全相关错误（例如路径遍历）
        raise HTTPException(
            status_code=400,
            detail={"message": str(exc)},
        )
    except ResourceNotFoundError as exc:
        # 文件不存在
        raise HTTPException(
            status_code=404,
            detail={"message": str(exc)},
        )
    except Exception as exc:
        logger = get_server_logger()
        logger.log_exception(exc, f"Unexpected error retrieving workflow args: {filename}")
        # 兜底错误
        raise HTTPException(
            status_code=500,
            detail={"message": f"Failed to retrieve workflow args: {exc}"},
        )


@router.post("/api/workflows/upload/content")
async def upload_workflow_content(request: WorkflowUploadContentRequest):
    return _persist_workflow_from_content(
        request.filename,
        request.content,
        allow_overwrite=False,
        action="upload",
        success_message="Workflow {filename} created successfully from content",
    )


@router.put("/api/workflows/{filename}/update")
async def update_workflow_content(filename: str, request: WorkflowUpdateContentRequest):
    return _persist_workflow_from_content(
        filename,
        request.content,
        allow_overwrite=True,
        action="update",
        success_message="Workflow {filename} updated successfully",
    )


@router.put("/api/workflows/{filename}/merge")
async def merge_workflow_content(filename: str, request: WorkflowMergeRequest):
    """Save an edited document from the visual editor, changing only the lines that differ.

    Unlike ``/update`` (which writes the text it is given), this keeps the file's comments,
    anchors/aliases, block scalars, layout and line endings wherever the data did not change.
    """
    try:
        safe_filename = validate_workflow_filename(filename, require_yaml_extension=True)
        file_path = YAML_DIR / safe_filename
        if not file_path.exists() or not file_path.is_file():
            raise ResourceNotFoundError(
                "Workflow file not found",
                resource_type="workflow",
                resource_id=safe_filename,
            )

        raw = file_path.read_bytes().decode("utf-8")
        newline = "\r\n" if "\r\n" in raw else "\n"
        original = raw.replace("\r\n", "\n")
        try:
            content = merge_workflow_document(original, request.document)
            yaml.safe_load(content)  # a merge that writes text the parser rejects must not reach the file
        except Exception as exc:  # an unparseable file: fall back to a plain dump
            get_server_logger().warning(
                "Workflow merge fell back to a full rewrite",
                details={"filename": safe_filename, "error": str(exc)},
            )
            content = yaml.safe_dump(request.document, sort_keys=False, allow_unicode=True)

        _, yaml_content = validate_workflow_content(safe_filename, content)
        persist_workflow(safe_filename, content, yaml_content, action="merge", directory=YAML_DIR, newline=newline)
        return {
            "status": "success",
            "filename": safe_filename,
            "content": content,
            "message": f"Workflow {safe_filename} updated successfully",
        }
    except (ValidationError, SecurityError, ResourceNotFoundError):
        raise
    except Exception as exc:
        logger = get_server_logger()
        logger.log_exception(exc, f"Unexpected error merging workflow: {filename}")
        raise WorkflowExecutionError(f"Failed to update workflow: {exc}")


@router.delete("/api/workflows/{filename}/delete")
async def delete_workflow(filename: str):
    try:
        safe_filename = validate_workflow_filename(filename, require_yaml_extension=True)
        file_path = YAML_DIR / safe_filename
        if not file_path.exists() or not file_path.is_file():
            raise ResourceNotFoundError(
                "Workflow file not found",
                resource_type="workflow",
                resource_id=safe_filename,
            )

        try:
            file_path.unlink()
        except Exception as exc:
            logger = get_server_logger()
            logger.log_exception(exc, f"Failed to delete workflow file: {safe_filename}")
            raise WorkflowExecutionError("Failed to delete workflow file", details={"filename": safe_filename})

        logger = get_server_logger()
        logger.info(
            "Workflow file deleted",
            log_type=LogType.WORKFLOW,
            filename=safe_filename,
        )

        return {
            "status": "deleted",
            "filename": safe_filename,
            "message": f"Workflow '{safe_filename}' deleted successfully",
        }
    except ValidationError:
        raise
    except SecurityError:
        raise
    except ResourceNotFoundError:
        raise
    except Exception as exc:
        logger = get_server_logger()
        logger.log_exception(exc, f"Unexpected error deleting workflow: {filename}")
        raise WorkflowExecutionError(f"Failed to delete workflow: {exc}")


@router.post("/api/workflows/{filename}/rename")
async def rename_workflow_file(filename: str, request: WorkflowRenameRequest):
    try:
        rename_workflow(filename, request.new_filename, directory=YAML_DIR)
        return {
            "status": "success",
            "source": validate_workflow_filename(filename, require_yaml_extension=True),
            "target": validate_workflow_filename(request.new_filename, require_yaml_extension=True),
            "message": f"Workflow renamed to '{request.new_filename}' successfully",
        }
    except ValidationError:
        raise
    except SecurityError:
        raise
    except ResourceConflictError:
        raise
    except ResourceNotFoundError:
        raise
    except Exception as exc:
        logger = get_server_logger()
        logger.log_exception(exc, f"Unexpected error renaming workflow: {filename}")
        raise WorkflowExecutionError(f"Failed to rename workflow: {exc}")


@router.post("/api/workflows/{filename}/copy")
async def copy_workflow_file(filename: str, request: WorkflowCopyRequest):
    try:
        copy_workflow(filename, request.new_filename, directory=YAML_DIR)
        return {
            "status": "success",
            "source": validate_workflow_filename(filename, require_yaml_extension=True),
            "target": validate_workflow_filename(request.new_filename, require_yaml_extension=True),
            "message": f"Workflow copied to '{request.new_filename}' successfully",
        }
    except ValidationError:
        raise
    except SecurityError:
        raise
    except ResourceConflictError:
        raise
    except ResourceNotFoundError:
        raise
    except Exception as exc:
        logger = get_server_logger()
        logger.log_exception(exc, f"Unexpected error copying workflow: {filename}")
        raise WorkflowExecutionError(f"Failed to copy workflow: {exc}")


@router.get("/api/workflows/{filename}/get")
async def get_workflow_raw_content(filename: str):
    try:
        safe_filename = validate_workflow_filename(filename, require_yaml_extension=True)

        file_path = YAML_DIR / safe_filename
        if not file_path.exists() or not file_path.is_file():
            raise ResourceNotFoundError(
                "Workflow file not found",
                resource_type="workflow",
                resource_id=safe_filename,
            )

        with open(file_path, "r", encoding="utf-8") as handle:
            raw_content = handle.read()

        logger = get_server_logger()
        logger.info("Workflow file content retrieved", log_type=LogType.WORKFLOW, filename=safe_filename)
        return {"content": raw_content}
    except ValidationError:
        raise
    except SecurityError:
        raise
    except ResourceNotFoundError:
        raise
    except Exception as exc:
        logger = get_server_logger()
        logger.log_exception(exc, f"Unexpected error retrieving workflow: {filename}")
        raise WorkflowExecutionError(f"Failed to retrieve workflow: {exc}")

