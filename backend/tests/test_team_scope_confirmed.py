import pytest

from agentdev.runtime.node.agent.team import (
    PLAN_RULE_APPROVED_EDITS,
    PLAN_RULE_CONFIRMED,
    SUBMIT_PLAN_TOOL,
    MAX_MEMBER_RESULT_CHARS,
    MEMBER_BUSY_WAIT_SECONDS,
    TeamState,
    has_go_ahead,
    starts_with_approval,
)
from tests.test_team_logic import _plan_turns, _state, _team, _tools


@pytest.mark.parametrize("text", ["Làm luôn nhé", "cứ làm đi", "go ahead and build it", "Just do it", "ok làm"])
def test_go_ahead_phrases(text):
    assert has_go_ahead(text)


@pytest.mark.parametrize("text", ["đừng làm luôn", "do not go ahead yet", "làm web bán hàng", ""])
def test_not_go_ahead(text):
    assert not has_go_ahead(text)


def test_go_ahead_message_skips_the_plan_gate():
    team = _team(state=_state("Làm cho tôi trang quản trị, làm luôn nhé"))
    assert team.state.scope_confirmed
    assert SUBMIT_PLAN_TOOL not in _tools(team)
    assert PLAN_RULE_CONFIRMED in team.system_prompt_section()


def test_ask_user_answer_confirms_scope():
    state = TeamState()
    assert not state.scope_confirmed
    state.add_exchange("Which stack?", "Vue")
    assert state.scope_confirmed


def test_approval_with_edits_executes_without_replanning():
    assert starts_with_approval("ok nhưng dùng Vue thay React")
    assert not starts_with_approval("đổi stack sang Django")
    team = _team(state=_state("ok nhưng dùng Vue thay React", _plan_turns()))
    assert team.plan_approved_with_edits and not team.plan_gate_enabled
    assert SUBMIT_PLAN_TOOL not in _tools(team)
    assert PLAN_RULE_APPROVED_EDITS in team.system_prompt_section()


def test_budgets():
    assert MAX_MEMBER_RESULT_CHARS == 2000 and MEMBER_BUSY_WAIT_SECONDS == 120
