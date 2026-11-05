"""Lab app preview: ports, launch-plan detection, and a real start/stop of a tiny Python server."""

import json
import os
import socket
import subprocess
import time
from pathlib import Path

import pytest

from agentdev.api.services import app_preview as ap


def _write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _pkg(directory: Path, **data) -> None:
    _write(directory / "package.json", json.dumps(data))


# --- ports ---------------------------------------------------------------

def test_allocate_port_skips_reserved_and_busy(monkeypatch):
    busy = socket.socket()
    busy.bind(("127.0.0.1", 0))
    busy.listen(1)
    taken = busy.getsockname()[1]
    try:
        assert not ap.port_is_free(taken)
        monkeypatch.setattr(ap, "PORT_RANGE", [5173, 6400, taken, 47150])
        port = ap.allocate_port()
        assert port not in ap.RESERVED_PORTS and port != taken
        assert port == 47150 or not ap.port_is_free(47150)
    finally:
        busy.close()


def test_allocate_port_respects_exclude_and_range():
    port = ap.allocate_port()
    assert port in ap.PORT_RANGE
    assert ap.allocate_port({port}) != port


def test_allocate_port_exhausted(monkeypatch):
    monkeypatch.setattr(ap, "PORT_RANGE", [5173, 5174, 6400])
    with pytest.raises(ap.PreviewError):
        ap.allocate_port()


# --- detection -------------------------------------------------------------

def test_static_site(tmp_path):
    _write(tmp_path / "index.html", "<h1>hi</h1>")
    plan = ap.detect_launch_plan(tmp_path)
    assert plan.kind == "static" and plan.entry == "index.html" and not plan.processes


def test_static_in_subfolder(tmp_path):
    _write(tmp_path / "game" / "index.html", "<h1>hi</h1>")
    plan = ap.detect_launch_plan(tmp_path)
    assert plan.kind == "static" and plan.entry == "game/index.html"


def test_vite_app_gets_port_flags(tmp_path):
    _pkg(tmp_path, scripts={"dev": "vite", "build": "vite build"}, devDependencies={"vite": "^5"})
    _write(tmp_path / "vite.config.js", "export default { server: { port: 5173 } }")
    _write(tmp_path / "index.html", "<div id=app></div>")
    plan = ap.detect_launch_plan(tmp_path)
    assert plan.kind == "node" and "Vite" in plan.summary
    cmd = plan.processes[0].cmd
    assert cmd[1:4] == ["run", "dev", "--"]
    assert cmd[-5:] == ["--port", "{port}", "--strictPort", "--host", "127.0.0.1"]
    assert plan.installs == [tmp_path]  # no node_modules yet


def test_vite_with_custom_script_uses_vite_directly(tmp_path):
    _pkg(tmp_path, scripts={"dev": "concurrently 'vite' 'node api.js'"}, devDependencies={"vite": "^5"})
    (tmp_path / "node_modules").mkdir()
    plan = ap.detect_launch_plan(tmp_path)
    cmd = plan.processes[0].cmd
    assert "vite" in cmd and "--strictPort" in cmd and "run" not in cmd
    assert plan.installs == []


def test_next_app(tmp_path):
    _pkg(tmp_path, scripts={"dev": "next dev"}, dependencies={"next": "14", "react": "18"})
    plan = ap.detect_launch_plan(tmp_path)
    assert plan.kind == "node" and "Next" in plan.summary
    assert plan.processes[0].cmd[-4:] == ["-p", "{port}", "-H", "127.0.0.1"]


def test_plain_node_server_uses_port_env(tmp_path):
    _pkg(tmp_path, main="server.js")
    _write(tmp_path / "server.js", "require('http').createServer().listen(process.env.PORT)")
    plan = ap.detect_launch_plan(tmp_path)
    assert plan.kind == "node"
    assert plan.processes[0].cmd[-1] == "server.js"
    assert plan.processes[0].env["PORT"] == "{port}"


def test_monorepo_client_server_with_proxy(tmp_path):
    _pkg(tmp_path, workspaces=["client", "server"], scripts={"dev": "concurrently ..."})
    _pkg(tmp_path / "client", scripts={"dev": "vite"}, devDependencies={"vite": "^5"})
    _write(tmp_path / "client" / "vite.config.ts",
           "export default { server: { port: 5173, proxy: { '/api': 'http://localhost:3001' } } }")
    _pkg(tmp_path / "server", scripts={"dev": "node index.js"}, dependencies={"express": "4"})
    plan = ap.detect_launch_plan(tmp_path)
    assert plan.kind == "node" and "Vite" in plan.summary
    roles = {p.role: p for p in plan.processes}
    assert roles["server"].preferred_port == 3001
    assert roles["server"].cwd == tmp_path / "server"
    assert roles["main"].cwd == tmp_path / "client"
    assert roles["main"].env["SERVER_PORT"] == "{server_port}"
    assert plan.installs == [tmp_path]  # workspaces: one install at the root


