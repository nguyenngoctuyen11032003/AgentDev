"""Token/speed efficiency of team delegation: run-wide budget, reserve-after-claim, lean briefs, language."""

import threading
import time
from types import SimpleNamespace

import pytest

from agentdev.api.services.conversation_turns import attachment_refs, build_transcript, make_turn
from agentdev.entity.messages import Message, MessageRole
from agentdev.runtime.node.agent.team import (
    DELEGATE_PARALLEL_TOOL,
    MAX_MEMBER_RESULT_CHARS,
    SUB_LEAD_PROTOCOL,
    TeamDelegation,
    TeamState,
    detect_language,
    get_team_state,
    latest_user_message,
    resolve_members,
)
from agentdev.utils.exceptions import WorkflowCancelledError


def _node(description=""):
    return SimpleNamespace(node_type="agent", description=description, role="", predecessors=[], successors=[])


def _team(runner, state=None, **kwargs):
    nodes = {"cto": _node(), "be": _node("BE"), "fe": _node("FE"), "qa": _node("QA")}
    opts = dict(max_delegations=10, max_review_rounds=2, plan_approval=False, max_parallel=3)
    opts.update(kwargs)
    return TeamDelegation(lead_id="cto", members=resolve_members("cto", [], nodes), runner=runner,
                          prompt_service=None, state=state or TeamState(), **opts)


def _ok(member, inputs, lead):
    return [Message(role=MessageRole.ASSISTANT, content=f"{member} done")]


# ---------------------------------------------------------------- 1. report size

def test_long_report_is_clipped_for_the_lead_but_kept_in_full():
    long_report = "START " + "x" * 20_000 + " END"
    team = _team(lambda *a: [Message(role=MessageRole.ASSISTANT, content=long_report)])
    result = team.execute("delegate_task", {"member": "be", "task": "Build"})
    assert len(result["report"]) < MAX_MEMBER_RESULT_CHARS + 200 and "START" in result["report"]
    assert "ask be" in result["note"]
    assert team.state.log[-1]["report"] == long_report


# ---------------------------------------------------------------- 2. run-wide budget

def test_member_runs_are_shared_by_all_leads_of_a_run():
    state = TeamState(max_member_runs=3)
    lead = _team(_ok, state=state)
    sub = _team(_ok, state=state)  # e.g. a sub-lead sharing the run's team state
    lead.execute("delegate_task", {"member": "be", "task": "a"})
    sub.execute(DELEGATE_PARALLEL_TOOL, {"tasks": [{"member": "fe", "task": "b"}, {"member": "qa", "task": "c"}]})
    assert state.member_runs == 3 and state.member_runs_left() == 0
    with pytest.raises(ValueError, match="Team budget exhausted.*3 of its 3"):
        lead.execute("delegate_task", {"member": "be", "task": "d"})
    assert lead.delegations == 1  # the refused delegation was not counted


def test_member_run_budget_is_configurable():
    assert get_team_state({"team_max_member_runs": 7}).max_member_runs == 7
    assert get_team_state({}).max_member_runs == 40


# ---------------------------------------------------------------- 3. reserve after claim, refund, log

def test_busy_member_does_not_use_up_a_delegation():
    team = _team(_ok, max_delegations=1)
    team.state.running.add("be")
    with pytest.raises(ValueError, match="already working"):
        team.execute("delegate_task", {"member": "be", "task": "x"})
    assert team.delegations == 0 and team.state.member_runs == 0


def test_crash_is_refunded_and_logged():
    def runner(member, inputs, lead):
        raise RuntimeError("tool exploded")

    team = _team(runner, max_delegations=1)
    with pytest.raises(RuntimeError):
        team.execute("delegate_task", {"member": "be", "task": "Fix login"})
    assert team.delegations == 0 and team.state.member_runs == 0 and team.state.running == set()
    assert team.state.log[-1]["member"] == "be" and "tool exploded" in team.state.log[-1]["report"]
    assert "be" not in team.state.history


def test_model_error_still_counts():
    def runner(member, inputs, lead):
        return [Message(role=MessageRole.ASSISTANT, content="MODEL ERROR: x", metadata={"model_error": True})]

    team = _team(runner)
    team.execute("delegate_task", {"member": "be", "task": "x"})
    assert team.delegations == 1


# ---------------------------------------------------------------- 4/5. lean briefs

