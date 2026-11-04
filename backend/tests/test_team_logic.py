"""Team logic: plan gate on approvals and questions, repeat guard, busy-member queueing, quota failover,
sub-leads that hand nothing out, approved-plan owners."""

import threading
import time
from types import SimpleNamespace

import pytest

from agentdev.api.services.conversation_turns import compose_follow_up_prompt, make_turn
from agentdev.entity.messages import Message, MessageRole
from agentdev.runtime.node.agent.team import (
    DELEGATE_PARALLEL_TOOL,
    LEAD_SMALL_TALK,
    PLAN_RULE_APPROVED,
    PLAN_RULE_QUESTION,
    SUBMIT_PLAN_TOOL,
    TeamDelegation,
    TeamMember,
    TeamState,
    get_team_state,
    is_plan_approval,
    is_simple_question,
    latest_user_message,
    newest_user_message,
)

PLAN = "## Kế hoạch\n- be: API đăng nhập\n- qa: kiểm thử"


def _ok(member, inputs, lead):
    return [Message(role=MessageRole.ASSISTANT, content=f"{member} done")]


def _team(runner=_ok, state=None, members=None, **kwargs):
    members = members or [
        TeamMember("be", "be", "Backend", skills=("api", "testing")),
        TeamMember("fe", "fe", "Frontend", skills=("ui",)),
        TeamMember("qa", "qa", "QA", skills=("testing",)),
    ]
    opts = dict(max_delegations=10, max_review_rounds=2, plan_approval=True, max_parallel=3)
    opts.update(kwargs)
    return TeamDelegation(lead_id="cto", members=members, runner=runner, prompt_service=None,
                          state=state or TeamState(), **opts)


def _state(message, turns=None):
    global_state = {"conversation_turns": turns} if turns is not None else {}
    state = get_team_state(global_state)
    prompt = compose_follow_up_prompt(turns or [], message)
    state.set_user_language(latest_user_message(prompt), newest=newest_user_message(prompt))
    return state


def _plan_turns():
    return [{"user": "Làm trang đăng nhập", "answer": PLAN, "attachments": [], "kind": "plan"}]


def _tools(team):
    return {spec.name for spec in team.tool_specs()}


# ---------------------------------------------------------------- classifiers

@pytest.mark.parametrize("text", ["ok", "OK!", "duyệt", "đồng ý nhé", "ok làm đi", "go ahead 👍", "làm luôn anh",
                                  "yes, do it", "approved", "Duyệt kế hoạch này, triển khai đi"])
def test_plain_approvals(text):
    assert is_plan_approval(text)


@pytest.mark.parametrize("text", ["", "ok nhưng dùng Vue", "ok but use Postgres", "thêm trang admin nữa",
                                  "đổi stack sang Django", "anh ơi cho hỏi chi phí", "nhé"])
def test_changes_and_other_replies_are_not_plain_approvals(text):
    assert not is_plan_approval(text)


@pytest.mark.parametrize("text", ["React hay Vue tốt hơn?", "How does the login flow work?", "Dự án này có rủi ro gì?",
                                  "what is SSR?"])
def test_plain_questions(text):
    assert is_simple_question(text)


@pytest.mark.parametrize("text", ["Can you build an online shop?", "Làm web bán hàng được không?",
                                  "Thêm trang admin", "Build a shop", "Xây dựng hệ thống quản trị giúp mình nhé?",
                                  "Bạn có thể giúp mình một trang admin không?", "I want a blog, possible?"])
def test_requests_for_work_are_not_plain_questions(text):
    assert not is_simple_question(text)


# ---------------------------------------------------------------- plan gate

def test_approval_of_previous_plan_executes_it_without_a_second_plan():
    team = _team(state=_state("ok, duyệt", _plan_turns()))
    assert team.plan_approved and not team.plan_gate_enabled
    assert SUBMIT_PLAN_TOOL not in _tools(team) and "delegate_task" in _tools(team)
    assert PLAN_RULE_APPROVED in team.system_prompt_section()
    with pytest.raises(ValueError, match="already approved"):
        team.execute(SUBMIT_PLAN_TOOL, {"plan": "again", "summary": "again"})


def test_change_request_to_previous_plan_may_revise_it():
    team = _team(state=_state("ok nhưng dùng Vue thay React", _plan_turns()))
    assert not team.plan_approved and SUBMIT_PLAN_TOOL in _tools(team)


def test_question_without_pending_plan_never_needs_approval():
    team = _team(state=_state("React hay Vue tốt hơn cho dự án này?"))
    assert SUBMIT_PLAN_TOOL not in _tools(team)
    assert PLAN_RULE_QUESTION in team.system_prompt_section()


