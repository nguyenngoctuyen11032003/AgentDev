"""Verify gate: a lead may not finish while the project's own tests are red (bounded, flag-gated)."""

import json
import os
import sys
import time
from types import SimpleNamespace

import yaml

from agentdev.entity.configs.node.team import AgentTeamConfig
from agentdev.entity.messages import Message, MessageRole, ToolCallPayload
from agentdev.runtime.node.agent import ModelResponse, ProviderRegistry
from agentdev.runtime.node.agent import verify_gate
from agentdev.runtime.node.executor import agent_executor as agent_executor_module
from agentdev.utils.code_execution import UNSAFE_CODE_EXECUTION_ENV

import pytest


@pytest.fixture(autouse=True)
def _allow_code_execution(monkeypatch):
    """The gate runs workflow-declared commands, so it needs the same server opt-in as the shell tool."""
    monkeypatch.setenv(UNSAFE_CODE_EXECUTION_ENV, "1")


# ---------------------------------------------------------------- detection and runner

def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("AGENTDEV_VERIFY_GATE", raising=False)
    assert verify_gate.enabled() is False
    monkeypatch.setenv("AGENTDEV_VERIFY_GATE", "1")
    assert verify_gate.enabled() is True


def test_team_config_accepts_verify_command():
    cfg = AgentTeamConfig.from_dict({"enabled": True, "verify_command": " npm test "}, path="t")
    assert cfg.verify_command == "npm test"
    assert AgentTeamConfig.from_dict({"enabled": True}, path="t").verify_command == ""


def test_detect_declared_wins(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    assert verify_gate.detect_command(tmp_path, "make check") == "make check"


def test_detect_npm_ignores_default_stub(tmp_path):
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({"scripts": {"test": 'echo "Error: no test specified" && exit 1'}}))
    assert verify_gate.detect_command(tmp_path) is None
    pkg.write_text(json.dumps({"scripts": {"test": "vitest run"}}))
    assert verify_gate.detect_command(tmp_path) == "npm test --silent"


def test_detect_pytest_and_make(tmp_path):
    assert verify_gate.detect_command(tmp_path) is None
    (tmp_path / "Makefile").write_text("build:\n\techo hi\n\ntest:\n\techo t\n")
    assert verify_gate.detect_command(tmp_path) == "make test"
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    assert "pytest" in verify_gate.detect_command(tmp_path)


def test_run_pass_fail_and_output_cap(tmp_path):
    ok = verify_gate.run_verification(tmp_path, f'"{sys.executable}" -c "print(1)"', "t-run", timeout=30)
    assert ok.status == "pass"
    bad = verify_gate.run_verification(
        tmp_path, f'"{sys.executable}" -c "print(\'x\' * 50000); raise SystemExit(3)"', "t-run", timeout=30)
    assert bad.status == "fail" and bad.returncode == 3
    assert len(bad.output) <= verify_gate.OUTPUT_LIMIT + 200
    assert verify_gate.blocks_finish(bad) and not verify_gate.blocks_finish(ok)


def test_run_timeout_is_not_approval(tmp_path):
    started = time.monotonic()
    res = verify_gate.run_verification(
        tmp_path, f'"{sys.executable}" -c "import time; time.sleep(60)"', "t-timeout", timeout=1)
    assert res.status == "timeout"
    assert verify_gate.blocks_finish(res)  # silence or timeout is never approval
    assert time.monotonic() - started < 20


def test_missing_command_is_error_not_failure(tmp_path):
    res = verify_gate.run_verification(tmp_path, "definitely-not-a-real-command-xyz", "t-missing", timeout=30)
    assert res.status == "error"
    assert not verify_gate.blocks_finish(res)


# ---------------------------------------------------------------- end to end (fake model)

