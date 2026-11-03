"""Lead chat quality: small-talk fast path, account-limit notes, compact follow-up history."""

from types import SimpleNamespace

import pytest

from agentdev.api.services.conversation_turns import (
    MAX_OLD_ANSWER_CHARS,
    build_transcript,
    make_turn,
)
from agentdev.entity.messages import Message, MessageRole
from agentdev.runtime.node.agent.team import (
    LEAD_SMALL_TALK,
    TeamDelegation,
    TeamState,
    get_team_state,
    is_small_talk,
    resolve_members,
)
from agentdev.runtime.node.agent.account_fallback import FallbackState


def _node(description=""):
    return SimpleNamespace(node_type="agent", description=description, role="", predecessors=[], successors=[])


def _team(runner=None, state=None, **kwargs):
    nodes = {"cto": _node(), "be": _node("BE"), "qa": _node("QA")}
    opts = dict(max_delegations=5, max_review_rounds=2, plan_approval=True)
    opts.update(kwargs)
    return TeamDelegation(
        lead_id="cto",
        members=resolve_members("cto", [], nodes),
        runner=runner or (lambda m, i, l: [Message(role=MessageRole.ASSISTANT, content=f"{m} done")]),
        prompt_service=None,
        state=state or TeamState(),
        **opts,
    )


@pytest.mark.parametrize(
    "text", ["hi", "Hello!", "Xin chào!", "chào bạn", "cảm ơn nhé 🙏", "thanks!!", "Thank you.", "こんにちは", "cam on"]
)
def test_greetings_and_thanks_are_small_talk(text):
    assert is_small_talk(text)


@pytest.mark.parametrize(
    "text",
    ["", "ok", "làm đi", "đồng ý", "go ahead", "hi, fix the login bug", "chào bạn, giúp mình sửa lỗi đăng nhập",
     "what is react?", "thanks, now add a logout button"],
)
def test_requests_and_approvals_are_not_small_talk(text):
    assert not is_small_talk(text)


def test_small_talk_lead_gets_short_prompt_and_no_team_tools():
    state = TeamState()
    state.set_user_language("Xin chào!")
    team = _team(state=state)
    assert team.system_prompt_section() == LEAD_SMALL_TALK
    assert team.tool_specs() == []


def test_real_request_keeps_full_protocol_and_tools():
    state = TeamState()
    state.set_user_language("Sửa lỗi đăng nhập trong dự án giúp mình")
    team = _team(state=state)
    text = team.system_prompt_section()
    assert "Bug fix or small" in text and "the tester verifies it" in text
    assert "Never re-delegate work already done" in text
    assert "account usage limit" in text
    assert {"delegate_task", "ask_user", "submit_plan"} <= {spec.name for spec in team.tool_specs()}


def test_sub_lead_ignores_small_talk_fast_path():
    state = TeamState()
    state.set_user_language("hi")
    team = _team(state=state, delegated=True)
    assert team.system_prompt_section() != LEAD_SMALL_TALK
    assert [spec.name for spec in team.tool_specs()] == ["delegate_task"]


def test_account_switch_during_member_run_is_noted_for_the_lead():
    global_state = {}
    state = get_team_state(global_state)

    def runner(member, inputs, lead):
        global_state["_account_fallback"] = FallbackState(exhausted={"claude-1"}, replacement={"claude-1": "codex-1"})
        return [Message(role=MessageRole.ASSISTANT, content="fixed")]

    team = _team(runner, state=state)
    result = team.execute("delegate_task", {"member": "be", "task": "Fix login"})
    assert result["report"] == "fixed"
    assert "usage limit" in result["account_note"] and "codex-1" in result["account_note"]
    # A switch that happened before this delegation is not reported again.
    again = team.execute("delegate_task", {"member": "qa", "task": "Test login"})
    assert "account_note" not in again


def test_no_account_note_without_fallback_state():
    result = _team(state=TeamState()).execute("delegate_task", {"member": "be", "task": "x"})
    assert "account_note" not in result


def test_old_turns_are_clipped_harder_than_recent_ones():
    long_answer = "A" * 3_000 + "TAIL"
    turns = [make_turn(f"question {i}", long_answer) for i in range(4)]
    text = build_transcript(turns)
    blocks = text.split("--- Turn ")[1:]
    assert len(blocks) == 4
    # Turns 1-2 are background: their answers are clipped to the old-turn budget.
    for block in blocks[:2]:
        answer = block.split("You answered: ", 1)[1]
        assert len(answer.strip()) <= MAX_OLD_ANSWER_CHARS and "omitted" in answer
    # The last two turns keep their full answers.
    for block in blocks[2:]:
        assert long_answer in block