def test_new_build_request_keeps_the_plan_gate():
    team = _team(state=_state("Làm cho tôi trang quản trị để sửa nội dung"))
    assert SUBMIT_PLAN_TOOL in _tools(team)
    # The real request of session fd44be85 (a new admin area) is planned first.
    real = ("Xem kỹ dự án Này và tôi đang muốn phát triển thêm trang quản trị để có thể cho người dùng đăng nhập "
            "vào và chỉnh sửa các thông tin như trang http://localhost:3000/gioi-thieu này")
    assert SUBMIT_PLAN_TOOL in _tools(_team(state=_state(real)))


def test_approval_without_a_pending_plan_is_not_treated_as_plan_approval():
    team = _team(state=_state("ok", [make_turn("hi", "hello")]))
    assert not team.plan_approved and SUBMIT_PLAN_TOOL in _tools(team)


def test_follow_up_greeting_uses_the_newest_message_for_small_talk():
    # "thanks" alone has no clear language: the language falls back to the earlier message, but the
    # small-talk check must still see "thanks", not the earlier request.
    state = _state("thanks", [make_turn("Sửa lỗi đăng nhập giúp mình", "Đã sửa xong.")])
    assert state.user_language == "Vietnamese" and state.user_message == "thanks"
    team = _team(state=state)
    assert team.system_prompt_section() == LEAD_SMALL_TALK and team.tool_specs() == []


def test_plan_owner_note_when_delegating_outside_the_approved_plan():
    team = _team(state=_state("duyệt", _plan_turns()))
    assert team.plan_owners() == ["be", "qa"]
    assert "note" not in team.execute("delegate_task", {"member": "be", "task": "API"})
    off_plan = team.execute("delegate_task", {"member": "fe", "task": "UI"})
    assert "not an owner in the plan" in off_plan["note"] and "be, qa" in off_plan["note"]


def test_sub_lead_of_a_named_owner_is_not_flagged():
    members = [TeamMember("pm", "pm", "PM", manages=("be",)), TeamMember("be", "be", "BE")]
    team = _team(state=_state("ok", _plan_turns()), members=members)
    result = team.execute("delegate_task", {"member": "pm", "task": "Deliver"})
    assert "not an owner" not in result.get("note", "")


# ---------------------------------------------------------------- repeat guard

def test_identical_task_right_after_is_not_run_again():
    calls = []

    def runner(member, inputs, lead):
        calls.append(member)
        return [Message(role=MessageRole.ASSISTANT, content=f"{member} report")]

    team = _team(runner, plan_approval=False)
    team.execute("delegate_task", {"member": "be", "task": "Fix   login"})
    again = team.execute("delegate_task", {"member": "be", "task": "fix login"})
    assert calls == ["be"] and again["repeated"] and again["report"] == "be report"
    assert "Not run again" in again["note"]
    assert team.delegations == 1 and team.state.member_runs == 1


def test_same_task_after_other_work_runs_again():
    calls = []

    def runner(member, inputs, lead):
        calls.append(member)
        return [Message(role=MessageRole.ASSISTANT, content="ok")]

    team = _team(runner, plan_approval=False)
    team.execute("delegate_task", {"member": "qa", "task": "Run tests"})
    team.execute("delegate_task", {"member": "be", "task": "Fix the failing test"})
    team.execute("delegate_task", {"member": "qa", "task": "Run tests"})
    assert calls == ["qa", "be", "qa"]


def test_failed_task_is_retried_not_reused():
    outputs = iter([
        [Message(role=MessageRole.ASSISTANT, content="MODEL ERROR: timeout", metadata={"model_error": True, "error": "timeout"})],
        [Message(role=MessageRole.ASSISTANT, content="done")],
    ])
    team = _team(lambda *a: next(outputs), plan_approval=False)
    assert "error" in team.execute("delegate_task", {"member": "be", "task": "x"})
    assert team.execute("delegate_task", {"member": "be", "task": "x"})["report"] == "done"


def test_parallel_call_reuses_a_just_finished_identical_task():
    calls = []

    def runner(member, inputs, lead):
        calls.append(member)
        return [Message(role=MessageRole.ASSISTANT, content=f"{member} ok")]

    team = _team(runner, plan_approval=False)
    team.execute("delegate_task", {"member": "be", "task": "API"})
    result = team.execute(DELEGATE_PARALLEL_TOOL, {"tasks": [{"member": "be", "task": "API"}, {"member": "fe", "task": "UI"}]})
    assert calls == ["be", "fe"] and result["results"][0]["repeated"]


# ---------------------------------------------------------------- same member twice in one reply

