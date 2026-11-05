"""Local-only hardening: Host/Origin checks, CORS, websocket origin, log redaction."""

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agentdev.api.app import app

LOCAL = {"Host": "localhost:6400"}


@pytest.fixture
def client():
    return TestClient(app)


def test_normal_localhost_host_ok(client):
    assert client.get("/api/sessions", headers=LOCAL).status_code == 200


def test_no_origin_no_host_issue_ok(client):
    assert client.get("/api/sessions", headers={"Host": "127.0.0.1:6400"}).status_code == 200
    assert client.get("/api/sessions", headers={"Host": "[::1]:6400"}).status_code == 200


def test_evil_host_and_origin_blocked(client):
    r = client.get("/api/sessions", headers={"Host": "evil.com", "Origin": "http://evil.com"})
    assert r.status_code == 400


def test_evil_host_without_origin_blocked(client):
    assert client.get("/api/sessions", headers={"Host": "rebind.evil.com:6400"}).status_code == 400


def test_evil_origin_has_no_cors_wildcard(client):
    r = client.get("/api/sessions", headers={**LOCAL, "Origin": "http://evil.com"})
    assert r.headers.get("access-control-allow-origin") not in ("*", "http://evil.com")


def test_loopback_origin_gets_cors(client):
    r = client.get("/api/sessions", headers={**LOCAL, "Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_require_local_origin_rejects_same_host_evil():
    from fastapi import HTTPException
    from starlette.requests import Request

    def req(host, origin):
        h = [(b"host", host.encode()), (b"origin", origin.encode())]
        return Request({"type": "http", "headers": h})

    from agentdev.connections.security import require_local_origin

    with pytest.raises(HTTPException):
        require_local_origin(req("evil.com", "http://evil.com"))
    require_local_origin(req("localhost:6400", "http://127.0.0.1:5173"))


def test_allowed_hosts_env(client, monkeypatch):
    monkeypatch.setenv("AGENTDEV_ALLOWED_HOSTS", "backend, my.lan")
    assert client.get("/api/sessions", headers={"Host": "backend:6400"}).status_code == 200
    assert client.get("/api/sessions", headers={"Host": "my.lan"}).status_code == 200


def test_cors_env_origin_allowed_for_csrf_check(monkeypatch):
    from starlette.requests import Request
    from agentdev.connections.security import require_local_origin

    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "https://app.example.com")
    h = [(b"host", b"localhost:6400"), (b"origin", b"https://app.example.com")]
    require_local_origin(Request({"type": "http", "headers": h}))


def test_ws_evil_origin_closed(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws", headers={**LOCAL, "Origin": "http://evil.com"}):
            pass
    assert exc.value.code == 1008


def test_ws_evil_host_closed(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws", headers={"Host": "evil.com"}):
            pass
    assert exc.value.code == 1008


def test_ws_no_origin_connects(client):
    with client.websocket_connect("/ws", headers=LOCAL):
        pass


def test_log_redacts_oauth_query(client, monkeypatch):
    from agentdev.utils import middleware

    seen = {}

    class L:
        def log_request(self, method, url, **kw):
            seen["url"] = url
            seen.update(kw)

        def log_response(self, *a, **k):
            pass

    monkeypatch.setattr(middleware, "get_server_logger", lambda: L())
    client.get("/api/sessions?code=SECRET1&state=SECRET2&token=SECRET3&x=ok", headers=LOCAL)
    blob = repr(seen)
    assert "SECRET" not in blob
    assert seen["query_params"]["x"] == "ok"


# ---- round 3 hardening ----
def test_redact_text_patterns():
    from agentdev.utils.middleware import redact_query_string

    out = redact_query_string("%63ode=S1&CODE=S2&id_token=S3&refresh_token=S4&client_secret=S5&api_key=S6&password=S7&x=ok&state=a&state=b")
    for s in ("S1", "S2", "S3", "S4", "S5", "S6", "S7", "=a&", "=b"):
        assert s not in out
    assert "x=ok" in out


def test_redact_query_dict_and_repeated():
    from agentdev.utils.middleware import redact_query

    r = redact_query({"Authorization": "x", "Api_Key": "y", "keep": "ok"})
    assert r["Authorization"] == "***" and r["Api_Key"] == "***" and r["keep"] == "ok"


def test_redact_url_repeated_params():
    from starlette.requests import Request
    from agentdev.utils.middleware import redact_url

    req = Request({"type": "http", "method": "GET", "path": "/x", "query_string": b"code=A1&code=B2&n=1&n=2",
                   "headers": [(b"host", b"localhost")], "scheme": "http", "server": ("localhost", 80)})
    u = redact_url(req)
    assert "A1" not in u and "B2" not in u and "n=1" in u and "n=2" in u


def test_access_log_filter_redacts():
    import logging
    from agentdev.utils.middleware import AccessLogRedactFilter

    rec = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                            ("127.0.0.1:1", "GET", "/api/connections/oauth/google/callback?code=SECRET&state=S2", "1.1", 200), None)
    assert AccessLogRedactFilter().filter(rec) is True
    assert "SECRET" not in rec.getMessage() and "S2" not in rec.getMessage()
    assert "/callback?" in rec.getMessage()


def test_access_log_filter_installed_on_import():
    import logging
    import agentdev.api.app  # noqa: F401
    from agentdev.utils.middleware import AccessLogRedactFilter

    assert any(isinstance(f, AccessLogRedactFilter) for f in logging.getLogger("uvicorn.access").filters)


@pytest.mark.parametrize("h", ["localhost:6497@evil.com", "evil.com\@localhost", "localhost:99999x", "local host", "a/b"])
def test_host_regex_rejects_malformed(h):
    from agentdev.connections.security import host_allowed

    assert not host_allowed(h)


def test_host_regex_accepts_good():
    from agentdev.connections.security import host_allowed

    assert host_allowed("LOCALHOST:6400") and host_allowed("127.0.0.1") and host_allowed("[::1]:6400")


def test_duplicate_host_header_rejected(client):
    from starlette.requests import Request
    from fastapi import HTTPException
    from agentdev.connections.security import require_local_origin

    h = [(b"host", b"localhost"), (b"host", b"evil.com")]
    with pytest.raises(HTTPException):
        require_local_origin(Request({"type": "http", "headers": h}))

    import asyncio
    from agentdev.api.bootstrap import HostGuardMiddleware

    sent = []

    async def app(scope, receive, send):
        sent.append("app")

    async def send(m):
        sent.append(m)

    asyncio.run(HostGuardMiddleware(app)({"type": "http", "headers": h}, None, send))
    assert "app" not in sent
