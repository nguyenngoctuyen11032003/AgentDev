import sys
import textwrap

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agentdev.api.routes import connections as connections_route
from agentdev.connections import cli_login
from agentdev.connections.cli_login import CliLoginError, CliLoginManager

FAKE_PASTE = textwrap.dedent(
    """
    import sys
    print("Opening browser to sign in")
    print("If the browser didn't open, visit: https://example.test/oauth/authorize?state=abc", flush=True)
    code = sys.stdin.readline().strip()
    if code == "good-code-12345#state":
        print("Login successful")
        sys.exit(0)
    print("Login failed: That code wasn't accepted.")
    sys.exit(1)
    """
)

FAKE_DEVICE = textwrap.dedent(
    """
    import time
    print("Open https://example.test/device and enter the code:", flush=True)
    print("ABCD-12345", flush=True)
    time.sleep(30)
    """
)


@pytest.fixture()
def manager(tmp_path, monkeypatch):
    def make(script: str, mode: str, logged_in: bool = True):
        path = tmp_path / "fake_cli.py"
        path.write_text(script, encoding="utf-8")
        monkeypatch.setitem(cli_login.LOGIN_SPECS, "anthropic", {"args": [str(path)], "mode": mode})
        monkeypatch.setattr(cli_login, "find_cli", lambda binary: sys.executable)
        monkeypatch.setattr(cli_login, "detect_cli", lambda vendor: {"logged_in": logged_in})
        mgr = CliLoginManager()
        monkeypatch.setattr(cli_login, "_manager", mgr)
        return mgr

    return make


def test_paste_flow_success(manager):
    mgr = manager(FAKE_PASTE, "paste")
    started = mgr.start("anthropic")
    assert started["status"] == "waiting" and started["url"].startswith("https://example.test/")
    done = mgr.submit_code(started["sessionId"], "good-code-12345#state")
    assert done["status"] == "succeeded"
    with pytest.raises(CliLoginError):
        mgr.status(started["sessionId"])  # finished sessions are dropped


def test_paste_flow_wrong_code_reports_cli_message(manager):
    mgr = manager(FAKE_PASTE, "paste")
    sid = mgr.start("anthropic")["sessionId"]
    done = mgr.submit_code(sid, "wrong-code-99999")
    assert done["status"] == "failed" and "wasn't accepted" in done["message"]


def test_code_is_validated_before_reaching_the_cli(manager):
    mgr = manager(FAKE_PASTE, "paste")
    sid = mgr.start("anthropic")["sessionId"]
    for bad in ["", "short", "has space in it 123", "line\nbreak-12345", "x" * 600]:
        with pytest.raises(CliLoginError):
            mgr.submit_code(sid, bad)
    assert mgr.cancel(sid) is True


def test_device_mode_exposes_code_and_rejects_paste(manager):
    mgr = manager(FAKE_DEVICE, "device")
    started = mgr.start("anthropic")
    assert started["deviceCode"] == "ABCD-12345" and started["mode"] == "device"
    with pytest.raises(CliLoginError):
        mgr.submit_code(started["sessionId"], "good-code-12345")
    mgr.cancel(started["sessionId"])


def test_start_fails_cleanly_when_cli_missing(monkeypatch):
    monkeypatch.setattr(cli_login, "find_cli", lambda binary: None)
    with pytest.raises(CliLoginError):
        CliLoginManager().start("anthropic")
    with pytest.raises(CliLoginError):
        CliLoginManager().start("gemini")


def test_start_fails_when_cli_prints_no_url(manager, monkeypatch):
    monkeypatch.setattr(cli_login, "START_WAIT", 3.0)
    mgr = manager('print("boom: something broke")', "paste")
    with pytest.raises(CliLoginError, match="boom"):
        mgr.start("anthropic")


def test_http_routes(manager):
    manager(FAKE_PASTE, "paste")
    app = FastAPI()
    app.include_router(connections_route.router)
    client = TestClient(app)
    started = client.post("/api/connections/cli-login/start", json={"vendor": "anthropic"})
    assert started.status_code == 200
    sid = started.json()["sessionId"]
    assert client.get(f"/api/connections/cli-login/{sid}").json()["status"] == "waiting"
    assert client.post(f"/api/connections/cli-login/{sid}/code", json={"code": "bad code!"}).status_code == 422
    ok = client.post(f"/api/connections/cli-login/{sid}/code", json={"code": "good-code-12345#state"})
    assert ok.status_code == 200 and ok.json()["status"] == "succeeded"
    assert client.get(f"/api/connections/cli-login/{sid}").status_code == 404
    assert client.post("/api/connections/cli-login/start", json={"vendor": "gemini"}).status_code == 422
