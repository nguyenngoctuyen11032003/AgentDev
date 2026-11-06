"""Lab/Run previews (agent-built apps on 127.0.0.1 preview ports) must not be able to call the AgentDev API.

A preview page is code a model wrote. Loopback origins are otherwise trusted (CSRF check, CORS, websocket),
so the preview port range is excluded everywhere.
"""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agentdev.api.app import app
from agentdev.api.services import app_preview
from agentdev.connections.security import origin_allowed

LOCAL = {"Host": "localhost:6400"}
FIRST, LAST = app_preview.PORT_RANGE[0], app_preview.PORT_RANGE[-1]
PREVIEWS = [f"http://127.0.0.1:{FIRST}", f"http://localhost:{LAST}", f"http://[::1]:{FIRST + 5}"]


@pytest.fixture
def client():
    return TestClient(app)


@pytest.mark.parametrize("origin", PREVIEWS)
def test_preview_origin_is_not_allowed(origin):
    assert origin_allowed(origin) is False


def test_frontend_and_other_loopback_ports_still_allowed():
    assert origin_allowed("http://localhost:5173") and origin_allowed("http://127.0.0.1:5173")
    assert origin_allowed(f"http://127.0.0.1:{LAST + 1}") and origin_allowed(f"http://127.0.0.1:{FIRST - 1}")


def test_preview_origin_stays_blocked_even_if_listed(monkeypatch):
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", PREVIEWS[0])
    assert origin_allowed(PREVIEWS[0]) is False


@pytest.mark.parametrize("origin", PREVIEWS)
def test_preview_origin_post_is_rejected_on_the_whole_api(client, origin):
    # a route with its own origin check, and one without (only the app-wide middleware stands in the way)
    for path in ("/api/tools/local", "/api/workflows/upload/content"):
        res = client.post(path, json={}, headers={**LOCAL, "Origin": origin})
        assert res.status_code == 403, path
    res = client.get("/api/sessions", headers={**LOCAL, "Origin": origin})
    assert res.status_code == 403
    assert res.headers.get("access-control-allow-origin") is None


def test_preview_origin_preflight_gets_no_cors(client):
    res = client.options("/api/workflows/upload/content", headers={
        **LOCAL, "Origin": PREVIEWS[0], "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    assert res.headers.get("access-control-allow-origin") is None


def test_frontend_origin_still_works(client):
    res = client.get("/api/sessions", headers={**LOCAL, "Origin": "http://localhost:5173"})
    assert res.status_code == 200 and res.headers.get("access-control-allow-origin") == "http://localhost:5173"
    res = client.options("/api/workflows/upload/content", headers={
        **LOCAL, "Origin": "http://127.0.0.1:5173", "Access-Control-Request-Method": "POST"})
    assert res.headers.get("access-control-allow-origin") == "http://127.0.0.1:5173"


def test_preview_origin_websocket_is_closed(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws", headers={**LOCAL, "Origin": PREVIEWS[0]}):
            pass
    assert exc.value.code == 1008