def test_fastapi_app(tmp_path):
    _write(tmp_path / "app" / "main.py", "from fastapi import FastAPI\napi = FastAPI()\n")
    plan = ap.detect_launch_plan(tmp_path)
    assert plan.kind == "python" and "FastAPI" in plan.summary
    cmd = plan.processes[0].cmd
    assert cmd[1:4] == ["-m", "uvicorn", "app.main:api"] and cmd[-1] == "{port}"


def test_flask_app(tmp_path):
    _write(tmp_path / "app.py", "from flask import Flask\napp = Flask(__name__)\n")
    _write(tmp_path / "requirements.txt", "flask\n")
    plan = ap.detect_launch_plan(tmp_path)
    assert plan.kind == "python" and "Flask" in plan.summary
    assert "app:app" in plan.processes[0].cmd and plan.notes


def test_python_script_without_server_is_not_runnable(tmp_path):
    _write(tmp_path / "main.py", "print('hello')\n")
    assert ap.detect_launch_plan(tmp_path).kind == "none"


def test_single_app_in_subfolder(tmp_path):
    _pkg(tmp_path / "todo-app", scripts={"dev": "vite"}, devDependencies={"vite": "^5"})
    _write(tmp_path / "README.md", "x")
    plan = ap.detect_launch_plan(tmp_path)
    assert plan.kind == "node" and plan.processes[0].cwd == tmp_path / "todo-app"


def test_env_drops_secrets(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    monkeypatch.setenv("AGENTDEV_STORAGE_DIR", "x")
    monkeypatch.setenv("PORT", "6400")
    env = ap.preview_env({"PORT": "47100"})
    assert "OPENAI_API_KEY" not in env and "GITHUB_TOKEN" not in env and "AGENTDEV_STORAGE_DIR" not in env
    assert env["PORT"] == "47100" and env["HOST"] == "127.0.0.1" and env["BROWSER"] == "none"


# --- manager ---------------------------------------------------------------

@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    root = tmp_path / "warehouse"
    root.mkdir()
    monkeypatch.setattr(ap, "_allowed_root", lambda: root.resolve())
    return root


def test_static_preview_has_no_process(warehouse):
    run = warehouse / "lab_x_1" / "code_workspace"
    _write(run / "site" / "index.html", "<h1>hi</h1>")
    mgr = ap.PreviewManager()
    result = mgr.start_dir(("job", 0), run, "/api/lab/jobs/job/runs/0/site/")
    assert result["status"] == "running" and result["kind"] == "static"
    assert result["url"] == "/api/lab/jobs/job/runs/0/site/site/index.html"
    assert result["port"] is None
    assert not mgr.has_live_preview(warehouse / "lab_x_1")


def test_refuses_dir_outside_warehouse(warehouse, tmp_path):
    outside = tmp_path / "elsewhere"
    _write(outside / "index.html", "x")
    with pytest.raises(ap.PreviewError) as err:
        ap.PreviewManager().start_dir(("job", 0), outside)
    assert err.value.status_code == 403


def test_nothing_to_run(warehouse):
    run = warehouse / "lab_x_2"
    _write(run / "notes.md", "x")
    with pytest.raises(ap.PreviewError) as err:
        ap.PreviewManager().start_dir(("job", 0), run)
    assert err.value.status_code == 422


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, check=False).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


_SERVER = '''
import http.server, os, subprocess, sys
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
open("child.pid", "w").write(str(child.pid))
if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", int(os.environ["PORT"])),
                                    http.server.SimpleHTTPRequestHandler).serve_forever()
'''


