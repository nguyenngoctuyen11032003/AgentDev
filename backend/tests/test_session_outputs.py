"""Run page "Sản phẩm": a chat session's output folder browsed, served, opened and previewed like a Lab run."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev import paths
from agentdev.api.routes import session_outputs as route
from agentdev.api.services import app_preview as ap
from agentdev.api.services import session_outputs

SID = "0b6c2a8e-1111-2222-3333-444455556666"


@pytest.fixture()
def env(tmp_path, monkeypatch):
    warehouse = tmp_path / "warehouse"
    warehouse.mkdir()
    monkeypatch.setattr(paths, "WAREHOUSE_DIR", warehouse)
    monkeypatch.setattr(ap, "_allowed_root", lambda: warehouse.resolve())
    monkeypatch.setattr(ap, "_manager", ap.PreviewManager())
    sessions: dict = {}
    monkeypatch.setattr(session_outputs, "session_lookup", lambda sid: sessions.get(sid))
    opened: list = []
    monkeypatch.setattr(route, "open_on_machine", lambda target, reveal=False: opened.append((target, reveal)) or "opened")
    app = FastAPI()
    app.include_router(route.router)
    workspace = warehouse / f"session_{SID}" / "code_workspace"
    return SimpleNamespace(warehouse=warehouse, tmp=tmp_path, sessions=sessions, opened=opened, workspace=workspace,
                           client=TestClient(app))


def _write(path: Path, text: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _url(suffix: str, sid: str = SID) -> str:
    return f"/api/sessions/{sid}/outputs/{suffix}"


def test_nothing_written_yet(env):
    data = env.client.get(_url("files")).json()
    assert data["available"] is False and data["files"] == [] and data["location"] == "session"
    assert Path(data["root"]) == env.workspace.resolve()
    summary = env.client.get(_url("summary")).json()
    assert summary["available"] is False and summary["file_count"] == 0 and summary["preview"] is None
    assert env.client.get(_url("file?path=a.txt")).status_code == 404


def test_lists_session_workspace(env):
    _write(env.workspace / "index.html", "<h1>hi</h1>")
    _write(env.workspace / "src" / "app.js", "1")
    _write(env.workspace / "node_modules" / "pkg" / "x.js", "skip")
    data = env.client.get(_url("files")).json()
    assert data["available"] is True and data["location"] == "session"
    assert {f["path"]: f["kind"] for f in data["files"]} == {"index.html": "html", "src/app.js": "code"}
    assert data["project"]["type"] == "static" and data["project"]["can_preview"] is True
    summary = env.client.get(_url("summary")).json()
    assert summary["file_count"] == 2 and summary["kinds"] == {"html": 1, "code": 1}
    assert summary["project"]["type"] == "static"


def test_serves_file_with_sandbox_and_site_index(env):
    _write(env.workspace / "site" / "index.html", "<script>1</script>")
    _write(env.workspace / "notes.md", "# hi")
    page = env.client.get(_url("file?path=site/index.html"))
    assert page.status_code == 200 and "sandbox" in page.headers["content-security-policy"]
    assert env.client.get(_url("file?path=notes.md")).text == "# hi"
    site = env.client.get(_url("site/site/"))
    assert site.status_code == 200 and site.text == "<script>1</script>"
    assert "sandbox" in site.headers["content-security-policy"]


@pytest.mark.parametrize("bad", ["../secret.txt", "..\\secret.txt", "/etc/passwd", "C:/Windows/win.ini", "a/../../x"])
def test_path_confinement(env, bad):
    _write(env.workspace / "ok.txt")
    _write(env.workspace.parent.parent / "secret.txt", "nope")
    response = env.client.get(_url("file"), params={"path": bad})
    assert response.status_code in (400, 404)
    assert "nope" not in response.text


def test_invalid_session_id(env):
    assert env.client.get(_url("files", sid="..")).status_code in (400, 404)
    assert env.client.get(_url("files", sid="a:b")).status_code == 400


def test_cross_origin_blocked(env):
    _write(env.workspace / "a.txt")
    evil = {"Origin": "https://evil.example"}
    assert env.client.get(_url("files"), headers=evil).status_code == 403
    assert env.client.get(_url("file?path=a.txt"), headers=evil).status_code == 403
    assert env.client.post(_url("open"), json={"path": ""}, headers=evil).status_code == 403
    assert env.client.post(_url("preview"), headers=evil).status_code == 403
    assert env.client.get(_url("files"), headers={"Origin": "http://localhost:5174"}).status_code == 200


def test_opened_project_is_the_root(env):
    project = env.tmp / "my-project"
    _write(project / "README.md", "# p")
    env.sessions[SID] = SimpleNamespace(projects=[{"local_path": str(project)}])
    data = env.client.get(_url("files")).json()
    assert data["location"] == "project" and Path(data["root"]) == project.resolve()
    assert [f["path"] for f in data["files"]] == ["README.md"]
    assert env.client.get(_url("file?path=README.md")).text == "# p"


def test_open_on_machine_confined(env):
    _write(env.workspace / "a.txt")
    assert env.client.post(_url("open"), json={"path": "a.txt", "reveal": True}).json()["status"] == "opened"
    assert env.opened[-1] == ((env.workspace / "a.txt").resolve(), True)
    assert env.client.post(_url("open"), json={"path": "../x"}).status_code == 400


def test_open_root_creates_session_folder(env):
    assert not env.workspace.exists()
    assert env.client.post(_url("open"), json={"path": ""}).status_code == 200
    assert env.workspace.is_dir() and env.opened[-1][0] == env.workspace.resolve()


def test_linked_session_folder_refused(env):
    target = env.tmp / "elsewhere"
    _write(target / "code_workspace" / "secret.txt", "nope")
    link = env.warehouse / f"session_{SID}"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not available")
    assert env.client.get(_url("files")).status_code == 403


def test_static_preview_of_session_workspace(env):
    _write(env.workspace / "index.html", "x")
    assert env.client.get(_url("preview")).json()["status"] == "idle"
    started = env.client.post(_url("preview")).json()
    assert started["status"] == "running" and started["kind"] == "static"
    assert started["url"] == f"/api/sessions/{SID}/outputs/site/"
    assert env.client.get(_url("summary")).json()["preview"]["status"] == "running"
    assert env.client.delete(_url("preview")).json()["status"] == "stopped"


def test_preview_of_opened_project_keyed_per_session(env):
    project = env.tmp / "proj"
    _write(project / "index.html", "x")
    env.sessions[SID] = SimpleNamespace(projects=[{"local_path": str(project)}])
    started = env.client.post(_url("preview")).json()
    assert started["status"] == "running" and started["url"] == f"/api/sessions/{SID}/outputs/site/"
    other = "0b6c2a8e-9999-2222-3333-444455556666"
    assert env.client.get(_url("preview", sid=other)).json()["status"] == "idle"
    # The warehouse rule still holds for everyone else (the Lab): the project is outside it
    with pytest.raises(ap.PreviewError) as err:
        ap.get_preview_manager().start_dir(("job", 0), project)
    assert err.value.status_code == 403


def test_preview_refuses_home_folder(env, monkeypatch):
    home = env.tmp / "home"
    _write(home / "index.html", "x")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    env.sessions[SID] = SimpleNamespace(projects=[{"local_path": str(home)}])
    assert env.client.post(_url("preview")).status_code == 403


def test_preview_nothing_written(env):
    assert env.client.post(_url("preview")).status_code == 404


def test_attachments_hidden_and_cloned_project_app_found(env):
    _write(env.workspace / "attachments" / "attachments_manifest.json", "{}")
    _write(env.workspace / "attachments" / "abc" / "key.pem", "secret")
    _write(env.workspace / "projects" / "shop" / "README.md", "# shop")
    _write(env.workspace / "projects" / "shop" / "web" / "index.html", "<h1>shop</h1>")
    data = env.client.get(_url("files")).json()
    assert [f["path"] for f in data["files"]] == ["projects/shop/README.md", "projects/shop/web/index.html"]
    assert data["project"]["type"] == "static" and data["project"]["dir"] == "projects/shop"
    assert data["project"]["entry"] == "projects/shop/web/index.html"
    summary = env.client.get(_url("summary")).json()
    assert summary["file_count"] == 2 and summary["project"]["can_preview"] is True
    started = env.client.post(_url("preview")).json()
    assert started["url"] == f"/api/sessions/{SID}/outputs/site/projects/shop/web/index.html"
    assert env.client.get(started["url"]).text == "<h1>shop</h1>"
    env.client.delete(_url("preview"))
