"""Stop kills a running CLI; quota detection ignores model/file text; media is never copied."""

import json
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agentdev.connections import cli_auth
from agentdev.entity.messages import AttachmentRef, Message, MessageBlock, MessageBlockType, MessageRole
from agentdev.runtime.node.agent.account_fallback import QuotaExceededError, looks_like_quota
from agentdev.runtime.node.agent.providers._cli_common import (
    MAX_INLINE_TEXT_BYTES,
    CliClient,
    CliProviderError,
    attachments_section,
    run_cli,
    stage_attachments,
)
from agentdev.runtime.node.agent.providers._native import NativeRunContext
from agentdev.runtime.node.agent.providers.claude_cli_provider import ClaudeCliProvider
from agentdev.runtime.node.agent.providers.cli_cancel import CliCancelled, cli_cancel_scope, current_cancel_event


def _cfg():
    return SimpleNamespace(base_url=None, api_key=None, name="m1", provider="x", params={})


def _done(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


# --- cancel -----------------------------------------------------------------------------------------


def test_cancel_scope_sets_and_resets():
    assert current_cancel_event() is None
    with cli_cancel_scope(None):
        assert current_cancel_event() is None
    event = threading.Event()
    with cli_cancel_scope(event):
        assert current_cancel_event() is event
    assert current_cancel_event() is None


def test_run_cli_is_killed_when_cancel_event_fires(tmp_path):
    event = threading.Event()
    threading.Timer(0.5, event.set).start()
    cmd = [sys.executable, "-c", "import sys, time; sys.stdin.read(); time.sleep(60)"]
    start = time.monotonic()
    with cli_cancel_scope(event), pytest.raises(CliCancelled):
        run_cli(cmd, "prompt", 120, "fake", str(tmp_path))
    assert time.monotonic() - start < 15


def test_run_cli_already_cancelled_does_not_spawn(tmp_path):
    event = threading.Event()
    event.set()
    with cli_cancel_scope(event), patch("subprocess.Popen") as popen, pytest.raises(CliCancelled):
        run_cli(["x"], "p", 10, "fake", str(tmp_path))
    popen.assert_not_called()


def test_run_capture_feeds_large_stdin_and_reads_output():
    big = "a" * 2_000_000
    code = "import sys; data = sys.stdin.read(); print(len(data)); print('e', file=sys.stderr)"
    done = cli_auth.run_capture([sys.executable, "-c", code], input=big, timeout=60, cancel_event=threading.Event())
    assert done.returncode == 0 and done.stdout.strip() == str(len(big)) and done.stderr.strip() == "e"


# --- quota patterns ---------------------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "You've hit your limit · resets 3pm",
    "You've hit your usage limit. Try again later.",
    "Claude AI usage limit reached|1700000000",
    "You've reached your weekly limit",
    "Credit balance is too low",
])
def test_quota_positive(text):
    assert looks_like_quota(text)


@pytest.mark.parametrize("text", [
    "The API quota is configured in settings.py",
    "Raise the rate limit to 100 requests per minute",
    "Retry when you hit your rate limit",
    "The function hits its limit at 10 items",
    "limit reached for this loop; breaking",
    "",
])
def test_quota_negative(text):
    assert not looks_like_quota(text)


def _native(tmp_path):
    return NativeRunContext(workspace=str(tmp_path))


def test_native_quota_not_detected_from_file_contents(tmp_path):
    tool_result = {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1",
                   "content": "docs: when you've hit your usage limit, wait for the reset"}]}}
    out = json.dumps(tool_result) + "\n"
    p = ClaudeCliProvider(_cfg())
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(rc=1, out=out, err="boom")):
        with pytest.raises(CliProviderError):
            p.call_model(CliClient("claude"), [Message(role=MessageRole.USER, content="hi")], [], native=_native(tmp_path))


def test_native_quota_detected_from_result_event(tmp_path):
    result = {"type": "result", "subtype": "error_during_execution", "is_error": True,
              "result": "You've hit your limit · resets 3pm"}
    p = ClaudeCliProvider(_cfg())
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(rc=1, out=json.dumps(result) + "\n")):
        with pytest.raises(QuotaExceededError):
            p.call_model(CliClient("claude"), [Message(role=MessageRole.USER, content="hi")], [], native=_native(tmp_path))


def test_quota_checked_before_login():
    payload = json.dumps({"is_error": True, "result": "You've hit your usage limit for this login"})
    p = ClaudeCliProvider(_cfg())
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(rc=1, out=payload)):
        with pytest.raises(QuotaExceededError):
            p.call_model(CliClient("claude"), [Message(role=MessageRole.USER, content="hi")], [])


# --- attachments ------------------------------------------------------------------------------------


def test_video_is_not_read_or_copied(tmp_path):
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"\0" * 4096)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    msg = Message(role=MessageRole.USER, content=[MessageBlock(MessageBlockType.VIDEO, attachment=AttachmentRef(
        "v1", "video/mp4", "demo.mp4", local_path=str(video)))])
    with patch("agentdev.runtime.node.agent.providers._cli_common._attachment_bytes") as read:
        staged = stage_attachments([msg], str(cwd))
    read.assert_not_called()
    assert not (cwd / "attachments").exists()
    assert staged[0].kind == "media" and staged[0].size == 4096
    section = attachments_section(staged, can_read_files=True)
    assert "demo.mp4" in section and str(video) in section and "4 KB" in section


def test_large_text_is_truncated_with_path(tmp_path):
    big = tmp_path / "log.txt"
    big.write_text("x" * (MAX_INLINE_TEXT_BYTES * 3), encoding="utf-8")
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    msg = Message(role=MessageRole.USER, content=[MessageBlock(MessageBlockType.FILE, attachment=AttachmentRef(
        "f1", "text/plain", "log.txt", local_path=str(big)))])
    staged = stage_attachments([msg], str(cwd))
    item = staged[0]
    assert item.kind == "text" and item.truncated and len(item.text) == MAX_INLINE_TEXT_BYTES
    assert (cwd / item.rel_path).stat().st_size == MAX_INLINE_TEXT_BYTES * 3
    section = attachments_section(staged, can_read_files=True)
    assert f"(truncated; full file at `{item.rel_path}`, read it if needed)" in section
    assert len(section) < MAX_INLINE_TEXT_BYTES + 1000
