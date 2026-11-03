"""Regressions found while auditing agentdev/api."""

import os
import sqlite3
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import artifacts as artifacts_route
from agentdev.api.services import vuegraphs_storage
from agentdev.api.services.workflow_storage import _update_workflow_id


def test_rename_updates_existing_id_line():
    out = _update_workflow_id("id: old_name\nname: x\n", "new_name")
    assert out == "id: new_name\nname: x\n"
    assert out.count("id:") == 1


def test_rename_adds_id_when_missing():
    assert _update_workflow_id("name: x\n", "n1").startswith("id: n1\n")


def test_vuegraph_db_connections_are_closed(monkeypatch, tmp_path):
    db = tmp_path / "g.db"
    monkeypatch.setenv("VUEGRAPHS_DB_PATH", str(db))
    closed = []
    real = sqlite3.connect

    class Tracked:
        def __init__(self, *a, **k):
            self.c = real(*a, **k)

        def __getattr__(self, n):
            return getattr(self.c, n)

        def __enter__(self):
            self.c.__enter__()
            return self

        def __exit__(self, *a):
            return self.c.__exit__(*a)

        def close(self):
            closed.append(1)
            self.c.close()

    monkeypatch.setattr(vuegraphs_storage.sqlite3, "connect", lambda *a, **k: Tracked(*a, **k))
    vuegraphs_storage.save_vuegraph_content("a.yaml", "x")
    assert vuegraphs_storage.fetch_vuegraph_content("a.yaml") == "x"
    assert len(closed) >= 3  # init + save + fetch


def test_artifact_stream_with_non_ascii_name(monkeypatch, tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("hello", encoding="utf-8")
    record = SimpleNamespace(
        ref=SimpleNamespace(local_path=str(f), mime_type="text/plain", name="báo cáo \"Q1\".txt"),
        extra={},
    )
    store = SimpleNamespace(get=lambda _id: record)
    manager = SimpleNamespace(attachment_service=SimpleNamespace(get_attachment_store=lambda sid: store))
    monkeypatch.setattr(artifacts_route, "_get_session_and_queue", lambda sid: (manager, None))
    app = FastAPI()
    app.include_router(artifacts_route.router)
    resp = TestClient(app).get("/api/sessions/s1/artifacts/a1?mode=stream&download=true")
    assert resp.status_code == 200
    assert resp.text == "hello"
    assert resp.headers["content-disposition"].startswith("attachment")


def test_create_local_tool_rejects_cross_origin():
    """A foreign website must not be able to write Python tool files (CSRF)."""
    from agentdev.api.routes import tools as tools_route

    app = FastAPI()
    app.include_router(tools_route.router)
    res = TestClient(app).post(
        "/api/tools/local",
        json={"filename": "evil", "content": "x = 1"},
        headers={"origin": "https://evil.example"},
    )
    assert res.status_code == 403


def test_batch_upload_over_limit_is_rejected(monkeypatch):
    from agentdev.api.routes import batch as batch_route

    monkeypatch.setattr(batch_route, "ensure_known_session", lambda session_id, require_connection=True: object())
    monkeypatch.setattr(batch_route, "MAX_BATCH_UPLOAD_BYTES", 10)
    monkeypatch.setattr(batch_route.BatchRunService, "_resolve_yaml_path", staticmethod(lambda name: name))
    app = FastAPI()
    app.include_router(batch_route.router)
    res = TestClient(app).post(
        "/api/workflows/batch",
        data={"session_id": "s", "yaml_file": "x.yaml"},
        files={"file": ("b.csv", b"task\n" + b"a" * 100, "text/csv")},
    )
    assert res.status_code == 413
