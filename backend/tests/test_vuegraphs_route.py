"""GET /api/vuegraphs/<name>: a workflow never laid out yet is a normal case, not an error."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import vuegraphs


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(vuegraphs.router)
    return TestClient(app)


def test_missing_layout_returns_200_with_null_content():
    response = _client().get("/api/vuegraphs/never_edited_workflow")
    assert response.status_code == 200
    assert response.json() == {"filename": "never_edited_workflow", "content": None}


def test_saved_layout_round_trips():
    client = _client()
    saved = client.post("/api/vuegraphs/upload/content", json={"filename": "wf_layout", "content": "{\"nodes\": []}"})
    assert saved.status_code == 200
    response = client.get("/api/vuegraphs/wf_layout")
    assert response.status_code == 200
    assert response.json()["content"] == "{\"nodes\": []}"
