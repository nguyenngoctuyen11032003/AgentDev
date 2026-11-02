"""Project (whole folder) uploads: structure, filtering, limits and path safety."""

import asyncio
import io
from pathlib import Path

import pytest
from starlette.datastructures import UploadFile

from agentdev.api.services.attachment_service import AttachmentService
from agentdev.utils.exceptions import ValidationError

SESSION = "sess1"


def _upload(content: bytes, name: str = "f") -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=name)


def _save(service, project_id, entries):
    files = [_upload(data, Path(path).name) for path, data in entries]
    paths = [path for path, _ in entries]
    return asyncio.run(service.save_project_files(SESSION, project_id, files, paths))


@pytest.fixture()
def service(tmp_path):
    return AttachmentService(root=tmp_path)


def _project_dir(tmp_path, project_id):
    return tmp_path / f"session_{SESSION}" / "code_workspace" / "projects" / project_id


def test_upload_keeps_structure_and_skips_ignored(service, tmp_path):
    project = service.create_project(SESSION, "my-app")
    assert project == {"project_id": "my-app", "workspace_path": "projects/my-app"}

    result = _save(
        service,
        "my-app",
        [
            ("src/main.js", b"console.log(1)"),
            ("src\\components\\App.vue", b"<template/>"),
            ("package.json", b"{}"),
            ("node_modules/vue/index.js", b"x"),
            (".git/HEAD", b"ref"),
            ("src/.DS_Store", b"junk"),
        ],
    )
    assert result["saved"] == 3 and result["skipped"] == 3

    root = _project_dir(tmp_path, "my-app")
    assert (root / "src" / "main.js").read_bytes() == b"console.log(1)"
    assert (root / "src" / "components" / "App.vue").exists()
    assert not (root / "node_modules").exists()
    assert not (root / ".git").exists()


def test_create_project_names_are_unique_and_sanitised(service):
    assert service.create_project(SESSION, "web")["project_id"] == "web"
    assert service.create_project(SESSION, "web")["project_id"] == "web_2"
    assert service.create_project(SESSION, "../../evil")["project_id"] == "evil"
    assert service.create_project(SESSION, "")["project_id"] == "project"


@pytest.mark.parametrize(
    "bad_path",
    ["../escape.txt", "a/../../escape.txt", "/etc/passwd", "C:/Windows/x", "C:\\x", "a/b:c"],
)
def test_rejects_paths_escaping_the_project(service, tmp_path, bad_path):
    service.create_project(SESSION, "app")
    with pytest.raises(ValidationError):
        _save(service, "app", [(bad_path, b"x")])
    assert not (tmp_path / "escape.txt").exists()


def test_rejects_unknown_or_traversing_project_id(service):
    with pytest.raises(ValidationError):
        _save(service, "missing", [("a.txt", b"x")])
    with pytest.raises(ValidationError):
        _save(service, "..", [("a.txt", b"x")])


def test_file_and_size_limits(service):
    service.max_project_files = 2
    service.create_project(SESSION, "app")
    _save(service, "app", [("a.txt", b"1"), ("b.txt", b"2")])
    with pytest.raises(ValidationError):
        _save(service, "app", [("c.txt", b"3")])

    service.max_project_files = 100
    service.max_project_bytes = 10
    service.create_project(SESSION, "big")
    with pytest.raises(ValidationError):
        _save(service, "big", [("huge.bin", b"x" * 11)])


def test_finalize_registers_overview_attachment(service, tmp_path):
    service.create_project(SESSION, "shop")
    _save(service, "shop", [("README.md", b"# Shop"), ("src/index.html", b"<html/>")])

    record = service.finalize_project(SESSION, "shop")

    assert record.ref.mime_type == "text/markdown"
    assert record.extra["kind"] == "project"
    assert record.extra["workspace_path"] == "projects/shop"
    assert record.extra["file_count"] == 2
    overview = Path(record.ref.local_path).read_text(encoding="utf-8")
    assert "projects/shop/" in overview
    assert "index.html" in overview and "README.md" in overview

    # The overview is a regular registered upload, so python nodes can resolve it too.
    resolved = service.resolve_uploaded_paths(SESSION, [record.ref.attachment_id])
    assert resolved == [str(Path(record.ref.local_path).resolve())]


def test_finalize_empty_project_fails(service):
    service.create_project(SESSION, "empty")
    with pytest.raises(ValidationError):
        service.finalize_project(SESSION, "empty")


def test_mismatched_files_and_paths(service):
    service.create_project(SESSION, "app")
    with pytest.raises(ValidationError):
        asyncio.run(service.save_project_files(SESSION, "app", [_upload(b"x")], []))
