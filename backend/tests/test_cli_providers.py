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


def _capture_claude(out):
    """Fake claude run that also keeps the system prompt file (the static part of the prompt lives there)."""
    seen = {}

    def fake(cmd, **kw):
        with open(cmd[cmd.index("--system-prompt-file") + 1], encoding="utf-8") as fh:
            seen["system"] = fh.read()
        seen["input"] = kw["input"]
        seen["full"] = seen["system"] + "\n\n" + kw["input"]
        return _done(out=out)

    return fake, seen


def test_claude_success_and_stdin():
    p = ClaudeCliProvider(_cfg())
    with patch("shutil.which", return_value="/bin/claude"):
        client = p.create_client()
    payload = '{"result":"hi","is_error":false,"usage":{"input_tokens":3,"output_tokens":2}}'
    fake, seen = _capture_claude(payload)
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake) as run:
        resp = p.call_model(client, _conv(), [], tool_specs=None)
    assert resp.message.content == "hi"
    args, kw = run.call_args
    assert SECRET_PROMPT in kw["input"] and "be brief" in seen["system"]
    assert not any(SECRET_PROMPT in a for a in args[0])
    assert not kw.get("shell")
    assert p.extract_token_usage(resp.raw_response).total_tokens == 5
    # no tools: plain-text path, no schema, no tool protocol, no tool calls
    assert "--json-schema" not in args[0] and "Tool-calling protocol" not in kw["input"]
    assert "--disable-slash-commands" in args[0] and "--bare" not in args[0]
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

    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake) as run:
        resp = p.call_model(CliClient("codex"), _conv(), [])
    assert resp.message.content == "answer"
    cmd = run.call_args.args[0]
    # The user's skills / AGENTS.md / plugins / MCP servers stay out of the call.
    for flag in ("skills.include_instructions=false", "project_doc_max_bytes=0", "mcp_servers={}", "--ephemeral"):
        assert flag in cmd
    assert "plugins" in cmd and "--ignore-user-config" not in cmd


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
    fake, seen = _capture_claude(json.dumps(payload))
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake) as run:
        resp = p.call_model(CliClient(path), _conv(), [], tool_specs=[WEATHER])
    run.seen = seen
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
    # Static part (tool protocol + schemas) in the system prompt, the conversation on stdin.
    assert "get_temperature" in run.seen["system"] and "Get the current temperature" in run.seen["system"]
    assert '"city"' in run.seen["system"] and SECRET_PROMPT in kw["input"]
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
    assert "Output ONLY the JSON object" in run.seen["system"]
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
    fake, seen = _capture_claude(payload)
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        resp = p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
    prompt = seen["full"]
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


def _weather_spec():
    return ToolSpec(
        name="get_weather",
        description="Weather for a city",
        parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
    )


def test_codex_tool_call_uses_strict_output_schema():
    p = CodexCliProvider(_cfg())
    seen = {}

    def fake(cmd, **kw):
        schema_path = cmd[cmd.index("--output-schema") + 1]
        with open(schema_path, encoding="utf-8") as fh:
            seen["schema"] = json.load(fh)
        seen["prompt"] = kw["input"]
        reply = {"text": "", "tool_calls": [{"name": "get_weather", "arguments": '{"city": "Hà Nội"}'}]}
        with open(cmd[cmd.index("-o") + 1], "w", encoding="utf-8") as fh:
            json.dump(reply, fh, ensure_ascii=False)
        events = '{"type":"turn.completed","usage":{"input_tokens":40,"cached_input_tokens":8,"output_tokens":6}}'
        return _done(out=events)

    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        resp = p.call_model(CliClient("codex"), _conv(), [], tool_specs=[_weather_spec()])

    schema = seen["schema"]
    assert schema["additionalProperties"] is False and schema["required"] == ["text", "tool_calls"]
    item = schema["properties"]["tool_calls"]["items"]
    assert item["additionalProperties"] is False and item["properties"]["name"]["enum"] == ["get_weather"]
    assert "Tool-calling protocol" in seen["prompt"] and "get_weather" in seen["prompt"]
    (call,) = resp.message.tool_calls
    assert call.function_name == "get_weather" and json.loads(call.arguments) == {"city": "Hà Nội"}
    assert p.extract_token_usage(resp.raw_response).total_tokens == 46


def test_codex_final_answer_with_tools_and_event_fallback():
    p = CodexCliProvider(_cfg())

    def fake(cmd, **kw):
        # -o file left empty: the answer is taken from the --json event stream
        events = "\n".join([
            '{"type":"item.completed","item":{"type":"agent_message","text":"{\\"text\\": \\"Trời nắng\\", \\"tool_calls\\": []}"}}',
            '{"type":"turn.completed","usage":{"input_tokens":5,"output_tokens":2}}',
        ])
        return _done(out=events)

    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        resp = p.call_model(CliClient("codex"), _conv(), [], tool_specs=[_weather_spec()])
    assert resp.message.content == "Trời nắng" and resp.message.tool_calls == []


def test_codex_without_tools_passes_no_schema():
    p = CodexCliProvider(_cfg())

    def fake(cmd, **kw):
        assert "--output-schema" not in cmd and "Tool-calling protocol" not in kw["input"]
        with open(cmd[cmd.index("-o") + 1], "w", encoding="utf-8") as fh:
            fh.write("plain")
        return _done()

    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        resp = p.call_model(CliClient("codex"), _conv(), [])
    assert resp.message.content == "plain"