class Provider:
    scripts: dict = {}
    seen: dict = {}

    def __init__(self, config):
        self.config = config

    def create_client(self):
        return None

    def call_model(self, client, conversation, timeline, tool_specs=None, **kwargs):
        node = self.config.node_id
        self.seen.setdefault(node, []).append([m.text_content() for m in conversation])
        steps = self.scripts[node]
        step = steps.pop(0) if len(steps) > 1 else steps[0]
        if callable(step):
            step = step()
        if isinstance(step, tuple):
            name, args = step
            call = ToolCallPayload(id=f"c{len(self.seen[node])}", function_name=name, arguments=json.dumps(args))
            return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content="", tool_calls=[call]))
        return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=step))

    def extract_token_usage(self, response):
        return None


CHECK = "import pathlib, sys\nsys.exit(0 if pathlib.Path('ok.txt').exists() else 1)\n"


def _run(tmp_path, monkeypatch, scripts, *, flag, project=True, verify_command=True):
    from agentdev.entity.graph_config import GraphConfig
    from agentdev.runtime import sdk
    from agentdev.runtime.bootstrap.schema import ensure_schema_registry_populated
    from agentdev.validation.check import load_config
    from agentdev.workflow.graph import GraphExecutor
    from agentdev.workflow.graph_context import GraphContext

    ensure_schema_registry_populated()
    ws = tmp_path / "ws"
    ws.mkdir()
    if project:
        (ws / "check.py").write_text(CHECK)
    team = {"enabled": True, "plan_approval": False, "members": ["Fixer"]}
    if verify_command:
        team["verify_command"] = f'"{sys.executable}" check.py'

    def agent(node_id, role, team=None):
        cfg = {"connection": "fake", "provider": "fake", "name": "fake-model", "role": role}
        if team:
            cfg["team"] = team
        return {"id": node_id, "type": "agent", "description": role, "config": cfg}

    definition = {"version": "0.4.0", "graph": {
        "id": "vg", "start": ["Lead"], "end": ["Lead"], "edges": [],
        "nodes": [agent("Lead", "Lead", team=team), agent("Fixer", "Fixes bugs")]}}
    path = tmp_path / "vg.yaml"
    path.write_text(yaml.safe_dump(definition), encoding="utf-8")
    creds = SimpleNamespace(provider="fake", vendor="fake", token="", base_url="")
    monkeypatch.setattr(agent_executor_module, "resolve_connection", lambda _id: creds)
    monkeypatch.setattr(ProviderRegistry, "get_provider", lambda _name: Provider)
    if flag:
        monkeypatch.setenv("AGENTDEV_VERIFY_GATE", "1")
    else:
        monkeypatch.delenv("AGENTDEV_VERIFY_GATE", raising=False)
    Provider.scripts, Provider.seen = scripts, {}
    design = load_config(path)
    config = GraphConfig.from_definition(design.graph, name="vg-test", output_root=sdk.OUTPUT_ROOT,
                                         source_path=str(path), vars=design.vars)
    GraphExecutor(GraphContext(config=config), workspace_root=ws)._execute("Fix the failing check please")
    return ws


def _make_ok(tmp_path, text):
    def do():
        (tmp_path / "ws" / "ok.txt").write_text("fixed")
        return text
    return do


def test_gate_sends_red_result_back_and_lead_delegates(tmp_path, monkeypatch):
    scripts = {
        "Lead": ["All done.", ("delegate_task", {"member": "Fixer", "task": "make check.py pass"}), "Really done."],
        "Fixer": [_make_ok(tmp_path, "Fixed it.")],
    }
    ws = _run(tmp_path, monkeypatch, scripts, flag=True)
    lead = Provider.seen["Lead"]
    assert len(lead) == 3
    assert any("VERIFY" in t and "check.py" in t for t in lead[1])  # the real result came back as feedback
    assert (ws / "ok.txt").exists() and "Fixer" in Provider.seen
    assert sum("VERIFY GATE" in t for t in lead[2]) == 1


def test_gate_is_bounded(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, {"Lead": ["done", "done again", "still done"]}, flag=True)
    assert len(Provider.seen["Lead"]) == 1 + verify_gate.MAX_ROUNDS
    assert "Fixer" not in Provider.seen


def test_flag_off_keeps_old_behavior(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, {"Lead": ["done"]}, flag=False)
    assert len(Provider.seen["Lead"]) == 1


