import json
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agentdev.connections import cli_auth
from agentdev.entity.messages import Message, MessageRole, ToolCallPayload
from agentdev.entity.tool_spec import ToolSpec
from agentdev.runtime.node.agent.providers._cli_common import CliClient, CliProviderError
from agentdev.runtime.node.agent.providers.claude_cli_provider import ClaudeCliProvider
from agentdev.runtime.node.agent.providers.codex_cli_provider import CodexCliProvider

SECRET_PROMPT = "TOP-SECRET-PROMPT-XYZ"


def _cfg(timeout=None):
    params = {"timeout": timeout} if timeout else {}
    return SimpleNamespace(base_url=None, api_key=None, name="m1", provider="x", params=params)


def _conv():
    return [
        Message(role=MessageRole.SYSTEM, content="be brief"),
        Message(role=MessageRole.USER, content=SECRET_PROMPT),
    ]


def _done(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


def test_claude_success_and_stdin():
    p = ClaudeCliProvider(_cfg())
    with patch("shutil.which", return_value="/bin/claude"):
        client = p.create_client()
    payload = '{"result":"hi","is_error":false,"usage":{"input_tokens":3,"output_tokens":2}}'
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(out=payload)) as run:
        resp = p.call_model(client, _conv(), [], tool_specs=None)
    assert resp.message.content == "hi"
    args, kw = run.call_args
    assert SECRET_PROMPT in kw["input"] and "be brief" in kw["input"]
    assert not any(SECRET_PROMPT in a for a in args[0])
    assert not kw.get("shell")
    assert p.extract_token_usage(resp.raw_response).total_tokens == 5
    # no tools: plain-text path, no schema, no tool protocol, no tool calls
    assert "--json-schema" not in args[0] and "Tool-calling protocol" not in kw["input"]
    assert resp.message.tool_calls == []


def test_claude_not_installed():
    with patch("shutil.which", return_value=None), pytest.raises(CliProviderError, match="not installed"):
        ClaudeCliProvider(_cfg()).create_client()


def test_claude_nonzero_exit():
    p = ClaudeCliProvider(_cfg())
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(rc=2, err="boom")):
        with pytest.raises(CliProviderError, match="code 2.*boom"):
            p.call_model(CliClient("claude"), _conv(), [])


def test_claude_timeout():
    p = ClaudeCliProvider(_cfg(timeout=7))
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=subprocess.TimeoutExpired("claude", 7)) as run:
        with pytest.raises(CliProviderError, match="timed out"):
            p.call_model(CliClient("claude"), _conv(), [])
    assert run.call_args.kwargs["timeout"] == 7


def test_claude_not_logged_in():
    p = ClaudeCliProvider(_cfg())
    out = '{"is_error":true,"result":"Please run /login"}'
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(rc=1, out=out)):
        with pytest.raises(CliProviderError, match="not logged in"):
            p.call_model(CliClient("claude"), _conv(), [])


def test_codex_success_reads_output_file_and_stdin():
    p = CodexCliProvider(_cfg())

    def fake(cmd, **kw):
        assert not any(SECRET_PROMPT in a for a in cmd)
        assert SECRET_PROMPT in kw["input"]
        with open(cmd[cmd.index("-o") + 1], "w", encoding="utf-8") as fh:
            fh.write("answer")
        return _done()

    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        resp = p.call_model(CliClient("codex"), _conv(), [])
    assert resp.message.content == "answer"


def test_codex_errors():
    p = CodexCliProvider(_cfg())
    with patch("shutil.which", return_value=None), pytest.raises(CliProviderError, match="not installed"):
        p.create_client()
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(rc=1, err="bad")):
        with pytest.raises(CliProviderError, match="code 1"):
            p.call_model(CliClient("codex"), _conv(), [])
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=subprocess.TimeoutExpired("codex", 1)):
        with pytest.raises(CliProviderError, match="timed out"):
            p.call_model(CliClient("codex"), _conv(), [])