def test_double_wrapped_reply_is_unwrapped():
    from agentdev.runtime.node.agent.providers._cli_common import parse_tool_reply

    spec = _weather_spec()
    text, calls = parse_tool_reply({"text": '{"text": "Trời nắng", "tool_calls": []}'}, "", [spec])
    assert text == "Trời nắng" and calls == []
    text, calls = parse_tool_reply({"text": '{"text": "", "tool_calls": [{"name": "get_weather", "arguments": {"city": "Huế"}}]}'}, "", [spec])
    assert [c.function_name for c in calls] == ["get_weather"]
    # a normal answer that merely contains braces is left alone
    text, _ = parse_tool_reply({"text": "{x} là ký hiệu tập hợp"}, "", [spec])
    assert text == "{x} là ký hiệu tập hợp"


def test_tool_preamble_says_tools_are_only_reachable_via_json():
    from agentdev.runtime.node.agent.providers._cli_common import build_tool_preamble

    text = build_tool_preamble([_weather_spec()], schema_enforced=True)
    assert "NOT exposed to you as native functions" in text and "never tell the user a listed tool is unavailable" in text


def test_cli_timeout_is_retried_by_the_default_retry_policy():
    from agentdev.entity.configs.node.agent import AgentRetryConfig
    from agentdev.runtime.node.agent.account_fallback import is_exhaustion_error, is_quota_error
    from agentdev.runtime.node.agent.providers._cli_common import CliTimeoutError

    p = ClaudeCliProvider(_cfg(timeout=7))
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=subprocess.TimeoutExpired("claude", 7)):
        with pytest.raises(CliTimeoutError) as info:
            p.call_model(CliClient("claude"), _conv(), [])
    policy = AgentRetryConfig(path="retry")
    assert isinstance(info.value, TimeoutError) and policy.should_retry(info.value)
    assert not is_quota_error(info.value) and not is_exhaustion_error(info.value)
    # Other CLI failures are still not retried.
    assert not policy.should_retry(CliProviderError("`claude` CLI is not logged in"))


def test_cli_timeout_gets_a_single_retry_not_the_full_policy():
    """One CLI call that keeps timing out must not hold the user for max_attempts x timeout."""
    from types import SimpleNamespace

    from agentdev.entity.configs.node.agent import AgentRetryConfig
    from agentdev.runtime.node.agent.providers._cli_common import CliTimeoutError
    from agentdev.runtime.node.executor import agent_executor as ae

    calls = {"n": 0}

    def always_times_out():
        calls["n"] += 1
        raise CliTimeoutError("`claude` CLI timed out after 300s")

    policy = AgentRetryConfig(path="retry", min_wait_seconds=0, max_wait_seconds=0)
    assert policy.max_attempts > 2
    fake_self = SimpleNamespace(log_manager=SimpleNamespace(warning=lambda *a, **k: None))
    node = SimpleNamespace(id="CTO")
    with pytest.raises(CliTimeoutError):
        ae.AgentNodeExecutor._execute_with_retry(fake_self, node, policy, always_times_out)
    assert calls["n"] == 1 + ae.MAX_CLI_TIMEOUT_RETRIES


# ---- effort passthrough, Codex streaming/no flat 300 s kill, Gemini timeout ----

def _cfg_params(**params):
    return SimpleNamespace(base_url=None, api_key=None, name="m1", provider="x", params=params)


def _codex_run(p):
    def fake(cmd, **kw):
        with open(cmd[cmd.index("-o") + 1], "w", encoding="utf-8") as fh:
            fh.write("answer")
        return _done()

    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake) as run:
        p.call_model(CliClient("codex"), _conv(), [])
    return run


def test_codex_effort_flag_and_unknown_value_omitted():
    cmd = _codex_run(CodexCliProvider(_cfg_params(effort="High"))).call_args.args[0]
    assert cmd[cmd.index("model_reasoning_effort=high") - 1] == "-c"
    cmd = _codex_run(CodexCliProvider(_cfg_params(effort="turbo"))).call_args.args[0]
    assert not any("model_reasoning_effort" in a for a in cmd)
    cmd = _codex_run(CodexCliProvider(_cfg())).call_args.args[0]
    assert not any("model_reasoning_effort" in a for a in cmd)


def test_codex_non_native_streams_without_300s_kill():
    kw = _codex_run(CodexCliProvider(_cfg())).call_args.kwargs
    assert kw["timeout"] >= 1800  # backstop only
    assert kw["on_stdout_line"] is not None and kw["idle_kill"] > 0  # idle watchdog on
    assert _codex_run(CodexCliProvider(_cfg(timeout=90))).call_args.kwargs["timeout"] == 90


def test_claude_effort_flag():
    p = ClaudeCliProvider(_cfg_params(effort="low"))
    fake, _ = _capture_claude(json.dumps({"type": "result", "result": "ok"}))
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake) as run:
        p.call_model(CliClient("claude"), _conv(), [])
    cmd = run.call_args.args[0]
    assert cmd[cmd.index("--effort") + 1] == "low"
    p = ClaudeCliProvider(_cfg_params(effort="bogus"))
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake) as run:
        p.call_model(CliClient("claude"), _conv(), [])
    assert "--effort" not in run.call_args.args[0]


def test_gemini_http_timeout_configurable():
    from agentdev.runtime.node.agent.providers.gemini_provider import GeminiProvider

    assert GeminiProvider(_cfg_params(timeout=90))._http_timeout_ms() == 90_000
    assert GeminiProvider(_cfg())._http_timeout_ms() == 600_000
    assert GeminiProvider(_cfg_params(timeout="x"))._http_timeout_ms() == 600_000
