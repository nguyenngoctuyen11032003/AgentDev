"""Agents that write to the project workspace get the project standards (structure, README, ports AgentDev
uses); pure chat agents do not. CLI subprocesses are told the reserved ports through the environment."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from agentdev.entity.messages import MessageRole
from agentdev.runtime.node.agent.providers._cli_common import cli_run_env
from agentdev.runtime.node.executor.agent_executor import AgentNodeExecutor
from agentdev.runtime.node.executor.workspace_standards import (
    WORKSPACE_STANDARDS,
    writes_workspace,
)
from agentdev.utils.reserved_ports import RESERVED_PORTS, RESERVED_PORTS_ENV

HEADING = "# Project workspace standards"


def _executor():
    executor = object.__new__(AgentNodeExecutor)
    executor.context = SimpleNamespace(cancel_event=None, global_state={}, log_manager=MagicMock())
    executor._active_teams = dict
    return executor


def _node():
    return SimpleNamespace(id="dev", role="You are the backend engineer.", description="")


def test_writes_workspace_detects_native_and_write_tools():
    assert writes_workspace(True, [])
    assert writes_workspace(False, ["read_file_segment", "save_file"])
    assert writes_workspace(False, ["run_shell_command"])
    assert not writes_workspace(False, [])
    assert not writes_workspace(False, ["read_file_segment", "search_in_files", "web_search"])


def test_section_included_for_workspace_writer():
    prompt = _executor()._build_system_prompt(_node(), None, workspace_writer=True)
    assert HEADING in prompt
    assert prompt.index("You are the backend engineer.") < prompt.index(HEADING)


def test_section_excluded_for_chat_agent():
    prompt = _executor()._build_system_prompt(_node(), None) or ""
    assert HEADING not in prompt
    prompt = _executor()._build_system_prompt(_node(), None, workspace_writer=False) or ""
    assert HEADING not in prompt


def test_prepared_messages_carry_the_flag():
    messages = _executor()._prepare_prompt_messages(_node(), "build an API", None, workspace_writer=True)
    assert messages[0].role is MessageRole.SYSTEM and HEADING in messages[0].content
    messages = _executor()._prepare_message_conversation(_node(), [], None)
    assert HEADING not in (messages[0].content or "")


def test_standards_name_reserved_ports_and_core_rules():
    for port in ("5173", "5174", "6400"):
        assert port in WORKSPACE_STANDARDS
    for phrase in ("README.md", ".gitignore", ".env.example", "PORT", "AGENTDEV_RESERVED_PORTS", "server.port"):
        assert phrase in WORKSPACE_STANDARDS
    assert len(WORKSPACE_STANDARDS.split()) < 400


def test_cli_env_lists_reserved_ports(tmp_path):
    env = cli_run_env(str(tmp_path))
    assert env[RESERVED_PORTS_ENV] == ",".join(str(p) for p in RESERVED_PORTS)
    assert {5173, 5174, 6400} <= set(RESERVED_PORTS)