def test_detect_cli():
    with patch("shutil.which", return_value=None):
        r = cli_auth.detect_cli("openai")
        assert r["installed"] is False and r["logged_in"] is None
    with patch("shutil.which", return_value="/bin/claude"), patch(
        "agentdev.connections.cli_auth.run_capture", return_value=_done(out="2.1 (Claude Code)")
    ):
        r = cli_auth.detect_cli("anthropic")
        assert r["installed"] and r["logged_in"] is True
    with patch("shutil.which", return_value="/bin/codex"), patch(
        "agentdev.connections.cli_auth.run_capture", side_effect=subprocess.TimeoutExpired("codex", 10)
    ):
        r = cli_auth.detect_cli("openai")
        assert r["installed"] and r["logged_in"] is None
    assert cli_auth.detect_cli("bogus")["installed"] is False


def test_model_name_cannot_inject_shell_syntax():
    from agentdev.runtime.node.agent.providers._cli_common import validate_model_name

    assert validate_model_name("claude-sonnet-5-5") == "claude-sonnet-5-5"
    for bad in ["x&whoami", "a|b", "%PATH%", "m 1", 'x"y', "a;b", "$(id)", "-rf"]:
        with pytest.raises(CliProviderError):
            validate_model_name(bad)


def test_run_capture_timeout_kills_child_and_returns_promptly():
    import sys
    import time

    t0 = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        cli_auth.run_capture([sys.executable, "-c", "import time; time.sleep(60)"], timeout=1)
    assert time.monotonic() - t0 < 15
    done = cli_auth.run_capture([sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"], input="abc", timeout=20)
    assert done.stdout.strip() == "ABC" and done.returncode == 0


# ---------------------------------------------------------------------------
# Claude CLI tool calling
# ---------------------------------------------------------------------------

WEATHER = ToolSpec(
    name="get_temperature",
    description="Get the current temperature of a city",
    parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
)


def _tool_run(reply=None, result_text=None, usage=None, path="claude"):
    """Run call_model with tools against a faked CLI emitting a structured reply."""
    payload = {"is_error": False, "usage": usage or {"input_tokens": 3, "output_tokens": 2}}
    if reply is not None:
        payload["structured_output"] = reply
        payload["result"] = json.dumps(reply)
    if result_text is not None:
        payload["result"] = result_text
    p = ClaudeCliProvider(_cfg())
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(out=json.dumps(payload))) as run:
        resp = p.call_model(CliClient(path), _conv(), [], tool_specs=[WEATHER])
    return p, resp, run


def test_claude_tools_tool_call_parsed():
    reply = {"text": "", "tool_calls": [{"name": "get_temperature", "arguments": {"city": "Hanoi"}}]}
    p, resp, run = _tool_run(reply)
    assert resp.has_tool_calls()
    call = resp.message.tool_calls[0]
    assert call.function_name == "get_temperature" and call.id
    assert json.loads(call.arguments) == {"city": "Hanoi"}
    args, kw = run.call_args
    cmd = args[0]
    assert cmd[cmd.index("--tools") + 1] == ""  # Claude Code's own tools stay disabled
    schema = json.loads(cmd[cmd.index("--json-schema") + 1])
    assert "tool_calls" in schema["properties"]
    assert "get_temperature" in kw["input"] and "Get the current temperature" in kw["input"]
    assert '"city"' in kw["input"] and SECRET_PROMPT in kw["input"]
    assert not any(SECRET_PROMPT in a for a in cmd)
    assert p.extract_token_usage(resp.raw_response).total_tokens == 5


def test_claude_tools_ids_are_unique():
    reply = {"text": "", "tool_calls": [{"name": "get_temperature", "arguments": {"city": "A"}},
                                         {"name": "get_temperature", "arguments": {"city": "B"}}]}
    _, resp, _ = _tool_run(reply)
    ids = [c.id for c in resp.message.tool_calls]
    assert len(ids) == 2 and len(set(ids)) == 2


def test_claude_tools_plain_text_answer():
    _, resp, _ = _tool_run({"text": "It is sunny."})
    assert resp.message.content == "It is sunny." and not resp.has_tool_calls()


def test_claude_tools_unknown_tool_becomes_text_note():
    reply = {"text": "Let me check", "tool_calls": [{"name": "launch_missiles", "arguments": {}}]}
    _, resp, _ = _tool_run(reply)
    assert not resp.has_tool_calls()
    assert "Let me check" in resp.message.content and "launch_missiles" in resp.message.content


def test_claude_tools_unknown_tool_only_still_has_text():
    _, resp, _ = _tool_run({"text": "", "tool_calls": [{"name": "nope", "arguments": {}}]})
    assert not resp.has_tool_calls() and "nope" in resp.message.content


def test_claude_tools_known_and_unknown_mixed():
    reply = {"text": "", "tool_calls": [{"name": "nope", "arguments": {}},
                                         {"name": "get_temperature", "arguments": {"city": "X"}}]}
    _, resp, _ = _tool_run(reply)
    assert [c.function_name for c in resp.message.tool_calls] == ["get_temperature"]


def test_claude_tools_malformed_json_falls_back_to_plain_text():
    _, resp, _ = _tool_run(result_text="Sorry, {not json at all")
    assert resp.message.content == "Sorry, {not json at all" and not resp.has_tool_calls()


def test_claude_tools_json_in_fenced_text_without_structured_output():
    body = '{"text": "", "tool_calls": [{"name": "get_temperature", "arguments": {"city": "Hue"}}]}'
    _, resp, _ = _tool_run(result_text="Here you go:\n```json\n" + body + "\n```")
    assert json.loads(resp.message.tool_calls[0].arguments) == {"city": "Hue"}


def test_claude_tools_cmd_shim_skips_json_schema_argv():
    _, resp, run = _tool_run({"text": "ok"}, path="C:/npm/claude.cmd")
    assert "--json-schema" not in run.call_args.args[0]
    assert "Output ONLY the JSON object" in run.call_args.kwargs["input"]
    assert resp.message.content == "ok"


def test_claude_tools_string_arguments_are_normalized():
    reply = {"text": "", "tool_calls": [{"name": "get_temperature", "arguments": '{"city": "Hanoi"}'}]}
    _, resp, _ = _tool_run(reply)
    assert json.loads(resp.message.tool_calls[0].arguments) == {"city": "Hanoi"}


def test_claude_tools_round_trip_renders_calls_and_results():
    conv = [
        Message(role=MessageRole.SYSTEM, content="be brief"),
        Message(role=MessageRole.USER, content="Weather in Hanoi?"),
        Message(
            role=MessageRole.ASSISTANT,
            content="",
            tool_calls=[ToolCallPayload(id="call_abc", function_name="get_temperature", arguments='{"city": "Hanoi"}')],
        ),
        Message(role=MessageRole.TOOL, content="31C and humid", tool_call_id="call_abc", metadata={"tool_name": "get_temperature"}),
    ]
    p = ClaudeCliProvider(_cfg())
    payload = json.dumps({"is_error": False, "structured_output": {"text": "It is 31C."}, "result": "{}"})
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(out=payload)) as run:
        resp = p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
    prompt = run.call_args.kwargs["input"]
    assert "[System instructions]\nbe brief" in prompt
    assert 'id=call_abc name=get_temperature arguments={"city": "Hanoi"}' in prompt
    assert "[Tool result] call_id=call_abc name=get_temperature\n31C and humid\n[End tool result]" in prompt
    convo = prompt[prompt.index("[Conversation]"):]
    assert convo.index("Weather in Hanoi?") < convo.index("[Assistant tool call]") < convo.index("[Tool result]")
    assert resp.message.content == "It is 31C." and not resp.has_tool_calls()


def test_claude_tools_tool_result_name_resolved_from_call_id():
    from agentdev.runtime.node.agent.providers._cli_common import flatten_conversation

    conv = [
        Message(role=MessageRole.USER, content="q"),
        Message(role=MessageRole.ASSISTANT, content="", tool_calls=[ToolCallPayload(id="c1", function_name="get_temperature", arguments="{}")]),
        Message(role=MessageRole.TOOL, content="ok", tool_call_id="c1"),
    ]
    assert "call_id=c1 name=get_temperature" in flatten_conversation(conv, "PREAMBLE")


def test_flatten_without_preamble_is_legacy_plain_text():
    from agentdev.runtime.node.agent.providers._cli_common import flatten_conversation

    conv = [
        Message(role=MessageRole.USER, content="hello"),
        Message(role=MessageRole.ASSISTANT, content="", tool_calls=[ToolCallPayload(id="c1", function_name="t", arguments="{}")]),
        Message(role=MessageRole.TOOL, content="res", tool_call_id="c1"),
    ]
    out = flatten_conversation(conv)
    assert "Tool: res" in out and "[Assistant tool call]" not in out and "Tool-calling protocol" not in out
