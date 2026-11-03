"""Files the user attaches reach the Claude / Codex CLIs; quota errors are classified."""

import base64
import os
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agentdev.entity.messages import AttachmentRef, Message, MessageBlock, MessageBlockType, MessageRole
from agentdev.runtime.node.agent.account_fallback import QuotaExceededError
from agentdev.runtime.node.agent.providers._cli_common import CliClient, stage_attachments
from agentdev.runtime.node.agent.providers.claude_cli_provider import ClaudeCliProvider
from agentdev.runtime.node.agent.providers.codex_cli_provider import CodexCliProvider

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
)


def _cfg():
    return SimpleNamespace(base_url=None, api_key=None, name="m1", provider="x", params={})


def _done(rc=0, out="", err=""):
    return subprocess.CompletedProcess([], rc, out, err)


def _conversation(tmp_path):
    image = tmp_path / "screen.png"
    image.write_bytes(PNG)
    notes = tmp_path / "spec.md"
    notes.write_text("# Spec\nLogin must lock after 5 tries", encoding="utf-8")
    blocks = [
        MessageBlock.text_block("Fix the login page as in the screenshot"),
        MessageBlock(MessageBlockType.IMAGE, attachment=AttachmentRef("a1", "image/png", "screen.png", local_path=str(image))),
        MessageBlock(MessageBlockType.FILE, attachment=AttachmentRef("a2", "text/markdown", "spec.md", local_path=str(notes))),
        MessageBlock(MessageBlockType.VIDEO, attachment=AttachmentRef(
            "a3", "video/mp4", "demo.mp4", data_uri="data:video/mp4;base64," + base64.b64encode(b"vid").decode())),
    ]
    return [Message(role=MessageRole.SYSTEM, content="sys"), Message(role=MessageRole.USER, content=blocks)]


def test_stage_attachments(tmp_path):
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    staged = {item.name: item for item in stage_attachments(_conversation(tmp_path), str(cwd))}
    assert staged["spec.md"].kind == "text" and "lock after 5 tries" in staged["spec.md"].text
    assert staged["screen.png"].kind == "image" and (cwd / staged["screen.png"].rel_path).read_bytes() == PNG
    assert staged["demo.mp4"].kind == "media"


def test_claude_gets_read_tool_and_file_list(tmp_path):
    p = ClaudeCliProvider(_cfg())
    seen = {}

    def fake(cmd, **kw):
        seen["cmd"], seen["input"] = cmd, kw["input"]
        seen["exists"] = os.path.isfile(os.path.join(kw["cwd"], "attachments", "screen.png"))
        return _done(out='{"result":"ok","is_error":false}')

    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        p.call_model(CliClient("claude"), _conversation(tmp_path), [])
    cmd = seen["cmd"]
    assert cmd[cmd.index("--tools") + 1] == "Read"
    assert "--allowedTools" not in cmd  # no blanket allow: reads stay inside the temp working dir
    assert seen["exists"]
    assert "attachments/screen.png" in seen["input"] and "Read tool" in seen["input"]
    assert "lock after 5 tries" in seen["input"]


def test_claude_without_attachments_keeps_tools_off():
    p = ClaudeCliProvider(_cfg())
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(out='{"result":"ok"}')) as run:
        p.call_model(CliClient("claude"), [Message(role=MessageRole.USER, content="hi")], [])
    cmd = run.call_args[0][0]
    assert cmd[cmd.index("--tools") + 1] == ""


def test_codex_gets_image_flag(tmp_path):
    p = CodexCliProvider(_cfg())
    seen = {}

    def fake(cmd, **kw):
        seen["cmd"], seen["input"] = cmd, kw["input"]
        images = [a.split("=", 1)[1] for a in cmd if a.startswith("--image=")]
        seen["image_ok"] = len(images) == 1 and os.path.isfile(images[0]) and cmd[-1] == "-"
        with open(cmd[cmd.index("-o") + 1], "w", encoding="utf-8") as fh:
            fh.write("answer")
        return _done()

    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        p.call_model(CliClient("codex"), _conversation(tmp_path), [])
    assert seen["image_ok"]
    assert "lock after 5 tries" in seen["input"]


def test_claude_limit_raises_quota_error():
    p = ClaudeCliProvider(_cfg())
    payload = '{"is_error":true,"result":"Claude AI usage limit reached|1730000000"}'
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(out=payload)):
        with pytest.raises(QuotaExceededError):
            p.call_model(CliClient("claude"), [Message(role=MessageRole.USER, content="hi")], [])


def test_codex_limit_vs_telemetry():
    p = CodexCliProvider(_cfg())
    telemetry = '{"type":"token_count","rate_limits":{"primary":{"used_percent":10}}}'
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(rc=1, out=telemetry, err="boom")):
        with pytest.raises(Exception) as info:
            p.call_model(CliClient("codex"), [Message(role=MessageRole.USER, content="hi")], [])
    assert not isinstance(info.value, QuotaExceededError)
    limit = '{"type":"error","message":"You\'ve hit your usage limit"}'
    with patch("agentdev.connections.cli_auth.run_capture", return_value=_done(rc=1, out=limit, err="")):
        with pytest.raises(QuotaExceededError):
            p.call_model(CliClient("codex"), [Message(role=MessageRole.USER, content="hi")], [])


def test_claude_normal_mode_replaces_cli_system_prompt():
    p = ClaudeCliProvider(_cfg())
    seen = {}

    def fake(cmd, **kw):
        seen["cmd"] = cmd
        path = cmd[cmd.index("--system-prompt-file") + 1]
        seen["system"] = open(path, encoding="utf-8").read()
        return _done(out='{"result":"ok"}')

    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        p.call_model(CliClient("claude"), [Message(role=MessageRole.USER, content="hi")], [])
    assert "AgentDev" in seen["system"]
    assert seen["cmd"][seen["cmd"].index("--setting-sources") + 1] == "project"