def test_python_server_end_to_end_and_tree_kill(warehouse):
    run = warehouse / "lab_x_3" / "code_workspace"
    _write(run / "server.py", _SERVER)
    _write(run / "index.html", "<h1>hello preview</h1>")
    mgr = ap.PreviewManager()
    first = mgr.start_dir(("job", 3), run)
    assert first["kind"] == "python" and first["status"] == "starting"
    deadline = time.monotonic() + 30
    status = first
    while time.monotonic() < deadline:
        status = mgr._previews[("job", 3)].to_dict()
        if status["status"] in ("running", "failed"):
            break
        time.sleep(0.2)
    assert status["status"] == "running", status["log_tail"]
    port = status["port"]
    assert port in ap.PORT_RANGE and port not in ap.RESERVED_PORTS
    assert status["url"] == f"http://localhost:{port}/"
    import urllib.request

    body = urllib.request.urlopen(f"http://127.0.0.1:{port}/index.html", timeout=5).read().decode()
    assert "hello preview" in body
    assert mgr.has_live_preview(warehouse / "lab_x_3")
    # Starting again returns the same preview.
    assert mgr.start_dir(("job", 3), run)["port"] == port

    child_pid = int((run / "child.pid").read_text())
    assert _pid_alive(child_pid)
    assert mgr.stop_for_dir(warehouse / "lab_x_3") == 1
    assert not mgr.has_live_preview(warehouse / "lab_x_3")
    assert not ap.port_accepts(port)
    for _ in range(20):
        if not _pid_alive(child_pid):
            break
        time.sleep(0.2)
    assert not _pid_alive(child_pid), "grandchild process survived the tree kill"


def test_failed_start_reports_error(warehouse):
    run = warehouse / "lab_x_4"
    _write(run / "server.py", "import sys\nif __name__ == '__main__':\n    print('boom PORT'); sys.exit(3)\n")
    mgr = ap.PreviewManager()
    mgr.start_dir(("job", 4), run)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline and mgr._previews[("job", 4)].status != "failed":
        time.sleep(0.2)
    result = mgr._previews[("job", 4)].to_dict()
    assert result["status"] == "failed" and "3" in result["error"]
    assert "boom" in result["log_tail"]


def test_concurrency_limit_and_idle_reap(warehouse, monkeypatch):
    mgr = ap.PreviewManager()
    for i in range(ap.MAX_CONCURRENT):
        mgr._previews[("j", i)] = ap.Preview(key=("j", i), root=warehouse, kind="node", status="running")
    run = warehouse / "lab_x_5"
    _write(run / "server.py", _SERVER)
    with pytest.raises(ap.PreviewError) as err:
        mgr.start_dir(("j", 99), run)
    assert err.value.status_code == 409
    assert mgr.reap_idle(now=time.monotonic() + ap.IDLE_SECONDS + 1) == ap.MAX_CONCURRENT
    assert all(p.status == "stopped" for p in mgr._previews.values())


def test_route_static_preview(warehouse, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agentdev.api.routes import lab_preview

    run = warehouse / "lab_x_6"
    _write(run / "index.html", "x")
    monkeypatch.setattr(ap, "_product_dir_for", lambda job, idx: run.resolve())
    monkeypatch.setattr(ap, "_manager", ap.PreviewManager())
    app = FastAPI()
    app.include_router(lab_preview.router)
    client = TestClient(app)
    assert client.get("/api/lab/jobs/j1/runs/0/preview").json()["status"] == "idle"
    started = client.post("/api/lab/jobs/j1/runs/0/preview").json()
    assert started == {"status": "running", "url": "/api/lab/jobs/j1/runs/0/site/", "port": None, "kind": "static",
                       "log_tail": "", "error": None, "started_at": started["started_at"],
                       "frameable": True}
    assert client.delete("/api/lab/jobs/j1/runs/0/preview").json()["status"] == "stopped"
    blocked = client.post("/api/lab/jobs/j1/runs/0/preview", headers={"Origin": "https://evil.example"})
    assert blocked.status_code == 403


def test_env_file_seeded_from_example(tmp_path):
    from agentdev.api.services import app_preview

    (tmp_path / ".env.example").write_text("SMTP_HOST=example\n", encoding="utf-8")
    logs = []
    preview = type("P", (), {"add_log": lambda self, line: logs.append(line)})()
    app_preview._seed_env_file(preview, tmp_path)
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "SMTP_HOST=example\n" and logs

    (tmp_path / ".env").write_text("KEEP=1\n", encoding="utf-8")
    app_preview._seed_env_file(preview, tmp_path)
    assert (tmp_path / ".env").read_text(encoding="utf-8") == "KEEP=1\n"


@pytest.mark.parametrize("headers, expected", [
    ({}, True),
    ({"X-Frame-Options": "SAMEORIGIN"}, False),
    ({"Content-Security-Policy": "default-src 'self';frame-ancestors 'self'"}, False),
    ({"Content-Security-Policy": "frame-ancestors *"}, True),
])
def test_frame_allowed_reads_app_headers(headers, expected):
    import http.server
    import threading

    from agentdev.api.services import app_preview

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            for name, value in headers.items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        assert app_preview.frame_allowed(f"http://127.0.0.1:{server.server_port}/") is expected
    finally:
        server.shutdown()