def test_brief_has_one_clipped_previous_report_and_a_digest_of_others():
    briefs = []

    def runner(member, inputs, lead):
        briefs.append(inputs[0].text_content())
        return [Message(role=MessageRole.ASSISTANT, content=f"report {len(briefs)} " + "r" * 5000)]

    state = get_team_state({"conversation_turns": [
        {"user": "u", "answer": "a", "team": [{"member": "be", "task": "Old task one", "report": "old report"}]}
    ]})
    team = _team(runner, state=state)
    for task in ("Task A", "Task B", "Task C"):
        team.execute("delegate_task", {"member": "be", "task": task})
    brief = briefs[-1]
    assert "report 2" in brief and "report 1" not in brief and "old report" not in brief
    assert brief.count("## Your report") == 1
    assert "Old task one" in brief and "Task A" in brief  # titles only
    assert len(brief) < 3_000


def test_sub_lead_brief_does_not_repeat_the_sub_lead_protocol():
    briefs = []
    pm = _node("Project manager")
    pm.config = SimpleNamespace(team=SimpleNamespace(enabled=True, members=["dev"]))
    nodes = {"cto": _node(), "pm": pm, "dev": _node("Dev")}
    team = TeamDelegation(lead_id="cto", members=resolve_members("cto", ["pm"], nodes),
                          runner=lambda m, i, l: briefs.append(i[0].text_content()) or _ok(m, i, l),
                          prompt_service=None, state=TeamState(), max_delegations=3, max_review_rounds=2,
                          plan_approval=False)
    team.execute("delegate_task", {"member": "pm", "task": "Ship login"})
    assert SUB_LEAD_PROTOCOL.splitlines()[0] not in briefs[0] and "Ship login" in briefs[0]


# ---------------------------------------------------------------- 6. parallel cancel

def test_parallel_cancel_stops_without_waiting_for_queued_members():
    cancel = threading.Event()
    started = []

    def runner(member, inputs, lead):
        started.append(member)
        cancel.set()
        time.sleep(1.0)
        return _ok(member, inputs, lead)

    team = _team(runner, max_parallel=2, cancel_event=cancel)
    t0 = time.monotonic()
    with pytest.raises(WorkflowCancelledError):
        team.execute(DELEGATE_PARALLEL_TOOL, {"tasks": [{"member": m, "task": "t"} for m in ("be", "fe", "qa")]})
    assert time.monotonic() - t0 < 0.8
    assert "qa" not in started
    assert "qa" not in team.state.running and team.delegations <= 2


# ---------------------------------------------------------------- 7. language

@pytest.mark.parametrize("text,expected", [
    ("toi muon lam web ban hang", "Vietnamese"),
    ("Hi Tuyền, fix the login bug", "English"),
    ("Làm API đăng nhập", "Vietnamese"),
    ("ログインのバグを直してください", "Japanese"),
    ("로그인 버그를 고쳐 주세요", "Korean"),
    ("做一个登录接口", "Chinese"),
    ("Build a login API", "English"),
    ("ok", ""),
    ("123", ""),
])
def test_detect_language(text, expected):
    assert detect_language(text) == expected


def test_short_follow_up_keeps_previous_language():
    follow_up = (
        "[Earlier]\nUser: toi muon lam web ban hang\nYou answered: Here is the plan in English words only.\n\n"
        "[The user's NEW message: answer this one.]\nok"
    )
    assert detect_language(latest_user_message(follow_up)) == "Vietnamese"
    state = TeamState(user_language="Japanese")
    state.set_user_language("ok")
    assert state.user_language == "Japanese"


def test_lead_prompt_states_language_and_request_classes():
    state = TeamState(user_language="Vietnamese")
    text = _team(_ok, state=state, plan_approval=True).system_prompt_section()
    assert "reply in Vietnamese" in text
    assert "Bug fix or small" in text and "làm luôn" in text and "member runs" in text


# ---------------------------------------------------------------- 10. attachments as references

def test_earlier_attachments_keep_paths_not_contents():
    refs = attachment_refs(["a1", "a2"], {"a1": {"ref": {"name": "spec.pdf", "local_path": "/w/att/a1/spec.pdf"}}})
    turn = make_turn("xem file", "ok", refs)
    text = build_transcript([turn])
    assert "spec.pdf (path: /w/att/a1/spec.pdf)" in text and "a2" in text and "re-read" in text


# ---------------------------------------------------------------- 7. briefs that prevent re-exploring

def test_briefs_and_protocols_steer_towards_context_and_away_from_repeats():
    briefs = []
    team = _team(lambda m, i, l: briefs.append(i[0].text_content()) or _ok(m, i, l))
    team.execute("delegate_task", {"member": "be", "task": "Build"})
    assert "Start from the files, decisions and results the brief gives you" in briefs[0]
    lead = team.system_prompt_section()
    assert "files or paths to start from" in lead and "same task again" in lead
