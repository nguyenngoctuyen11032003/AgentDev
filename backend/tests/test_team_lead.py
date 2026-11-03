"""Team lead (CTO / PM) orchestration: the lead delegates to member nodes and answers the user."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from agentdev.entity.configs.base import ConfigError
from agentdev.entity.configs.node.team import AgentTeamConfig
from agentdev.entity.messages import Message, MessageRole, ToolCallPayload
from agentdev.runtime.node.agent import ModelResponse, ProviderRegistry
from agentdev.runtime.node.agent.team import (
    DECISION_MARKER,
    TeamDelegation,
    TeamState,
    resolve_members,
    user_exchanges,
)
from agentdev.runtime.node.executor import agent_executor as agent_executor_module
from agentdev.utils.human_prompt import HumanPromptService, PromptResult


# ---------------------------------------------------------------- config

def test_team_config_defaults_and_validation():
    cfg = AgentTeamConfig.from_dict({"enabled": True}, path="team")
    assert cfg.enabled and cfg.members == [] and cfg.plan_approval and cfg.max_delegations == 30
    cfg = AgentTeamConfig.from_dict({"enabled": True, "members": ["be", "be", "qa"], "plan_approval": False}, path="t")
    assert cfg.members == ["be", "qa"] and cfg.plan_approval is False
    with pytest.raises(ConfigError):
        AgentTeamConfig.from_dict({"members": "be"}, path="t")
    with pytest.raises(ConfigError):
        AgentTeamConfig.from_dict({"max_delegations": 0}, path="t")


# ---------------------------------------------------------------- unit

def _node(node_type="agent", description="", role="", wired=False):
    return SimpleNamespace(
        node_type=node_type,
        description=description,
        role=role,
        predecessors=[object()] if wired else [],
        successors=[],
    )


def test_resolve_members_defaults_to_unwired_agents():
    nodes = {
        "cto": _node(),
        "be": _node(description="Backend developer"),
        "qa": _node(role="You are a tester.\nMore text"),
        "writer": _node(wired=True),
        "human": _node(node_type="human"),
    }
    members = resolve_members("cto", [], nodes)
    assert {m.node_id: m.summary for m in members} == {"be": "Backend developer", "qa": "You are a tester."}
    assert [m.node_id for m in resolve_members("cto", ["qa", "missing", "cto"], nodes)] == ["qa"]


def _delegation(runner, **kwargs):
    members = resolve_members("cto", [], {"cto": _node(), "be": _node(description="BE"), "qa": _node(description="QA")})
    opts = dict(max_delegations=3, max_review_rounds=2, plan_approval=True)
    opts.update(kwargs)
    return TeamDelegation(lead_id="cto", members=members, runner=runner, prompt_service=None, state=TeamState(), **opts)


def test_delegate_runs_member_with_brief_and_history():
    calls = []

    def runner(member, inputs, lead):
        calls.append((member, inputs[0].text_content(), lead))
        return [Message(role=MessageRole.ASSISTANT, content=f"{member} done #{len(calls)}")]

    team = _delegation(runner)
    first = team.execute("delegate_task", {"member": "be", "task": "Build login API"})
    assert first["report"] == "be done #1" and first["needs_user_decision"] is False
    second = team.execute("delegate_task", {"member": "be", "task": "Fix review comments"})
    assert second["delegations_left"] == 1
    brief = calls[1][1]
    assert "Fix review comments" in brief and "Build login API" in brief and "be done #1" in brief
    assert DECISION_MARKER in brief  # members are told how to escalate
    assert calls[0][2] == "cto"


def test_delegate_guards():
    team = _delegation(lambda m, i, l: [Message(role=MessageRole.ASSISTANT, content="ok")], max_delegations=1)
    with pytest.raises(ValueError, match="not on your team"):
        team.execute("delegate_task", {"member": "ghost", "task": "x"})
    team.execute("delegate_task", {"member": "qa", "task": "test"})
    with pytest.raises(ValueError, match="limit"):
        team.execute("delegate_task", {"member": "qa", "task": "again"})


def test_decision_marker_is_flagged():
    team = _delegation(lambda m, i, l: [Message(role=MessageRole.ASSISTANT, content=f"{DECISION_MARKER} Postgres or MySQL?")])
    assert team.execute("delegate_task", {"member": "be", "task": "pick db"})["needs_user_decision"] is True


def test_ask_user_answers_are_kept_for_the_next_turn():
    prompt = SimpleNamespace(request=lambda *a, **k: PromptResult(text="ok, but use Vue"))
    members = resolve_members("cto", [], {"cto": _node(), "be": _node(description="BE")})
    state = TeamState()
    team = TeamDelegation(lead_id="cto", members=members, runner=lambda *a: [], prompt_service=prompt, state=state,
                          max_delegations=3, max_review_rounds=2, plan_approval=True)
    assert team.execute("ask_user", {"question": "Plan: React SPA. Approve?"}) == {"answer": "ok, but use Vue"}
    assert user_exchanges({"_team_state": state}) == [{"question": "Plan: React SPA. Approve?", "answer": "ok, but use Vue"}]
    assert user_exchanges({}) == []


def test_lead_prompt_lists_team_and_rules():
    text = _delegation(lambda *a: []).system_prompt_section()
    assert "`be`: BE" in text and "`qa`: QA" in text
    assert "approval" in text and "answer it yourself" in text
    assert "act on it immediately" in text  # a follow-up "ok" proceeds instead of re-planning
    text_off = _delegation(lambda *a: [], plan_approval=False).system_prompt_section()
    assert "without asking for plan approval" in text_off


# ---------------------------------------------------------------- end to end

class ScriptedProvider:
    """Plays a fixed script per node; records what each node was sent."""

    scripts = {}
    seen = {}

    def __init__(self, config):
        self.config = config

    def create_client(self):
        return None

    def call_model(self, client, conversation, timeline, tool_specs=None, **kwargs):
        node_id = self.config.node_id
        self.seen.setdefault(node_id, []).append(
            {"conversation": [m.text_content() for m in conversation], "tools": [s.name for s in tool_specs or []]}
        )
        step = self.scripts[node_id].pop(0)
        if isinstance(step, tuple):
            name, args = step
            call = ToolCallPayload(id=f"call-{len(self.seen[node_id])}", function_name=name, arguments=json.dumps(args))
            return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content="", tool_calls=[call]))
        return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=step))

    def extract_token_usage(self, response):
        return None


@pytest.fixture()
def team_workflow(tmp_path, monkeypatch):
    def agent(node_id, role, team=None):
        config = {"connection": "fake", "provider": "fake", "name": "fake-model", "role": role}
        if team:
            config["team"] = team
        return {"id": node_id, "type": "agent", "description": role, "config": config}

    definition = {
        "version": "0.4.0",
        "graph": {
            "id": "team_test",
            "start": ["CTO"],
            "end": ["CTO"],
            "nodes": [
                agent("CTO", "You are the CTO.", team={"enabled": True}),
                agent("Backend Dev", "Backend developer"),
                agent("Tester", "QA tester"),
            ],
            "edges": [],
        },
    }
    path = tmp_path / "team.yaml"
    path.write_text(yaml.safe_dump(definition), encoding="utf-8")

    creds = SimpleNamespace(provider="fake", vendor="fake", token="", base_url="")
    monkeypatch.setattr(agent_executor_module, "resolve_connection", lambda _id: creds)
    monkeypatch.setattr(ProviderRegistry, "get_provider", lambda _name: ScriptedProvider)
    questions = []

    def fake_request(self, node_id, task_description, *, inputs=None, metadata=None):
        questions.append((node_id, task_description))
        return PromptResult(text="Duyệt, làm đi")

    monkeypatch.setattr(HumanPromptService, "request", fake_request)
    ScriptedProvider.seen = {}
    return path, questions


def test_lead_delegates_asks_user_and_answers(team_workflow):
    from agentdev.runtime.sdk import run_workflow

    path, questions = team_workflow
    ScriptedProvider.scripts = {
        "CTO": [
            ("ask_user", {"question": "Kế hoạch: FastAPI + Postgres. Duyệt không?"}),
            ("delegate_task", {"member": "Backend Dev", "task": "Implement /login"}),
            ("delegate_task", {"member": "Tester", "task": "Test /login. Dev report: <see>"}),
            "Đã xong: API /login đã viết và test đạt.",
        ],
        "Backend Dev": ["Implemented /login in app/auth.py"],
        "Tester": ["All 4 login tests pass"],
    }

    result = run_workflow(path, task_prompt="Làm API đăng nhập")

    assert result.final_message.text_content() == "Đã xong: API /login đã viết và test đạt."
    assert questions == [("CTO", "Kế hoạch: FastAPI + Postgres. Duyệt không?")]

    cto_calls = ScriptedProvider.seen["CTO"]
    assert {"delegate_task", "ask_user"} <= set(cto_calls[0]["tools"])
    system_prompt = cto_calls[0]["conversation"][0]
    assert "`Backend Dev`" in system_prompt and "`Tester`" in system_prompt
    # The lead talks to the user, so it gets the answer rules (language of the user's message, ...).
    assert "# How you answer" in system_prompt and "NEWEST message" in system_prompt
    # The lead sees the user's answer and each member's report.
    assert any("Duyệt, làm đi" in text for text in cto_calls[1]["conversation"])
    assert any("All 4 login tests pass" in text for text in cto_calls[3]["conversation"])

    # Members only get their brief, never the lead's tools.
    dev_call = ScriptedProvider.seen["Backend Dev"][0]
    assert "delegate_task" not in dev_call["tools"]
    assert any("Implement /login" in text for text in dev_call["conversation"])
    # Members report to the lead: no user-facing answer rules, the member protocol instead.
    assert not any("# How you answer" in text for text in dev_call["conversation"])
    assert any("# You are a member of a team" in text for text in dev_call["conversation"])
    assert ScriptedProvider.scripts["CTO"] == []


def test_member_events_are_tagged_for_the_ui(team_workflow):
    from agentdev.runtime.sdk import run_workflow

    path, _ = team_workflow
    ScriptedProvider.scripts = {
        "CTO": [("delegate_task", {"member": "Tester", "task": "Smoke test"}), "Smoke test passed."],
        "Backend Dev": [],
        "Tester": ["ok"],
    }
    result = run_workflow(path, task_prompt="smoke")
    log_dir = Path(result.meta_info.output_dir)
    events = []
    for log_file in log_dir.rglob("*.json"):
        try:
            payload = json.loads(log_file.read_text(encoding="utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("logs"), list):
            events.extend(payload["logs"])
    tester_events = [e for e in events if e.get("node_id") == "Tester" and e.get("event_type") in ("NODE_START", "NODE_END")]
    assert tester_events, f"no Tester events in {log_dir}"
    assert all(e["details"].get("delegated_by") == "CTO" for e in tester_events)
    assert result.final_message.text_content() == "Smoke test passed."


def test_roster_shows_sub_teams_so_named_work_can_be_routed():
    pm = _node(description="Project manager")
    pm.config = SimpleNamespace(team=SimpleNamespace(enabled=True, members=["QA Tester", "Ghost"]))
    nodes = {"CTO": _node(), "Project Manager": pm, "QA Tester": _node(wired=True, description="QA")}
    members = resolve_members("CTO", ["Project Manager"], nodes)
    assert members[0].manages == ("QA Tester",)
    team = TeamDelegation(lead_id="CTO", members=members, runner=lambda *a: [], prompt_service=None,
                          state=TeamState(), max_delegations=3, max_review_rounds=2, plan_approval=True)
    text = team.system_prompt_section()
    assert "`Project Manager`: Project manager — leads: QA Tester" in text
    assert "Never do a named person's work yourself" in text
