"""A session that opened no project saves its work in <PROJECTS_DIR>/<name>/ (see utils/project_folders.py)."""

import asyncio

from agentdev import paths
from agentdev.api.services import workflow_run_service as run_service_module
from agentdev.api.services.local_projects import opened_project_folder
from agentdev.utils import project_folders

from tests.test_run_lifecycle import FakeSocketManager, run_service  # noqa: F401  (fixture)


def _run(service, patch_run, session_id, prompt, seen):
    async def run(self, task_input):
        seen.append({"workspace": self.runtime_context.code_workspace, "graph_dir": self.graph.directory})

    patch_run(run)
    asyncio.run(service.start_workflow(session_id, "solo.yaml", prompt, FakeSocketManager()))


def test_session_without_a_project_gets_a_named_folder(run_service, tmp_path):
    service, store, patch_run = run_service
    seen = []
    _run(service, patch_run, "s-new", "Làm web quản lý công việc nhóm", seen)
    session = store.get_session("s-new")
    folder = opened_project_folder(session)
    assert folder is not None and folder.parent == (tmp_path / "AgentDev").resolve()
    assert folder.name == "lam-web-quan-ly-cong-viec-nhom"
    assert seen[0]["workspace"] == folder  # the agents' code workspace IS the project root
    # AgentDev's own files go to <project>/.agentdev/session_<id>, not into the code
    assert seen[0]["graph_dir"] == folder / ".agentdev" / "session_s-new"
    assert [p.name for p in folder.iterdir()] == [".agentdev"]
    assert not (tmp_path / "WareHouse" / "session_s-new" / "code_workspace" / "generated").exists()


def test_follow_up_reuses_the_same_folder(run_service, tmp_path):
    service, store, patch_run = run_service
    seen = []
    _run(service, patch_run, "s-two", "Làm app đặt bàn", seen)
    _run(service, patch_run, "s-two", "Thêm trang thống kê", seen)
    folders = [p.name for p in (tmp_path / "AgentDev").iterdir()]
    assert folders == ["lam-app-dat-ban"]
    assert seen[0]["workspace"] == seen[1]["workspace"]


def test_two_sessions_never_share_a_folder(run_service, tmp_path):
    service, store, patch_run = run_service
    seen = []
    _run(service, patch_run, "s-a", "Làm app đặt bàn", seen)
    _run(service, patch_run, "s-b", "Làm app đặt bàn", seen)
    assert seen[0]["workspace"] != seen[1]["workspace"]
    assert sorted(p.name for p in (tmp_path / "AgentDev").iterdir()) == ["lam-app-dat-ban", "lam-app-dat-ban-2"]


def test_session_from_before_project_folders_keeps_its_warehouse_workspace(run_service, tmp_path):
    service, store, patch_run = run_service
    old = tmp_path / "WareHouse" / "session_s-old" / "code_workspace"
    old.mkdir(parents=True)
    (old / "index.html").write_text("<h1>old</h1>", encoding="utf-8")
    seen = []
    _run(service, patch_run, "s-old", "Sửa trang cũ", seen)
    assert seen[0]["workspace"] == old.resolve()
    assert not (tmp_path / "AgentDev").exists()


def test_a_folder_the_user_opened_is_used_as_is_and_gets_no_agentdev_dir(run_service, tmp_path):
    service, store, patch_run = run_service
    mine = tmp_path / "my-repo"
    mine.mkdir()
    service.attachment_service.prepare_session_workspace("s-mine")
    record = service.attachment_service.open_local_project("s-mine", str(mine))
    store.register_project("s-mine", "solo.yaml", {"name": "my-repo", "attachment_id": record.ref.attachment_id,
                                                    "local_path": str(mine)})
    seen = []
    _run(service, patch_run, "s-mine", "Sửa lỗi", seen)
    assert seen[0]["workspace"] == mine.resolve()
    assert not (mine / ".agentdev").exists()
    assert not project_folders.projects_root().exists()


def test_falls_back_to_the_warehouse_when_the_folder_cannot_be_made(run_service, tmp_path, monkeypatch):
    service, store, patch_run = run_service
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setattr(paths, "PROJECTS_DIR", blocker / "AgentDev")  # a path below a file: mkdir fails
    seen = []
    _run(service, patch_run, "s-ro", "Làm app", seen)
    assert seen[0]["workspace"] == (tmp_path / "WareHouse" / "session_s-ro" / "code_workspace").resolve()


def test_agent_git_cannot_climb_out_of_a_project_folder(tmp_path):
    from agentdev.utils.git_guard import with_git_ceiling

    folder = project_folders.create_project_dir("Web")
    env = with_git_ceiling({}, str(folder))
    assert env["GIT_CEILING_DIRECTORIES"].split(__import__("os").pathsep)[0] == str(project_folders.projects_root().resolve())


def test_agentdev_internal_files_are_not_listed_as_product_files(tmp_path):
    from agentdev.api.services import lab_outputs

    folder = project_folders.create_project_dir("Web")
    (folder / "index.html").write_text("<h1>x</h1>", encoding="utf-8")
    (folder / ".agentdev" / "execution_logs.json").write_text("{}", encoding="utf-8")
    assert [rel for rel, _size in lab_outputs._walk(folder)] == ["index.html"]