def test_no_command_detected_is_noop(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, {"Lead": ["done"]}, flag=True, project=False, verify_command=False)
    assert len(Provider.seen["Lead"]) == 1


def test_green_workspace_finishes_at_once(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, {"Lead": [_make_ok(tmp_path, "done")]}, flag=True)
    assert len(Provider.seen["Lead"]) == 1


# ---------------------------------------------------------------- security and robustness

def test_refuses_without_unsafe_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv(UNSAFE_CODE_EXECUTION_ENV, raising=False)
    marker = tmp_path / "ran.txt"
    code = "open('ran.txt', 'w').write('x')"
    res = verify_gate.run_verification(tmp_path, f'"{sys.executable}" -c "{code}"', "t-guard", timeout=30)
    assert res.status == "error" and UNSAFE_CODE_EXECUTION_ENV in res.output
    assert not marker.exists()  # never executed, never a pass
    assert res.status != "pass"


def test_refuses_blocked_command(tmp_path):
    res = verify_gate.run_verification(tmp_path, "git push origin main", "t-blocked", timeout=30)
    assert res.status == "error" and "Blocked" in res.output


def test_env_is_sanitized(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTDEV_SECRET_THING", "leak")
    monkeypatch.setenv("MY_API_KEY", "leak")
    code = "import os; print(os.environ.get('AGENTDEV_SECRET_THING'), os.environ.get('MY_API_KEY'))"
    res = verify_gate.run_verification(tmp_path, f'"{sys.executable}" -c "{code}"', "t-env", timeout=30)
    assert res.status == "pass" and "leak" not in res.output


def test_cancel_event_stops_the_command(tmp_path):
    import threading

    cancel = threading.Event()
    threading.Timer(1.0, cancel.set).start()
    started = time.monotonic()
    res = verify_gate.run_verification(
        tmp_path, f'"{sys.executable}" -c "import time; time.sleep(60)"', "t-cancel", timeout=120, cancel_event=cancel)
    assert res.status == "cancelled"
    assert not verify_gate.blocks_finish(res)
    assert time.monotonic() - started < 20


def test_relative_executable_resolves_against_project_root(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    other = tmp_path / "other"
    (root / "node_modules" / ".bin").mkdir(parents=True)
    other.mkdir()
    (root / "run_tests.sh").write_text("exit 0\n")
    (root / "node_modules" / ".bin" / "jest").write_text("")
    monkeypatch.chdir(other)  # the server's cwd is somewhere else
    assert not verify_gate._executable_missing("./run_tests.sh --x", root)
    assert not verify_gate._executable_missing("node_modules/.bin/jest", root)
    assert verify_gate._executable_missing("./nope.sh", root)


@pytest.mark.skipif(os.name != "nt", reason="cmd.exe only")
def test_windows_missing_command_in_shell_is_error(tmp_path):
    res = verify_gate.run_verification(tmp_path, "cmd /c definitelynotacommandxyz", "t-winmiss", timeout=30)
    assert res.status == "error" and not verify_gate.blocks_finish(res)


def test_pytest_no_tests_collected_is_not_a_failure(tmp_path):
    res = verify_gate.run_verification(
        tmp_path, f'"{sys.executable}" -B -m pytest -q -p no:cacheprovider', "t-pyt5", timeout=60)
    assert res.returncode == 5
    assert res.status == "none" and not verify_gate.blocks_finish(res)


def test_detect_prefers_project_venv_python(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    py =tmp_path / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")
    py.parent.mkdir(parents=True)
    py.write_text("")
    assert str(py) in verify_gate.detect_command(tmp_path)


def test_pytest_import_error_of_project_deps_is_error_not_failure(tmp_path):
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    (tmp_path / "test_a.py").write_text("import module_that_does_not_exist_xyz\n\ndef test_a():\n    pass\n")
    command = verify_gate.detect_command(tmp_path)
    res = verify_gate.run_verification(tmp_path, command, "t-imp", timeout=60)
    assert res.status == "error" and not verify_gate.blocks_finish(res)
