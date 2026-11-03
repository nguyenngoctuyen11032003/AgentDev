"""Batch run API: request validation happens before the background run starts."""

import io

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import batch as batch_route


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(batch_route, "ensure_known_session", lambda session_id, require_connection=True: object())
    started = []
    monkeypatch.setattr(batch_route.asyncio, "create_task", lambda coro: (started.append(coro), coro.close()))
    app = FastAPI()
    app.include_router(batch_route.router)
    test_client = TestClient(app)
    test_client.started = started
    return test_client


def _post(client, **form):
    data = {"session_id": "s1", "yaml_file": "wf.yaml", "max_parallel": "5", **form}
    files = {"file": ("batch.csv", io.BytesIO(b"task\nhello\n"), "text/csv")}
    return client.post("/api/workflows/batch", data=data, files=files)


@pytest.mark.parametrize("value", ["0", "51"])
def test_max_parallel_out_of_range_is_rejected(client, value):
    response = _post(client, max_parallel=value)
    assert response.status_code == 400
    assert "max_parallel" in response.json()["detail"]
    assert client.started == []


@pytest.mark.parametrize("name", ["missing.yaml", "../escape.yaml", "notyaml.txt"])
def test_unknown_or_unsafe_workflow_is_rejected_up_front(client, name):
    response = _post(client, yaml_file=name)
    assert response.status_code == 400
    assert client.started == []


def test_valid_request_starts_the_batch(client, monkeypatch, tmp_path):
    monkeypatch.setattr(batch_route.BatchRunService, "_resolve_yaml_path", staticmethod(lambda name: tmp_path / name))
    response = _post(client)
    assert response.status_code == 200
    assert response.json()["task_count"] == 1
    assert len(client.started) == 1
