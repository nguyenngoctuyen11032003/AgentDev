"""Files of an opened project: no auto-listing in the chat, safe open on this machine."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import artifacts
from agentdev.api.services.artifact_dispatcher import ArtifactDispatcher
from agentdev.api.services.artifact_events import ArtifactEvent, ArtifactEventQueue
from agentdev.api.services.local_projects import (
    is_noise_path,
    resolve_project_file,
    wants_files_shown,
)
from agentdev.utils.exceptions import ValidationError


@pytest.mark.parametrize(
    "path",
    ["CURRENT", "LOG", "next-development.log", "db/00000101.sst", "db/00000104.meta", "node_modules/a/b.js",
     ".git/HEAD", ".next/trace", "src/__pycache__/x.pyc", "MANIFEST-000004", "logs/today.txt", "a.exe"],
)
def test_noise_paths(path):
    assert is_noise_path(path)


@pytest.mark.parametrize("path", ["README.md", "GLOSSARY.md", "src/main.py", "docs/spec.pdf", "shot.png", ".github/ci.yml"])
def test_real_files_are_not_noise(path):
    assert not is_noise_path(path)


def test_intent_detection():
    assert wants_files_shown("Cho tôi xem file README.md")
    assert wants_files_shown("show me the report")
    assert not wants_files_shown("Thêm nút đăng nhập vào trang chủ")


def _event(rel, change="updated"):
    return ArtifactEvent(
        node_id="n", attachment_id="a", file_name=Path(rel).name, relative_path=rel,
        workspace_path=rel, mime_type=None, size=1, sha256="x", data_uri=None, change_type=change,
    )


class _Store:
    def __init__(self):
        self.queue = ArtifactEventQueue()

    def get_artifact_queue(self, _sid):
        return self.queue


def _dispatch(root, request, rels):
    store = _Store()
    dispatcher = ArtifactDispatcher("s", store, None, local_root=root)
    dispatcher.set_request(request)
    dispatcher.emit(dispatcher._filter_local([_event(r) for r in rels]))
    return [e.relative_path for e in store.queue._events], store.queue._events


def test_local_project_hides_files_unless_asked(tmp_path):
    rels = ["README.md", "LOG", "db/1.sst"]
    shown, _ = _dispatch(tmp_path, "Thêm tính năng đăng nhập", rels)
    assert shown == []
    shown, events = _dispatch(tmp_path, "cho tôi xem file README.md", rels)
    assert shown == ["README.md"]
    assert events[0].extra["open_local"] is True


def test_non_local_runs_keep_all_files():
    store = _Store()
    dispatcher = ArtifactDispatcher("s", store, None)
    dispatcher.emit(dispatcher._filter_local([_event("a.txt"), _event("LOG")]))
    assert len(store.queue._events) == 2


def test_resolve_project_file_blocks_escape(tmp_path):
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.py").write_text("x")
    (root / "LOG").write_text("x")
    (tmp_path / "secret.txt").write_text("x")
    assert resolve_project_file(root, "src/a.py") == (root / "src" / "a.py").resolve()
    for bad in ["../secret.txt", "src/../../secret.txt", str(tmp_path / "secret.txt"), "", "missing.txt", "LOG"]:
        with pytest.raises(ValidationError):
            resolve_project_file(root, bad)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "a.md").write_text("hi")
    (tmp_path / "secret.txt").write_text("x")
    session = SimpleNamespace(projects=[{"local_path": str(root)}])
    other = SimpleNamespace(projects=[])
    sessions = {"s1": session, "s2": other}
    manager = SimpleNamespace(session_store=SimpleNamespace(get_session=sessions.get))
    monkeypatch.setattr(artifacts, "get_websocket_manager", lambda: manager)
    opened = []
    monkeypatch.setattr(artifacts, "open_on_machine", lambda target, reveal=False: opened.append(target) or "opened")
    app = FastAPI()
    app.include_router(artifacts.router)
    test_client = TestClient(app)
    test_client.opened = opened
    return test_client


def test_open_endpoint(client):
    url = "/api/sessions/{}/local-files/open"
    assert client.post(url.format("s1"), json={"relative_path": "a.md"}).status_code == 200
    assert len(client.opened) == 1
    assert client.post(url.format("s1"), json={"relative_path": "../secret.txt"}).status_code == 400
    assert client.post(url.format("s2"), json={"relative_path": "a.md"}).status_code == 404
    assert client.post(url.format("nope"), json={"relative_path": "a.md"}).status_code == 404
    blocked = client.post(url.format("s1"), json={"relative_path": "a.md"}, headers={"Origin": "https://evil.example"})
    assert blocked.status_code == 403
    assert len(client.opened) == 1
