"""A6-7: with AGENTDEV_MEMBER_PROTOCOL_SYSTEM the member protocol moves from the brief to the system prompt."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from agentdev.runtime.node.agent import team as team_mod
from agentdev.runtime.node.agent.team import TeamDelegation, TeamState, _nested_delegation, resolve_members
from agentdev.runtime.node.executor.agent_executor import AgentNodeExecutor

MARK = "You are a member of a team"


def _node(description=""):
    return SimpleNamespace(node_type="agent", description=description, role="", predecessors=[], successors=[])


def _team():
    nodes = {"cto": _node(), "be": _node("BE")}
    members = resolve_members("cto", [], nodes)
    return TeamDelegation(lead_id="cto", members=members, runner=lambda *a: [], prompt_service=None,
                          state=TeamState(), max_delegations=5, max_review_rounds=1, plan_approval=False, max_parallel=1)


def _executor():
    ex = object.__new__(AgentNodeExecutor)
    ex.context = SimpleNamespace(cancel_event=None, global_state={}, log_manager=MagicMock())
    return ex


def test_flag_off_keeps_protocol_in_brief(monkeypatch):
    monkeypatch.setenv("AGENTDEV_MEMBER_PROTOCOL_SYSTEM", "0")
    assert MARK in _team()._compose_brief("be", "do x")
    with _nested_delegation():
        assert _executor()._member_protocol_section(SimpleNamespace(id="be")) == ""


def test_flag_on_moves_protocol_to_system(monkeypatch):
    monkeypatch.setenv("AGENTDEV_MEMBER_PROTOCOL_SYSTEM", "1")
    brief = _team()._compose_brief("be", "do x")
    assert MARK not in brief and "do x" in brief
    with _nested_delegation():
        section = _executor()._member_protocol_section(SimpleNamespace(id="be"))
    assert MARK in section and "{" not in section
    # the same text for every lead: it is a stable prefix
    with _nested_delegation():
        assert section == _executor()._member_protocol_section(SimpleNamespace(id="other"))


def test_not_added_outside_a_delegation_or_for_a_lead(monkeypatch):
    monkeypatch.setenv("AGENTDEV_MEMBER_PROTOCOL_SYSTEM", "1")
    ex = _executor()
    assert ex._member_protocol_section(SimpleNamespace(id="be")) == ""  # top-level agent
    ex._active_teams()["lead"] = _team()
    with _nested_delegation():
        assert ex._member_protocol_section(SimpleNamespace(id="lead")) == ""
