"""Token savings for CLI tool loops: a byte-stable prompt prefix and Claude Code session resume."""

import json
import os
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agentdev.connections import cli_auth
from agentdev.entity.messages import Message, MessageRole, ToolCallPayload
from agentdev.entity.tool_spec import ToolSpec
from agentdev.runtime.node.agent.account_fallback import QuotaExceededError
from agentdev.runtime.node.agent.providers._cli_common import (
    CliClient,
    CliRunState,
    build_tool_preamble,
    flatten_conversation,
    split_conversation,
)
from agentdev.runtime.node.agent.providers.claude_cli_provider import ClaudeCliProvider
from agentdev.runtime.node.agent.providers.cli_cancel import CliCancelled, cli_cancel_scope

WEATHER = ToolSpec(
    name="get_temperature",
    description="Get the current temperature of a city",
    parameters={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
)
ROLE = "You are Researcher. SKILLS-CATALOG-MARKER"
TASK = "FIRST-USER-TASK: weather in Hanoi and Hue?"


@pytest.fixture(autouse=True)
def _claude_home(tmp_path, monkeypatch):
    """Session files go to a throwaway Claude config dir; the switch env var is cleared."""
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude_home"))
    monkeypatch.delenv("AGENTDEV_CLI_SESSION_REUSE", raising=False)
    return tmp_path / "claude_home"


def _cfg(**params):
    return SimpleNamespace(base_url=None, api_key=None, name="m1", provider="x", params=params)


def _done(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


def _reply(calls=None, text="", cost=None):
    payload = {"is_error": False, "structured_output": {"text": text, "tool_calls": calls or []}, "result": "{}",
               "usage": {"input_tokens": 3, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 10,
                         "output_tokens": 2}}
    if cost is not None:
        payload["total_cost_usd"] = cost
    return json.dumps(payload)


class FakeClaude:
    """Records every call (argv, stdin, system prompt file) and answers from a script of outputs."""

    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.calls = []

    def __call__(self, cmd, **kw):
        with open(cmd[cmd.index("--system-prompt-file") + 1], encoding="utf-8") as fh:
            system = fh.read()
        self.calls.append({"cmd": cmd, "input": kw["input"], "system": system, "cwd": kw.get("cwd"),
                           "cancel": kw.get("cancel_event")})
        out = self.outputs.pop(0)
        out = out(cmd, **kw) if callable(out) else out
        return _done(out=out) if isinstance(out, str) else out


def _flag(cmd, name):
    return cmd[cmd.index(name) + 1] if name in cmd else None


def _start():
    return [Message(role=MessageRole.SYSTEM, content=ROLE), Message(role=MessageRole.USER, content=TASK)]


def _step(conv, response, result):
    """What the agent executor does between two model calls: append the reply and the tool results."""
    conv.append(response.message.clone())
    for call in response.message.tool_calls:
        conv.append(Message(role=MessageRole.TOOL, content=result, tool_call_id=call.id,
                            metadata={"tool_name": call.function_name}))


CALL_HANOI = [{"name": "get_temperature", "arguments": {"city": "Hanoi"}}]
CALL_HUE = [{"name": "get_temperature", "arguments": {"city": "Hue"}}]


# --- (a) stable prefix --------------------------------------------------------------------------------


def test_split_matches_flatten_and_static_part_is_stable_across_steps():
    preamble = build_tool_preamble([WEATHER], True)
    conv = _start()
    static1, transcript1 = split_conversation(conv, preamble)
    assert flatten_conversation(conv, preamble) == static1 + "\n\n" + transcript1
    conv += [
        Message(role=MessageRole.ASSISTANT, content="",
                tool_calls=[ToolCallPayload(id="c1", function_name="get_temperature", arguments='{"city": "Hanoi"}')]),
        Message(role=MessageRole.TOOL, content="31C", tool_call_id="c1", metadata={"tool_name": "get_temperature"}),
    ]
    static2, transcript2 = split_conversation(conv, preamble)
    assert static2 == static1  # byte-identical prefix on every step of the tool loop
    assert flatten_conversation(conv, preamble) == static2 + "\n\n" + transcript2
    assert ROLE in static1 and "get_temperature" in static1 and TASK not in static1
    assert "31C" in transcript2 and ROLE not in transcript2


def test_stateless_steps_share_identical_system_prompt():
    fake = FakeClaude(_reply(CALL_HANOI), _reply(text="done"))
    p = ClaudeCliProvider(_cfg(session_reuse=False))
    conv = _start()
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        first = p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
        _step(conv, first, "31C")
        p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
    one, two = fake.calls
    assert one["system"] == two["system"] and ROLE in one["system"] and "get_temperature" in one["system"]
    assert TASK in one["input"] and TASK in two["input"] and "31C" in two["input"]
    assert one["cwd"] == two["cwd"]  # same working folder: the CLI's cwd-dependent prompt part stays equal
    for call in fake.calls:
        assert "--no-session-persistence" in call["cmd"] and "--resume" not in call["cmd"]
        assert "--strict-mcp-config" in call["cmd"]
    p.close()
    assert not os.path.exists(one["cwd"])


# --- (b) session resume -------------------------------------------------------------------------------


def test_second_step_resumes_session_and_sends_only_new_messages():
    fake = FakeClaude(_reply(CALL_HANOI, cost=0.03), _reply(CALL_HUE, cost=0.05), _reply(text="done", cost=0.06))
    p = ClaudeCliProvider(_cfg())
    conv = _start()
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        r1 = p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
        _step(conv, r1, "HANOI-RESULT 31C")
        r2 = p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
        _step(conv, r2, "HUE-RESULT 29C")
        r3 = p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
    first, second, third = fake.calls
    sid = _flag(first["cmd"], "--session-id")
    assert sid and "--no-session-persistence" not in first["cmd"] and TASK in first["input"]
    assert _flag(second["cmd"], "--resume") == sid and _flag(third["cmd"], "--resume") == sid
    for call in (second, third):
        assert "--session-id" not in call["cmd"] and "--no-session-persistence" not in call["cmd"]
        # Same isolation and reply contract as the first step.
        assert _flag(call["cmd"], "--setting-sources") == "project" and "--strict-mcp-config" in call["cmd"]
        assert _flag(call["cmd"], "--tools") == "" and "--json-schema" in call["cmd"]
        assert TASK not in call["input"] and ROLE not in call["input"]
    assert "HANOI-RESULT" in second["input"] and "HUE-RESULT" not in second["input"]
    assert "HUE-RESULT" in third["input"] and "HANOI-RESULT" not in third["input"]
    assert "[Tool result] call_id=" in third["input"] and "tool-calling protocol" in third["input"]
    assert r3.message.content == "done"
    # Resumed sessions report a running total cost; each call keeps only its own share.
    costs = [round(r.raw_response["total_cost_usd"], 6) for r in (r1, r2, r3)]
    assert costs == [0.03, 0.02, 0.01]
    usage = p.extract_token_usage(r2.raw_response)
    assert usage.input_tokens == 113 and usage.metadata["cache_read_input_tokens"] == 100
    assert usage.metadata["session"] == "resumed"


def test_resume_error_falls_back_to_stateless_for_the_rest_of_the_run():
    fake = FakeClaude(_reply(CALL_HANOI), _done(rc=1, err="No conversation found with session ID"),
                      _reply(CALL_HUE), _reply(text="done"))
    p = ClaudeCliProvider(_cfg())
    conv = _start()
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        r1 = p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
        _step(conv, r1, "31C")
        r2 = p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
        _step(conv, r2, "29C")
        r3 = p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
    assert [c.function_name for c in r2.message.tool_calls] == ["get_temperature"] and r3.message.content == "done"
    resumed, fallback, later = fake.calls[1:]
    assert "--resume" in resumed["cmd"]
    for call in (fallback, later):
        assert "--no-session-persistence" in call["cmd"] and "--resume" not in call["cmd"]
        assert TASK in call["input"]  # full conversation again


def test_quota_on_resume_is_raised_for_account_fallback():
    limit = json.dumps({"is_error": True, "result": "You've hit your usage limit"})
    fake = FakeClaude(_reply(CALL_HANOI), _done(rc=1, out=limit))
    p = ClaudeCliProvider(_cfg())
    conv = _start()
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        r1 = p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
        _step(conv, r1, "31C")
        with pytest.raises(QuotaExceededError):
            p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
    assert len(fake.calls) == 2


def test_changed_history_or_tools_start_a_new_session():
    fake = FakeClaude(_reply(CALL_HANOI), _reply(text="a"), _reply(text="b"))
    p = ClaudeCliProvider(_cfg())
    conv = _start()
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        r1 = p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
        _step(conv, r1, "31C")
        edited = [Message(role=MessageRole.SYSTEM, content=ROLE + " (edited)")] + conv[1:]
        p.call_model(CliClient("claude"), edited, [], tool_specs=[WEATHER])
        other = ToolSpec(name="search", description="Search", parameters={"type": "object", "properties": {}})
        p.call_model(CliClient("claude"), conv, [], tool_specs=[other])
    sids = [_flag(c["cmd"], "--session-id") for c in fake.calls]
    assert all(sids) and len(set(sids)) == 3
    assert not any("--resume" in c["cmd"] for c in fake.calls)


def test_calls_without_tools_never_persist_a_session():
    fake = FakeClaude(_done(out='{"result":"hi"}'))
    p = ClaudeCliProvider(_cfg())
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        p.call_model(CliClient("claude"), _start(), [])
    assert "--no-session-persistence" in fake.calls[0]["cmd"]


@pytest.mark.parametrize("value", ["0", "off", "false"])
def test_env_switch_turns_session_reuse_off(monkeypatch, value):
    monkeypatch.setenv("AGENTDEV_CLI_SESSION_REUSE", value)
    fake = FakeClaude(_reply(CALL_HANOI), _reply(text="done"))
    p = ClaudeCliProvider(_cfg())
    conv = _start()
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        r1 = p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
        _step(conv, r1, "31C")
        p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
    assert all("--no-session-persistence" in c["cmd"] for c in fake.calls)


def test_close_deletes_session_transcript_and_project_folder(_claude_home):
    def started(cmd, **kw):
        # What Claude Code writes: projects/<cwd with non-alphanumerics as "-">/<session id>.jsonl
        project = _claude_home / "projects" / "".join(ch if ch.isalnum() else "-" for ch in kw["cwd"])
        project.mkdir(parents=True, exist_ok=True)
        (project / f"{_flag(cmd, '--session-id')}.jsonl").write_text("{}", encoding="utf-8")
        (project / "memory").mkdir(exist_ok=True)
        return _reply(CALL_HANOI)

    fake = FakeClaude(started)
    p = ClaudeCliProvider(_cfg())
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        p.call_model(CliClient("claude"), _start(), [], tool_specs=[WEATHER])
    cwd = fake.calls[0]["cwd"]
    projects = _claude_home / "projects"
    assert len(list(projects.glob("*/*.jsonl"))) == 1
    p.close()
    assert list(projects.iterdir()) == [] and not os.path.exists(cwd)


def test_run_state_is_released_when_provider_is_garbage_collected():
    class Owner:
        pass

    owner = Owner()
    state = CliRunState(owner)
    workdir = state.workdir()
    assert os.path.isdir(workdir)
    del owner
    import gc

    gc.collect()
    assert not os.path.exists(workdir)


# --- cancel -------------------------------------------------------------------------------------------


def test_cancel_still_kills_a_resumed_call():
    real_run_capture = cli_auth.run_capture

    def slow(cmd, **kw):
        # The resumed call runs a real long process under the same cancel event the executor set.
        sleeper = [sys.executable, "-c", "import sys, time; sys.stdin.read(); time.sleep(60)"]
        return real_run_capture(sleeper, input=kw["input"], timeout=120, cwd=kw.get("cwd"),
                                cancel_event=kw.get("cancel_event"))

    fake = FakeClaude(_reply(CALL_HANOI), slow, _reply(text="fresh"))
    p = ClaudeCliProvider(_cfg())
    conv = _start()
    event = threading.Event()
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        r1 = p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
        _step(conv, r1, "31C")
        threading.Timer(0.5, event.set).start()
        with cli_cancel_scope(event), pytest.raises(CliCancelled):
            p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
        assert fake.calls[1]["cancel"] is event and "--resume" in fake.calls[1]["cmd"]
        # The interrupted session is dropped: a retry starts a fresh one instead of resuming it.
        p.call_model(CliClient("claude"), conv, [], tool_specs=[WEATHER])
    assert "--session-id" in fake.calls[2]["cmd"]
