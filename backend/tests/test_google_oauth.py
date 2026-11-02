import base64
import hashlib
import json
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import connection_oauth
from agentdev.connections import google_oauth as g
from agentdev.connections import store as store_module
from agentdev.connections.store import ConnectionStore


class FakeResp:
    def __init__(self, body, status=200):
        self._b, self.status_code = body, status

    def json(self):
        return self._b


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")
    monkeypatch.setattr(store_module, "_store", ConnectionStore(tmp_path / "c.json"))
    g._pending.clear()
    g._results.clear()
    calls = []

    def fake(method, url, **kw):
        calls.append((url, kw["data"]))
        if kw["data"]["grant_type"] == "refresh_token":
            return FakeResp({"access_token": "new-at", "expires_in": 3600})
        return FakeResp({"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "scope": "s"})

    g.set_http(fake)
    yield calls
    g.set_http(None)


def client():
    app = FastAPI()
    app.include_router(connection_oauth.router)
    return TestClient(app)


def test_pkce_and_auth_url():
    v, c = g.generate_pkce()
    expected = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).decode().rstrip("=")
    assert c == expected
    res = g.start_login("L")
    q = parse_qs(urlparse(res["auth_url"]).query)
    assert q["state"] == [res["state"]]
    assert q["code_challenge_method"] == ["S256"]
    assert q["redirect_uri"] == ["http://localhost:8000/api/connections/oauth/google/callback"]


def test_state_single_use(env):
    st = g.start_login("L")["state"]
    tokens = g.complete_login(st, "code")
    assert tokens.access_token == "at" and tokens.refresh_token == "rt"
    assert env[0][1]["code_verifier"]
    with pytest.raises(g.OAuthError):
        g.complete_login(st, "code")


def test_state_expiry(monkeypatch):
    st = g.start_login("L")["state"]
    real = g._now()
    monkeypatch.setattr(g, "_now", lambda: real + g.PENDING_TTL_SECONDS + 1)
    with pytest.raises(g.OAuthError):
        g.complete_login(st, "code")


def test_unconfigured(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID")
    assert not g.is_configured()
    with pytest.raises(g.OAuthError):
        g.start_login("x")


def test_refresh_and_valid_token():
    t = g.OAuthTokens("old", "rt", 0, "a@b.c", "s")
    new = g.refresh(t)
    assert new.access_token == "new-at" and new.refresh_token == "rt" and new.email == "a@b.c"
    tok, upd = g.get_valid_access_token(t.to_dict())
    assert tok == "new-at" and upd["refresh_token"] == "rt"
    fresh = g.OAuthTokens("ok", "rt", g._now() + 3600).to_dict()
    assert g.get_valid_access_token(fresh) == ("ok", None)
    assert g.OAuthTokens.from_dict(fresh).to_dict() == fresh


def test_http_error_no_token_leak():
    g.set_http(lambda *a, **k: FakeResp({"error": "invalid_grant"}, 400))
    with pytest.raises(g.OAuthError) as e:
        g.refresh(g.OAuthTokens("a", "secret-rt"))
    assert "secret-rt" not in str(e.value)


def test_callback_success_persists():
    c = client()
    assert c.get("/api/connections/oauth/google/status").json() == {"configured": True}
    r = c.post("/api/connections/oauth/google/start", json={"label": "Mine"}).json()
    resp = c.get("/api/connections/oauth/google/callback", params={"code": "x", "state": r["state"]})
    assert "agentdev-oauth" in resp.text and '"ok": true' in resp.text
    conns = store_module.get_store().list()
    assert len(conns) == 1 and conns[0].auth_type == "oauth" and conns[0].vendor == "gemini"
    assert json.loads(conns[0].secret)["refresh_token"] == "rt"
    assert c.get("/api/connections/oauth/google/poll", params={"state": r["state"]}).json() == {"status": "done"}


def test_callback_bad_state_and_escaping():
    c = client()
    evil = "<script>alert(1)</script>"
    resp = c.get("/api/connections/oauth/google/callback", params={"code": evil, "state": evil})
    assert '"ok": false' in resp.text
    assert evil not in resp.text and "alert(1)" not in resp.text
    assert store_module.get_store().list() == []


def test_poll_pending():
    c = client()
    r = c.post("/api/connections/oauth/google/start", json={"label": "Mine"}).json()
    assert c.get("/api/connections/oauth/google/poll", params={"state": r["state"]}).json() == {"status": "pending"}


def test_gemini_bearer_path():
    from agentdev.runtime.node.agent.providers.gemini_provider import GeminiProvider

    p = GeminiProvider.__new__(GeminiProvider)
    p.api_key, p.base_url = "oauth-bearer:tok123", ""
    headers = p.create_client()._api_client._http_options.headers
    assert headers["Authorization"] == "Bearer tok123"
    assert "x-goog-api-key" not in headers

    p.api_key = "plain-key"
    headers = p.create_client()._api_client._http_options.headers
    assert headers["x-goog-api-key"] == "plain-key" and "Authorization" not in headers
