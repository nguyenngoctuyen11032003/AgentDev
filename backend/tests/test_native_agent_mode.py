"""Native agent mode: Claude Code / Codex run their own agent loop in the project workspace."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from agentdev.entity.configs.base import ConfigError
from agentdev.entity.configs.node.agent import AgentConfig
from agentdev.entity.configs.node.native_mode import AgentNativeModeConfig
from agentdev.entity.enums import CallStage
from agentdev.entity.messages import AttachmentRef, Message, MessageBlock, MessageBlockType, MessageRole
from agentdev.runtime.node.agent.account_fallback import QuotaExceededError
from agentdev.runtime.node.agent.providers._cli_common import CliClient, CliProviderError
from agentdev.runtime.node.agent.providers._native import NativeRunContext
from agentdev.runtime.node.agent.providers.claude_cli_provider import ClaudeCliProvider
from agentdev.runtime.node.agent.providers.codex_cli_provider import CodexCliProvider
from agentdev.runtime.node.executor.agent_executor import AgentNodeExecutor
from agentdev.runtime.node.executor.base import ExecutionContext
from agentdev.utils.code_execution import UNSAFE_CODE_EXECUTION_ENV
from agentdev.utils.exceptions import SecurityError

RUN = "agentdev.connections.cli_auth.run_capture"


def _cfg(timeout=None):
    params = {"timeout": timeout} if timeout else {}
    return SimpleNamespace(base_url=None, api_key=None, name="m1", provider="x", params=params)


def _conv(extra_blocks=None):
    user = Message(role=MessageRole.USER, content="fix the failing test")
    if extra_blocks:
        user = Message(role=MessageRole.USER, content=[MessageBlock(MessageBlockType.TEXT, text="fix it"), *extra_blocks])
    return [Message(role=MessageRole.SYSTEM, content="You are a backend developer."), user]


def _done(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


def _arg(argv, flag):
    return argv[argv.index(flag) + 1]


def _claude_stream(result_text="Fixed the bug.", *, is_error=False, subtype="success", edit_path=None):
    events = [{"type": "system", "subtype": "init", "tools": ["Read", "Edit"]}]
    if edit_path:
        events.append({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Edit", "input": {"file_path": edit_path, "old_string": "a"}},
        ]}})
        events.append({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "updated", "is_error": False},
        ]}})
    events.append({"type": "result", "subtype": subtype, "is_error": is_error, "result": result_text,
                   "usage": {"input_tokens": 10, "cache_read_input_tokens": 5, "output_tokens": 7},
                   "total_cost_usd": 0.01})
    return "\n".join(json.dumps(e) for e in events)


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    return root


# --------------------------------------------------------------------------- config


def test_native_mode_config_parsing():
    assert AgentNativeModeConfig.from_dict({}, path="n").enabled is False
    cfg = AgentNativeModeConfig.from_dict({"enabled": True, "allow_commands": True, "max_turns": 20}, path="n")
    assert (cfg.enabled, cfg.allow_commands, cfg.max_turns) == (True, True, 20)
    assert AgentNativeModeConfig.from_dict(True, path="n").enabled is True
    for bad in (0, -1, "5", True, 10_000):
        with pytest.raises(ConfigError):
            AgentNativeModeConfig.from_dict({"max_turns": bad}, path="n")
    agent = AgentConfig.from_dict({"name": "m", "connection": "c", "native_mode": {"enabled": True}}, path="a")
    assert agent.native_mode.enabled and not agent.native_mode.allow_commands
    assert AgentConfig.from_dict({"name": "m", "connection": "c"}, path="a").native_mode is None
    assert "native_mode" in AgentConfig.field_specs()


# --------------------------------------------------------------------------- claude


def test_claude_native_argv_cwd_and_activity(workspace):
    events = []
    native = NativeRunContext(workspace=str(workspace), max_turns=12,
                              on_tool=lambda *a: events.append(a))
    p = ClaudeCliProvider(_cfg())
    out = _claude_stream(edit_path=str(workspace / "app.py"))
    with patch(RUN, return_value=_done(out=out)) as run:
        resp = p.call_model(CliClient("claude"), _conv(), [], tool_specs=None, native=native)
    argv, kw = run.call_args.args[0], run.call_args.kwargs
    assert kw["cwd"] == str(workspace)
    assert kw["timeout"] == 1800
    assert _arg(argv, "--tools") == "Read,Glob,Grep,Edit,Write"
    assert _arg(argv, "--permission-mode") == "acceptEdits"
    assert _arg(argv, "--max-turns") == "12"
    assert _arg(argv, "--output-format") == "stream-json"
    assert "--strict-mcp-config" in argv and "--restricted" in argv
    assert _arg(argv, "--permission-prompts") == "none"
    # The user's own ~/.claude setup (CLAUDE.md, skills, plugins, auto-memory, hooks) stays out; no --bare.
    assert _arg(argv, "--setting-sources") == "project" and "--disable-slash-commands" in argv
    assert _arg(argv, "--settings").endswith("agentdev_settings.json") and "--bare" not in argv
    assert "--allowedTools" not in argv and "--add-dir" not in argv
    assert not any("dangerously" in a for a in argv)
    assert "--json-schema" not in argv
    assert "Native agent mode" in kw["input"] and "Tool-calling protocol" not in kw["input"]
    assert "Shell commands are disabled" in kw["input"]
    assert resp.message.content.startswith("Fixed the bug.")
    assert "[Files changed by the agent] app.py" in resp.message.content
    assert resp.raw_response["changed_files"] == [str(workspace / "app.py")]
    assert p.extract_token_usage(resp.raw_response).total_tokens == 22
    assert [(e[0], e[1], e[2]) for e in events] == [("before", "claude:Edit", None), ("after", "claude:Edit", True)]


def test_claude_native_bash_only_when_allowed(workspace):
    native = NativeRunContext(workspace=str(workspace), allow_commands=True)
    with patch(RUN, return_value=_done(out=_claude_stream())) as run:
        ClaudeCliProvider(_cfg(timeout=99)).call_model(CliClient("claude"), _conv(), [], native=native)
    argv, kw = run.call_args.args[0], run.call_args.kwargs
    assert _arg(argv, "--tools") == "Read,Glob,Grep,Edit,Write,Bash"
    assert _arg(argv, "--allowedTools") == "Bash"
    assert kw["timeout"] == 99
    assert "You may run shell commands" in kw["input"]


def test_claude_normal_mode_unchanged(workspace):
    with patch(RUN, return_value=_done(out='{"result":"hi","is_error":false}')) as run:
        resp = ClaudeCliProvider(_cfg()).call_model(CliClient("claude"), _conv(), [])
    argv, kw = run.call_args.args[0], run.call_args.kwargs
    assert _arg(argv, "--tools") == "" and _arg(argv, "--output-format") == "stream-json"
    assert "--include-partial-messages" in argv
    assert kw["cwd"] != str(workspace) and "agentdev-cli-" in kw["cwd"]
    # Streaming arms the idle watchdog; the wall-clock limit is only a backstop.
    assert kw["timeout"] == 1800 and "on_stdout_line" in kw and "--permission-mode" not in argv
    assert resp.message.content == "hi"


def test_claude_normal_mode_reads_stream_result(workspace):
    """A long reply streams deltas; the final result event is what gets parsed."""
    out = _claude_stream("streamed answer")
    with patch(RUN, return_value=_done(out=out)):
        resp = ClaudeCliProvider(_cfg()).call_model(CliClient("claude"), _conv(), [])
    assert resp.message.content == "streamed answer"


def test_claude_normal_mode_explicit_timeout_is_kept(workspace):
    with patch(RUN, return_value=_done(out='{"result":"hi","is_error":false}')) as run:
        ClaudeCliProvider(_cfg(timeout=120)).call_model(CliClient("claude"), _conv(), [])
    assert run.call_args.kwargs["timeout"] == 120


def test_claude_native_quota_and_errors(workspace):
    native = NativeRunContext(workspace=str(workspace))
    p = ClaudeCliProvider(_cfg())
    limit = _claude_stream("You've hit your usage limit · resets 5pm", is_error=True, subtype="error_during_execution")
    with patch(RUN, return_value=_done(rc=1, out=limit)):
        with pytest.raises(QuotaExceededError):
            p.call_model(CliClient("claude"), _conv(), [], native=native)
    with patch(RUN, return_value=_done(rc=1, err="Claude usage limit reached")):
        with pytest.raises(QuotaExceededError):
            p.call_model(CliClient("claude"), _conv(), [], native=native)
    with patch(RUN, return_value=_done(rc=1, out=_claude_stream("Please run /login", is_error=True))):
        with pytest.raises(CliProviderError, match="not logged in"):
            p.call_model(CliClient("claude"), _conv(), [], native=native)
    with patch(RUN, return_value=_done(rc=3, err="boom")):
        with pytest.raises(CliProviderError, match="code 3.*boom"):
            p.call_model(CliClient("claude"), _conv(), [], native=native)


def test_claude_native_max_turns_is_not_fatal(workspace):
    native = NativeRunContext(workspace=str(workspace), max_turns=3)
    out = _claude_stream("", is_error=True, subtype="error_max_turns", edit_path=str(workspace / "a.py"))
    with patch(RUN, return_value=_done(rc=1, out=out)):
        resp = ClaudeCliProvider(_cfg()).call_model(CliClient("claude"), _conv(), [], native=native)
    assert "limit of 3 agent turns" in resp.message.content and "a.py" in resp.message.content


def test_claude_native_retries_without_new_flags_on_old_cli(workspace):
    native = NativeRunContext(workspace=str(workspace))
    replies = [_done(rc=1, err="error: unknown option '--restricted'"), _done(out=_claude_stream())]
    with patch(RUN, side_effect=replies) as run:
        resp = ClaudeCliProvider(_cfg()).call_model(CliClient("claude"), _conv(), [], native=native)
    second = run.call_args_list[1].args[0]
    assert "--restricted" not in second and "--permission-prompts" not in second
    assert "--strict-mcp-config" in second and _arg(second, "--permission-mode") == "acceptEdits"
    assert _arg(second, "--setting-sources") == "project" and "--disable-slash-commands" in second
    assert resp.message.content == "Fixed the bug."


def test_claude_native_attachments_outside_workspace(workspace, tmp_path):
    pdf = tmp_path / "spec.pdf"
    pdf.write_bytes(b"%PDF-1.4 data")
    ref = AttachmentRef(attachment_id="a1", name="spec.pdf", mime_type="application/pdf", local_path=str(pdf))
    conv = _conv([MessageBlock(MessageBlockType.FILE, attachment=ref)])
    seen = {}

    def fake_run(cmd, **kw):
        staging = _arg(cmd, "--add-dir")
        seen["staging"] = staging
        seen["exists"] = (Path(staging) / "attachments" / "spec.pdf").is_file()
        seen["input"] = kw["input"]
        return _done(out=_claude_stream())

    native = NativeRunContext(workspace=str(workspace))
    with patch(RUN, side_effect=fake_run):
        ClaudeCliProvider(_cfg()).call_model(CliClient("claude"), conv, [], native=native)
    assert seen["exists"]
    assert not Path(seen["staging"]).resolve().is_relative_to(workspace.resolve())
    assert list(workspace.iterdir()) == []  # nothing copied into the user's project
    assert "/attachments/spec.pdf" in seen["input"]


# --------------------------------------------------------------------------- codex


def _codex_events(edit=None, command=None):
    events = [{"type": "thread.started", "thread_id": "x"}]
    if command:
        events.append({"type": "item.completed", "item": {"type": "command_execution", "command": command,
                                                          "aggregated_output": "1 passed", "exit_code": 0}})
    if edit:
        events.append({"type": "item.completed", "item": {"type": "file_change", "status": "completed",
                                                          "changes": [{"path": edit, "kind": "update"}]}})
    events.append({"type": "item.completed", "item": {"type": "agent_message", "text": "Done."}})
    events.append({"type": "turn.completed", "usage": {"input_tokens": 4, "output_tokens": 3}})
    return "\n".join(json.dumps(e) for e in events)


def test_codex_native_read_only_without_commands(workspace):
    native = NativeRunContext(workspace=str(workspace))
    with patch(RUN, return_value=_done(out=_codex_events())) as run:
        resp = CodexCliProvider(_cfg()).call_model(CliClient("codex"), _conv(), [], native=native)
    argv, kw = run.call_args.args[0], run.call_args.kwargs
    assert _arg(argv, "-C") == str(workspace) and kw["cwd"] == str(workspace)
    assert _arg(argv, "--sandbox") == "read-only"
    assert "mcp_servers={}" in argv and "web_search=disabled" in argv
    # No user skill catalog / plugins / hooks / memories, no session files; config.toml (auth) still loads.
    assert "skills.include_instructions=false" in argv and "--ephemeral" in argv
    assert {"apps", "plugins", "hooks", "memories"} <= {argv[i + 1] for i, a in enumerate(argv) if a == "--disable"}
    assert "--ignore-user-config" not in argv and "project_doc_max_bytes=0" not in argv
    assert "--output-schema" not in argv and argv[-1] == "-"
    assert not any("dangerously" in a or a == "--full-auto" for a in argv)
    assert kw["timeout"] == 1800
    assert "sandbox is read-only" in kw["input"]
    assert resp.message.content == "Done."


def test_codex_native_workspace_write_with_commands(workspace):
    events = []
    native = NativeRunContext(workspace=str(workspace), allow_commands=True, on_tool=lambda *a: events.append(a))
    out = _codex_events(edit=str(workspace / "calc.py"), command="pytest -q")
    with patch(RUN, return_value=_done(out=out)) as run:
        resp = CodexCliProvider(_cfg()).call_model(CliClient("codex"), _conv(), [], native=native)
    argv = run.call_args.args[0]
    assert _arg(argv, "--sandbox") == "workspace-write"
    assert "sandbox_workspace_write.network_access=false" in argv
    assert "[Files changed by the agent] calc.py" in resp.message.content
    names = [(e[0], e[1]) for e in events]
    assert names == [("before", "codex:shell"), ("after", "codex:shell"),
                     ("before", "codex:apply_patch"), ("after", "codex:apply_patch")]
    assert CodexCliProvider(_cfg()).extract_token_usage(resp.raw_response).total_tokens == 7


def test_codex_native_quota(workspace):
    native = NativeRunContext(workspace=str(workspace))
    err_event = json.dumps({"type": "error", "message": "You've hit your usage limit. Try again later."})
    with patch(RUN, return_value=_done(rc=1, out=err_event)):
        with pytest.raises(QuotaExceededError):
            CodexCliProvider(_cfg()).call_model(CliClient("codex"), _conv(), [], native=native)


def test_codex_normal_mode_unchanged():
    with patch(RUN, return_value=_done(out=_codex_events())) as run:
        CodexCliProvider(_cfg()).call_model(CliClient("codex"), _conv(), [])
    argv, kw = run.call_args.args[0], run.call_args.kwargs
    assert _arg(argv, "--sandbox") == "read-only" and "-C" not in argv
    assert "agentdev-cli-" in kw["cwd"] and kw["timeout"] == 300


# --------------------------------------------------------------------------- executor


def _executor(tmp_path, *, opened=True):
    graph_dir = tmp_path / "session"
    root = tmp_path / "project" if opened else graph_dir / "code_workspace"
    root.mkdir(parents=True, exist_ok=True)
    context = ExecutionContext(tool_manager=Mock(), function_manager=Mock(), log_manager=Mock(),
                               global_state={"python_workspace_root": root, "graph_directory": graph_dir})
    return AgentNodeExecutor(context), root


def _agent_cfg(native=None, team=None):
    data = {"name": "m", "connection": "c"}
    if native is not None:
        data["native_mode"] = native
    if team is not None:
        data["team"] = team
    return AgentConfig.from_dict(data, path="a")


NODE = SimpleNamespace(id="Backend Developer")


def test_executor_native_context_and_shell_opt_in(tmp_path, monkeypatch):
    executor, root = _executor(tmp_path)
    cfg = _agent_cfg({"enabled": True, "allow_commands": True, "max_turns": 9})
    monkeypatch.delenv(UNSAFE_CODE_EXECUTION_ENV, raising=False)
    native = executor._resolve_native_mode(NODE, cfg, ClaudeCliProvider)
    assert native.workspace == str(root.resolve()) and native.max_turns == 9
    assert native.allow_commands is False  # server opt-in off
    monkeypatch.setenv(UNSAFE_CODE_EXECUTION_ENV, "1")
    assert executor._resolve_native_mode(NODE, cfg, ClaudeCliProvider).allow_commands is True
    no_cmd = _agent_cfg({"enabled": True})
    assert executor._resolve_native_mode(NODE, no_cmd, ClaudeCliProvider).allow_commands is False
    assert executor._resolve_native_mode(NODE, _agent_cfg(), ClaudeCliProvider) is None
    assert executor._resolve_native_mode(NODE, _agent_cfg({"enabled": False}), ClaudeCliProvider) is None
    # tool activity goes to the run log
    native.on_tool("before", "claude:Edit", None, None, {"arguments": {}})
    args = executor.log_manager.record_tool_call.call_args.args
    assert args[0] == NODE.id and args[1] == "claude:Edit" and args[5] == CallStage.BEFORE


def test_executor_rejects_native_on_team_lead(tmp_path):
    executor, _ = _executor(tmp_path)
    cfg = _agent_cfg({"enabled": True}, team={"enabled": True})
    assert executor._resolve_native_mode(NODE, cfg, ClaudeCliProvider) is None
    assert "team lead" in executor.log_manager.warning.call_args.args[0]


def test_executor_native_needs_cli_provider(tmp_path):
    executor, _ = _executor(tmp_path)
    assert executor._resolve_native_mode(NODE, _agent_cfg({"enabled": True}), object) is None
    assert executor.log_manager.warning.called


def test_executor_default_session_workspace_is_allowed(tmp_path):
    executor, root = _executor(tmp_path, opened=False)
    assert executor._native_workspace_root() == root.resolve()


def test_executor_refuses_agentdev_install_unless_opened(tmp_path, monkeypatch):
    import agentdev.runtime.node.executor.agent_executor as mod

    # A run whose default workspace (graph_dir/code_workspace) is, or contains, the AgentDev checkout.
    executor, root = _executor(tmp_path, opened=False)
    monkeypatch.setattr(mod, "AGENTDEV_INSTALL_ROOT", root.resolve())
    with pytest.raises(SecurityError, match="AgentDev installation"):
        executor._native_workspace_root()
    monkeypatch.setattr(mod, "AGENTDEV_INSTALL_ROOT", (root / "AgentDev").resolve())
    with pytest.raises(SecurityError):
        executor._native_workspace_root()
    # The user explicitly opened the checkout as the project folder: allowed.
    opened, project = _executor(tmp_path, opened=True)
    monkeypatch.setattr(mod, "AGENTDEV_INSTALL_ROOT", project.resolve())
    assert opened._native_workspace_root() == project.resolve()


def test_install_root_points_at_the_checkout():
    import agentdev.runtime.node.executor.agent_executor as mod

    assert (mod.AGENTDEV_INSTALL_ROOT / "backend" / "agentdev").is_dir()


def test_executor_missing_workspace(tmp_path):
    context = ExecutionContext(tool_manager=Mock(), function_manager=Mock(), log_manager=Mock(), global_state={})
    with pytest.raises(SecurityError):
        AgentNodeExecutor(context)._native_workspace_root()


def test_invoke_provider_passes_native_only_to_supporting_providers(tmp_path):
    executor, root = _executor(tmp_path)
    native = NativeRunContext(workspace=str(root))
    node = SimpleNamespace(id="n", model_name="m", as_config=lambda _cls: _agent_cfg({"enabled": True}))
    from agentdev.runtime.node.agent import ModelResponse

    seen = []

    class Fake:
        supports_native_mode = True

        def call_model(self, client, **kwargs):
            seen.append(kwargs.get("native"))
            return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content="ok"), raw_response={})

    class Plain(Fake):
        supports_native_mode = False

    executor._ensure_not_cancelled = lambda: None
    executor._invoke_provider(Fake(), None, [], [], {}, [], node, native=native)
    executor._invoke_provider(Plain(), None, [], [], {}, [], node, native=native)
    executor._invoke_provider(Fake(), None, [], [], {}, [], node)
    assert seen == [native, None, None]


def test_claude_native_skills_are_readable_but_not_editable(workspace):
    from agentdev.paths import SKILLS_DIR

    captured = {}

    def fake_run(argv, *args, **kwargs):
        with open(_arg(argv, "--settings"), encoding="utf-8") as fh:
            captured["settings"] = json.load(fh)
        captured["argv"] = argv
        return _done(out=_claude_stream())

    conv = [Message(role=MessageRole.USER, content=f"- fe: UI (file: {SKILLS_DIR.as_posix()}/fe/SKILL.md)")]
    native = NativeRunContext(workspace=str(workspace))
    with patch(RUN, side_effect=fake_run):
        ClaudeCliProvider(_cfg()).call_model(CliClient("claude"), conv, [], tool_specs=None, native=native)
    if SKILLS_DIR.is_dir():
        assert str(SKILLS_DIR) in captured["argv"]
        assert captured["settings"]["permissions"]["deny"] == [f"Edit({SKILLS_DIR.as_posix()}/**)"]

    # No skills listed: no extra directory and no deny rule.
    with patch(RUN, side_effect=fake_run):
        ClaudeCliProvider(_cfg()).call_model(CliClient("claude"), _conv(), [], tool_specs=None, native=native)
    assert "permissions" not in captured["settings"] and "--add-dir" not in captured["argv"]
