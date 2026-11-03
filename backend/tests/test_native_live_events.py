"""Native CLI runs report their tool calls live, while the CLI runs, not all at once after it exits."""

import json
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agentdev.connections import cli_auth
from agentdev.entity.messages import Message, MessageRole
from agentdev.runtime.node.agent.providers._cli_common import CliCancelled, CliClient
from agentdev.runtime.node.agent.providers._native import (
    ClaudeStreamReader,
    CodexActivityReader,
    LiveEvents,
    NativeRunContext,
    read_claude_stream,
    read_codex_activity,
)
from agentdev.runtime.node.agent.providers.claude_cli_provider import ClaudeCliProvider
from agentdev.runtime.node.agent.providers.cli_cancel import cli_cancel_scope
from agentdev.runtime.node.agent.providers.codex_cli_provider import CodexCliProvider

RUN = "agentdev.connections.cli_auth.run_capture"
_REAL_RUN = cli_auth.run_capture


def _cfg():
    return SimpleNamespace(base_url=None, api_key=None, name="m1", provider="x", params={})


def _conv():
    return [Message(role=MessageRole.SYSTEM, content="You are a developer."),
            Message(role=MessageRole.USER, content="write hello.html")]


def _lines(*events):
    return [json.dumps(e) for e in events]


def _claude_events(edit_path):
    return _lines(
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Write", "input": {"file_path": edit_path, "content": "hi"}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "written", "is_error": False}]}},
        {"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": edit_path}}]}},
        {"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t2", "content": [{"type": "text", "text": "hi"}]}]}},
        {"type": "result", "subtype": "success", "is_error": False, "result": "Created hello.html.",
         "usage": {"input_tokens": 3, "output_tokens": 4}, "total_cost_usd": 0.001},
    )


# A fake CLI: prints the first `gate` lines, then waits (up to 8s) for `go` to exist before printing the
# rest. If tool events only arrive after exit, `go` is never created in time and the run is marked "late".
_FAKE_CLI = r"""
import json, os, sys, time
sys.stdin.read()
lines = json.loads(open(sys.argv[1], encoding="utf-8").read())
gate, go = int(sys.argv[2]), sys.argv[3]
for line in lines[:gate]:
    print(line, flush=True)
deadline = time.time() + 8
while not os.path.exists(go) and time.time() < deadline:
    time.sleep(0.05)
late = not os.path.exists(go)
if late:
    open(go + ".late", "w").close()
for line in lines[gate:]:
    if late and '"type": "result"' in line:
        event = json.loads(line); event["result"] = "LATE"; line = json.dumps(event)
    print(line, flush=True)
    time.sleep(0.05)
"""


@pytest.fixture
def fake_cli(tmp_path):
    script = tmp_path / "fake_cli.py"
    script.write_text(_FAKE_CLI, encoding="utf-8")

    def make(lines, gate):
        data = tmp_path / "lines.json"
        data.write_text(json.dumps(lines), encoding="utf-8")
        go = tmp_path / "go"
        calls = []

        def run(cmd, **kw):  # the real runner, with the vendor CLI swapped for the fake script
            calls.append(kw)
            return _REAL_RUN([sys.executable, str(script), str(data), str(gate), str(go)], **kw)

        return run, go, calls

    return make


def test_claude_native_reports_tool_calls_live_once(tmp_path, fake_cli):
    workspace = tmp_path / "project"
    workspace.mkdir()
    edit_path = str(workspace / "hello.html")
    lines = _claude_events(edit_path)
    run, go, calls = fake_cli(lines, gate=2)  # stop right after the first tool_use
    events = []

    def on_tool(stage, name, success, result, details):
        events.append((stage, name, success, result, details))
        if stage == "before" and name == "claude:Write":
            go.write_text("1")  # only reached while the CLI is still running if the event is live

    native = NativeRunContext(workspace=str(workspace), on_tool=on_tool)
    with patch(RUN, side_effect=run):
        resp = ClaudeCliProvider(_cfg()).call_model(CliClient("claude"), _conv(), [], tool_specs=None, native=native)

    assert callable(calls[0]["on_stdout_line"])
    assert resp.message.content.startswith("Created hello.html."), "the tool event did not arrive while running"
    # Exactly the calls the whole-output parser reports, in the same order, each once.
    expected = []
    full = "\n".join(lines) + "\n"
    result, changed = read_claude_stream(full, NativeRunContext(workspace=str(workspace),
                                                                on_tool=lambda *a: expected.append(a)))
    assert events == expected
    assert [(e[0], e[1]) for e in events] == [("before", "claude:Write"), ("after", "claude:Write"),
                                             ("before", "claude:Read"), ("after", "claude:Read")]
    # Final result and changed files identical to parsing the whole output.
    raw = dict(resp.raw_response)
    assert raw.pop("changed_files") == changed == [edit_path]
    assert raw == result


