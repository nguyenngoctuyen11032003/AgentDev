"""Previews must listen on 127.0.0.1 only (A5-6): explicit host flags/env for every server kind."""

import json

from agentdev.api.services import app_preview as ap


def _flat(tpl) -> str:
    return " ".join(tpl.cmd) + " " + json.dumps(tpl.env)


def test_env_forces_loopback_for_common_servers():
    env = ap.preview_env({"PORT": "47100"})
    for key in ("HOST", "HOSTNAME", "BIND", "BIND_ADDR", "SERVER_HOST"):
        assert env[key] == "127.0.0.1", key


def test_env_cannot_be_overridden_to_all_interfaces(monkeypatch):
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("HOSTNAME", "0.0.0.0")
    env = ap.preview_env({})
    assert env["HOST"] == "127.0.0.1" and env["HOSTNAME"] == "127.0.0.1"


def _pkg(tmp_path, pkg):
    (tmp_path / "package.json").write_text(json.dumps(pkg), encoding="utf-8")
    return tmp_path


def test_node_templates_carry_loopback(tmp_path):
    cases = [
        {"scripts": {"dev": "next dev"}, "dependencies": {"next": "14"}},
        {"scripts": {"dev": "vite"}, "devDependencies": {"vite": "5"}},
        {"scripts": {"start": "react-scripts start"}, "dependencies": {"react-scripts": "5"}},
        {"scripts": {"start": "node server.js"}},
        {"main": "x.js"},
    ]
    for i, pkg in enumerate(cases):
        d = tmp_path / f"c{i}"
        d.mkdir()
        _pkg(d, pkg)
        (d / "x.js").write_text("", encoding="utf-8")
        found = ap._node_process(d)
        assert found, pkg
        tpl, _label = found
        env = ap.preview_env(tpl.env)
        assert env["HOST"] == "127.0.0.1"
        assert "127.0.0.1" in _flat(tpl) or env["HOSTNAME"] == "127.0.0.1"


def test_python_script_gets_loopback_env(tmp_path):
    (tmp_path / "server.py").write_text(
        "import http.server\nif __name__ == '__main__':\n    http.server.HTTPServer(('', 1), None).serve_forever()\n",
        encoding="utf-8")
    tpl, _ = ap._python_process(tmp_path)
    env = ap.preview_env(tpl.env)
    assert env["HOST"] == "127.0.0.1" and env["HOSTNAME"] == "127.0.0.1"