def test_second_task_for_a_busy_member_of_the_same_lead_waits_instead_of_failing():
    started = threading.Event()
    order = []

    def runner(member, inputs, lead):
        task = inputs[0].content.rsplit("\n", 1)[-1]
        order.append(("start", task))
        started.set()
        time.sleep(0.15)
        order.append(("end", task))
        return [Message(role=MessageRole.ASSISTANT, content=f"done {task}")]

    team = _team(runner, plan_approval=False)
    results = {}
    first = threading.Thread(target=lambda: results.update(a=team.execute("delegate_task", {"member": "be", "task": "A"})))
    first.start()
    started.wait(2)
    results["b"] = team.execute("delegate_task", {"member": "be", "task": "B"})
    first.join(2)
    assert results["a"]["report"] == "done A" and results["b"]["report"] == "done B"
    assert order == [("start", "A"), ("end", "A"), ("start", "B"), ("end", "B")]
    assert team.state.running == set()


def test_member_busy_for_another_lead_still_fails_fast():
    team = _team(plan_approval=False)
    team.state.running.add("be")  # e.g. a sub-lead is using it
    with pytest.raises(ValueError, match="already working"):
        team.execute("delegate_task", {"member": "be", "task": "x"})


# ---------------------------------------------------------------- quota failover

def _quota_runner(calls):
    def runner(member, inputs, lead):
        calls.append(member)
        if member == "be":
            return [Message(role=MessageRole.ASSISTANT, content="MODEL ERROR: limit",
                            metadata={"model_error": True, "error": "Claude usage limit reached; resets 5pm"})]
        return [Message(role=MessageRole.ASSISTANT, content=f"{member} ok")]
    return runner


def test_quota_error_marks_member_unavailable_and_names_alternatives():
    calls = []
    team = _team(_quota_runner(calls), plan_approval=False)
    first = team.execute("delegate_task", {"member": "be", "task": "API"})
    assert "out of quota" in first["error"] and "qa" in first["error"]  # qa shares the "testing" skill
    with pytest.raises(ValueError, match="unavailable for the rest of this request"):
        team.execute("delegate_task", {"member": "be", "task": "Other task"})
    assert calls == ["be"] and team.delegations == 1
    assert team.state.log[-1]["report"].startswith("[failed")


def test_other_model_errors_allow_a_retry():
    team = _team(lambda *a: [Message(role=MessageRole.ASSISTANT, content="x", metadata={"model_error": True, "error": "timeout"})],
                 plan_approval=False)
    assert "Retry once" in team.execute("delegate_task", {"member": "be", "task": "API"})["error"]
    assert team.state.unavailable == {}


def test_parallel_call_skips_an_unavailable_member():
    calls = []
    team = _team(_quota_runner(calls), plan_approval=False)
    team.execute("delegate_task", {"member": "be", "task": "API"})
    result = team.execute(DELEGATE_PARALLEL_TOOL, {"tasks": [{"member": "be", "task": "B"}, {"member": "fe", "task": "UI"}]})
    assert result["failed"] == ["be"] and calls == ["be", "fe"]


# ---------------------------------------------------------------- sub-lead that delegated nothing

def test_sub_lead_that_handed_nothing_out_is_flagged_and_rerunnable():
    members = [TeamMember("pm", "pm", "PM", manages=("fe", "qa")), TeamMember("fe", "fe", "FE")]
    calls = []

    def runner(member, inputs, lead):
        calls.append(member)
        return [Message(role=MessageRole.ASSISTANT, content="Could not delegate: No such tool available")]

    team = _team(runner, members=members, plan_approval=False)
    result = team.execute("delegate_task", {"member": "pm", "task": "Build the page"})
    assert "handed none of this to its team" in result["note"] and "brief fe directly" in result["note"]
    team.execute("delegate_task", {"member": "pm", "task": "Build the page"})
    assert calls == ["pm", "pm"]  # not reused: the second try really runs


def test_sub_lead_that_delegated_is_not_flagged():
    state = TeamState()
    members = [TeamMember("pm", "pm", "PM", manages=("fe",))]

    def runner(member, inputs, lead):
        state.add_report("fe", "page", "fe done", lead="pm")  # the sub-lead's own delegation
        return [Message(role=MessageRole.ASSISTANT, content="fe built it")]

    team = _team(runner, state=state, members=members, plan_approval=False)
    assert "note" not in team.execute("delegate_task", {"member": "pm", "task": "Build"})


def test_pending_plan_is_seeded_only_from_a_plan_turn():
    assert get_team_state({"conversation_turns": _plan_turns()}).pending_plan == PLAN
    assert get_team_state({"conversation_turns": [make_turn("hi", "hello")]}).pending_plan == ""