def test_claude_native_cancel_kills_cli_mid_run(tmp_path, fake_cli):
    workspace = tmp_path / "project"
    workspace.mkdir()
    run, _go, _calls = fake_cli(_claude_events(str(workspace / "a.html")), gate=2)  # never released
    cancel = threading.Event()
    events = []

    def on_tool(stage, name, *rest):
        events.append((stage, name))
        cancel.set()  # stop the run as soon as the first live tool event shows up

    native = NativeRunContext(workspace=str(workspace), on_tool=on_tool)
    started = time.monotonic()
    with patch(RUN, side_effect=run), cli_cancel_scope(cancel), pytest.raises(CliCancelled):
        ClaudeCliProvider(_cfg()).call_model(CliClient("claude"), _conv(), [], tool_specs=None, native=native)
    assert time.monotonic() - started < 6  # killed, not waiting out the fake CLI's 8s gate
    time.sleep(0.3)
    assert events == [("before", "claude:Write")]  # nothing reported after the abort


def test_codex_native_reports_started_items_live(tmp_path, fake_cli):
    workspace = tmp_path / "project"
    workspace.mkdir()
    cmd_item = {"id": "i1", "type": "command_execution", "command": "ls"}
    lines = _lines(
        {"type": "thread.started"},
        {"type": "item.started", "item": {**cmd_item, "status": "in_progress", "aggregated_output": ""}},
        {"type": "item.completed", "item": {**cmd_item, "status": "completed", "exit_code": 0,
                                            "aggregated_output": "a.txt"}},
        {"type": "item.completed", "item": {"id": "i2", "type": "file_change", "status": "completed",
                                            "changes": [{"path": "a.txt", "kind": "add"}]}},
        {"type": "item.completed", "item": {"id": "i3", "type": "agent_message", "text": "Done."}},
    )
    run, go, _calls = fake_cli(lines, gate=2)  # stop right after item.started
    events = []

    def on_tool(stage, name, success, result, details):
        events.append((stage, name, success))
        if stage == "before" and name == "codex:shell":
            go.write_text("1")

    native = NativeRunContext(workspace=str(workspace), allow_commands=True, on_tool=on_tool)
    with patch(RUN, side_effect=run):
        resp = CodexCliProvider(_cfg()).call_model(CliClient("codex"), _conv(), [], tool_specs=None, native=native)
    assert not (tmp_path / "go.late").exists(), "the item.started event did not arrive while running"
    assert events == [("before", "codex:shell", None), ("after", "codex:shell", True),
                      ("before", "codex:apply_patch", None), ("after", "codex:apply_patch", True)]
    assert resp.raw_response["changed_files"] == ["a.txt"]
    assert resp.message.content.startswith("Done.")


def test_live_events_feed_each_line_once_and_catch_up_at_finish():
    events = []
    native = NativeRunContext(workspace=".", on_tool=lambda *a: events.append((a[0], a[1])))
    lines = _claude_events("x.html")
    stdout = "".join(line + "\n" for line in lines)
    live = LiveEvents(ClaudeStreamReader(native))
    for line in lines[:2]:  # only part of the output streamed live
        live.push(line + "\n")
    live.finish(stdout)
    assert events == [("before", "claude:Write"), ("after", "claude:Write"),
                      ("before", "claude:Read"), ("after", "claude:Read")]
    live.finish(stdout)  # idempotent
    assert len(events) == 4


def test_live_events_abort_stops_reporting():
    events = []
    native = NativeRunContext(workspace=".", on_tool=lambda *a: events.append(a[1]))
    live = LiveEvents(ClaudeStreamReader(native))
    live.abort()
    for line in _claude_events("x.html"):
        live.push(line + "\n")
    live.finish("")
    assert events == []


def test_codex_reader_completed_without_start_reports_both():
    events = []
    native = NativeRunContext(workspace=".", on_tool=lambda *a: events.append((a[0], a[1], a[2])))
    out = "\n".join(_lines(
        {"type": "item.completed", "item": {"id": "c1", "type": "command_execution", "command": "x", "exit_code": 2}},
    ))
    assert read_codex_activity(out, native) == []
    assert events == [("before", "codex:shell", None), ("after", "codex:shell", False)]
    reader = CodexActivityReader(native)
    reader.feed({"type": "item.started", "item": {"id": "c2", "type": "command_execution", "command": "y"}})
    reader.feed({"type": "item.started", "item": {"id": "c2", "type": "command_execution", "command": "y"}})
    assert events[-1] == ("before", "codex:shell", None) and len(events) == 3  # a repeated start is ignored


def test_run_capture_streams_stdout_lines_before_exit():
    seen = []
    code = "import sys, time\nprint('one', flush=True)\ntime.sleep(1.0)\nprint('two', flush=True)\n"
    started = time.monotonic()
    done = cli_auth.run_capture([sys.executable, "-c", code], input="", timeout=20,
                                on_stdout_line=lambda line: seen.append((line, time.monotonic() - started)))
    assert done.stdout.replace("\r\n", "\n") == "one\ntwo\n"
    assert [s[0] for s in seen] == ["one\n", "two\n"]
    assert seen[0][1] < seen[1][1] - 0.5  # the first line arrived well before the process ended
