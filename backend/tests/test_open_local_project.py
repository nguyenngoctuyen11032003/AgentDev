"""Opening a project folder on this machine in place (like "Open Folder" in an editor)."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import local_folders
from agentdev.api.services.attachment_service import (
    IGNORED_PROJECT_DIRS,
    IGNORED_PROJECT_FILES,
    AttachmentService,
)
from agentdev.api.services.local_projects import (
    is_git_ignored,
    list_folders,
    opened_project_folder,
    parse_gitignore,
    scan_project,
)
from agentdev.utils.exceptions import ValidationError

SESSION = "sess1"


def _write(root: Path, rel: str, text: str = "x") -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "my-app"
    _write(root, "README.md")
    _write(root, "src/main.py")
    _write(root, "src/util/helpers.py")
    _write(root, "node_modules/lib/index.js")
    _write(root, ".git/HEAD")
    _write(root, "logs/today.log")
    _write(root, "keep.log")
    _write(root, ".gitignore", "logs/\n*.log\n!keep.log\n")
    _write(root, "src/.gitignore", "/generated.py\n")
    _write(root, "src/generated.py")
    return root


def _scan(root, **kwargs):
    return scan_project(str(root), ignored_dirs=IGNORED_PROJECT_DIRS, ignored_files=IGNORED_PROJECT_FILES, **kwargs)


def test_gitignore_rules_match_like_git():
    rules = parse_gitignore("*.log\n!keep.log\nbuild/\n/top.txt\ndocs/**/draft.md\n")
    assert is_git_ignored(rules, "a/b.log", False)
    assert not is_git_ignored(rules, "keep.log", False)
    assert is_git_ignored(rules, "x/build", True) and not is_git_ignored(rules, "x/build", False)
    assert is_git_ignored(rules, "top.txt", False) and not is_git_ignored(rules, "sub/top.txt", False)
    assert is_git_ignored(rules, "docs/a/b/draft.md", False)


def test_scan_skips_dependencies_and_gitignored_files(project):
    scan = _scan(project)
    files = sorted(rel for _abs, rel in scan.files)
    assert files == [".gitignore", "README.md", "keep.log", "src/.gitignore", "src/main.py", "src/util/helpers.py"]
    assert scan.skipped == 2  # node_modules, .git
    assert scan.gitignored == 2  # logs/, src/generated.py


def test_scan_refuses_huge_folders(project):
    with pytest.raises(ValidationError, match="limit"):
        _scan(project, max_files=2)


def test_list_folders_returns_only_folder_names(project):
    listing = list_folders(str(project))
    names = [item["name"] for item in listing["folders"]]
    assert names == ["logs", "node_modules", "src", ".git"]  # visible first, files never listed
    assert listing["parent"] == str(project.parent)
    with pytest.raises(ValidationError):
        list_folders("relative/path")
    with pytest.raises(ValidationError):
        list_folders(str(project / "README.md"))


def test_open_local_project_copies_nothing_and_points_at_the_folder(tmp_path, project):
    service = AttachmentService(root=tmp_path / "warehouse")
    record = service.open_local_project(SESSION, str(project))
    assert record.extra["local_path"] == str(project.resolve())
    assert record.extra["workspace_path"] == "."
    assert record.extra["file_count"] == 6
    overview = Path(record.ref.local_path).read_text(encoding="utf-8")
    assert "src/main.py" in overview and "node_modules" not in overview.split("## Folder tree")[1]
    assert not (tmp_path / "warehouse" / f"session_{SESSION}" / "code_workspace" / "projects").exists()

    # Re-opening the same folder is fine; a second, different folder is refused.
    service.open_local_project(SESSION, str(project), current_folder=str(project))
    other = tmp_path / "other"
    _write(other, "a.txt")
    with pytest.raises(ValidationError, match="already has a project folder"):
        service.open_local_project(SESSION, str(other), current_folder=str(project))


def test_opened_project_folder_reads_the_session_projects(project):
    session = SimpleNamespace(projects=[{"name": "x"}, {"name": "my-app", "local_path": str(project)}])
    assert opened_project_folder(session) == project
    assert opened_project_folder(SimpleNamespace(projects=[{"name": "x"}])) is None


def test_runtime_uses_the_opened_folder_as_code_workspace(tmp_path, project):
    from agentdev.workflow.runtime.runtime_builder import RuntimeBuilder

    graph = SimpleNamespace(
        name="g", log_level=None, directory=tmp_path / "session", config=SimpleNamespace(vars={})
    )
    runtime = RuntimeBuilder(graph).build(session_id=SESSION, workspace_root=project)
    assert runtime.code_workspace == project.resolve()
    assert runtime.global_state["python_workspace_root"] == project.resolve()
    # Attachments stay in the session directory, never inside the user's project
    assert not (project / "attachments").exists()
    assert (tmp_path / "session" / "code_workspace" / "attachments").is_dir()


def test_browse_api_blocks_other_websites(project):
    app = FastAPI()
    app.include_router(local_folders.router)
    client = TestClient(app)
    assert "locations" in client.get("/api/local-folders").json()
    assert client.get("/api/local-folders", params={"path": str(project)}).status_code == 200
    blocked = client.get(
        "/api/local-folders", params={"path": str(project)}, headers={"Origin": "https://evil.example"}
    )
    assert blocked.status_code == 403
