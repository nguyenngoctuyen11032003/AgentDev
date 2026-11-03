"""Plan-approval gate: a lead with ``plan_approval`` submits a plan and stops until the user approves."""

import asyncio
import json
from types import SimpleNamespace

import pytest
import yaml

from agentdev.api.services.conversation_turns import PLAN_REPLY_NOTE, compose_follow_up_prompt, make_turn
from agentdev.api.services.session_history import SessionHistoryStore
from agentdev.api.services.session_store import SessionStatus, WorkflowSessionStore
from agentdev.api.services.workflow_run_service import WorkflowRunService
from agentdev.entity.messages import Message, MessageRole, ToolCallPayload
from agentdev.runtime.node.agent import ModelResponse, ProviderRegistry
from agentdev.runtime.node.agent.team import (
    NEW_MESSAGE_MARKER,
    PLAN_GATE_REFUSAL,
    SUBMIT_PLAN_TOOL,
    TeamDelegation,
    TeamState,
    latest_user_message,
)
from agentdev.runtime.node.executor import agent_executor as agent_executor_module

PLAN = "## Kế hoạch\n- Backend Dev: API\n- Tester: kiểm thử"


class ScriptedProvider:
    """Plays a script per node; a step is text, a (name, args) call, or a list of calls in one reply."""

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
        if isinstance(step, (tuple, list)):
            calls = [step] if isinstance(step, tuple) else step
            payloads = [
                ToolCallPayload(id=f"call-{len(self.seen[node_id])}-{i}", function_name=name, arguments=json.dumps(args))
                for i, (name, args) in enumerate(calls)
            ]
            return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content="", tool_calls=payloads))
        return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=step))

    def extract_token_usage(self, response):
        return None


@pytest.fixture()
def lead_workflow(tmp_path, monkeypatch):
    def make(plan_approval=True):
        def agent(node_id, role, team=None):
            config = {"connection": "fake", "provider": "fake", "name": "fake-model", "role": role}
            if team:
                config["team"] = team
            return {"id": node_id, "type": "agent", "description": role, "config": config}

        definition = {
            "version": "0.4.0",
            "graph": {
                "id": "plan_gate",
                "start": ["CTO"],
                "end": ["CTO"],
                "nodes": [
                    agent("CTO", "You are the CTO.", team={"enabled": True, "plan_approval": plan_approval}),
                    agent("Backend Dev", "Backend developer"),
                    agent("Tester", "QA tester"),
                ],
                "edges": [],
            },
        }
        path = tmp_path / f"plan_{plan_approval}.yaml"
        path.write_text(yaml.safe_dump(definition), encoding="utf-8")
        return path

    creds = SimpleNamespace(provider="fake", vendor="fake", token="", base_url="")
    monkeypatch.setattr(agent_executor_module, "resolve_connection", lambda _id: creds)
    monkeypatch.setattr(ProviderRegistry, "get_provider", lambda _name: ScriptedProvider)
    ScriptedProvider.seen = {}
    return make


def _run(path, prompt):
    from agentdev.entity.graph_config import GraphConfig
    from agentdev.runtime.sdk import OUTPUT_ROOT, ensure_schema_registry_populated
    from agentdev.validation.check import load_config
    from agentdev.workflow.graph import GraphExecutor
    from agentdev.workflow.graph_context import GraphContext

    ensure_schema_registry_populated()
    design = load_config(path)
    config = GraphConfig.from_definition(design.graph, name="plan_gate_test", output_root=OUTPUT_ROOT, source_path=str(path), vars=design.vars)
    context = GraphContext(config=config)
    executor = GraphExecutor(context)
    executor._execute(prompt)
    return executor, executor._get_execution_context().global_state


def test_submit_plan_ends_the_turn_and_sets_plan_pending(lead_workflow):
    ScriptedProvider.scripts = {
        "CTO": [(SUBMIT_PLAN_TOOL, {"plan": PLAN, "summary": "Web bán hàng"}), "never reached"],
        "Backend Dev": [],
        "Tester": [],
    }
    executor, state = _run(lead_workflow(), "Làm web bán hàng mới")

    assert executor.get_final_output_message().text_content() == PLAN
    assert state["plan_pending"] == {"node": "CTO", "summary": "Web bán hàng", "plan": PLAN}
    assert len(ScriptedProvider.seen["CTO"]) == 1  # no model call after submit_plan
    assert SUBMIT_PLAN_TOOL in ScriptedProvider.seen["CTO"][0]["tools"]
    assert "submit_plan" in ScriptedProvider.seen["CTO"][0]["conversation"][0]  # protocol text
    assert ScriptedProvider.scripts["CTO"] == ["never reached"]


def test_delegation_in_the_same_reply_as_the_plan_is_refused(lead_workflow):
    ScriptedProvider.scripts = {
        "CTO": [[
            ("delegate_task", {"member": "Backend Dev", "task": "early"}),
            (SUBMIT_PLAN_TOOL, {"plan": PLAN, "summary": "s"}),
            ("delegate_task", {"member": "Tester", "task": "later"}),
        ]],
        "Backend Dev": ["should not run"],
        "Tester": ["should not run"],
    }
    executor, state = _run(lead_workflow(), "Dự án mới")
    assert executor.get_final_output_message().text_content() == PLAN
    assert "Backend Dev" not in ScriptedProvider.seen and "Tester" not in ScriptedProvider.seen
    assert state["plan_pending"]["plan"] == PLAN
    assert not state["_team_state"].log


def test_team_refuses_delegation_after_submit_plan():
    members = [SimpleNamespace(node_id="be", summary="BE", skills=(), manages=())]
    team = TeamDelegation(lead_id="cto", members=members, runner=lambda *a: [], prompt_service=None, state=TeamState(),
                          max_delegations=3, max_review_rounds=2, plan_approval=True)
    assert team.execute(SUBMIT_PLAN_TOOL, {"plan": PLAN, "summary": ""})["status"] == "submitted"
    assert team.plan["summary"] == "Kế hoạch"  # no summary given: the plan's first line
    with pytest.raises(ValueError) as refused:
        team.execute("delegate_task", {"member": "be", "task": "x"})
    assert str(refused.value) == PLAN_GATE_REFUSAL


def test_no_submit_plan_without_plan_approval_or_for_a_sub_lead(lead_workflow):
    members = [SimpleNamespace(node_id="be", summary="BE", skills=(), manages=())]

    def team(**kw):
        opts = dict(lead_id="cto", members=members, runner=lambda *a: [], prompt_service=None, state=TeamState(),
                    max_delegations=3, max_review_rounds=2)
        opts.update(kw)
        return TeamDelegation(**opts)

    assert SUBMIT_PLAN_TOOL not in [s.name for s in team(plan_approval=False).tool_specs()]
    assert SUBMIT_PLAN_TOOL not in [s.name for s in team(plan_approval=True, delegated=True).tool_specs()]
    with pytest.raises(ValueError):
        team(plan_approval=False).execute(SUBMIT_PLAN_TOOL, {"plan": PLAN})

    ScriptedProvider.scripts = {
        "CTO": [("delegate_task", {"member": "Backend Dev", "task": "API"}), "Xong."],
        "Backend Dev": ["done"],
        "Tester": [],
    }
    executor, state = _run(lead_workflow(plan_approval=False), "Làm API")
    assert executor.get_final_output_message().text_content() == "Xong."
    assert SUBMIT_PLAN_TOOL not in ScriptedProvider.seen["CTO"][0]["tools"]
    assert "plan_pending" not in state


def test_follow_up_after_a_plan_tells_the_lead_how_to_treat_the_reply():
    plan_turn = make_turn("Làm web mới", PLAN)
    plan_turn["kind"] = "plan"
    prompt = compose_follow_up_prompt([plan_turn], "ok, duyệt")
    assert "The user replied to your plan: ok, duyệt. If this approves it (e.g. ok, đồng ý, duyệt, làm đi, go ahead), " \
        "execute the plan now without re-asking; if it requests changes, revise and call submit_plan again." in prompt
    assert "You proposed this plan for approval" in prompt
    # The user's own text is still what the language is detected from.
    assert prompt.rfind(NEW_MESSAGE_MARKER) > prompt.find("The user replied to your plan")
    assert latest_user_message(prompt).strip() == "ok, duyệt"

    normal = compose_follow_up_prompt([make_turn("hi", "hello")], "ok")
    assert "replied to your plan" not in normal
    assert PLAN_REPLY_NOTE.split("{")[0] not in normal


def test_session_summary_awaiting_plan_and_has_work(tmp_path):
    store = WorkflowSessionStore(history=SessionHistoryStore(tmp_path))
    session = store.create_session(yaml_file="w.yaml", task_prompt="Làm web", session_id="s1")
    store.update_session_status("s1", SessionStatus.RUNNING)
    assert store.list_summaries()[0]["awaiting_plan"] is False

    store.complete_session("s1", {})
    plan_turn = make_turn("Làm web", PLAN)
    plan_turn["kind"] = "plan"
    store.add_turn("s1", plan_turn)
    summary = store.list_summaries()[0]
    assert summary["awaiting_plan"] is True and summary["has_work"] is False
    assert store.history.get_meta("s1")["awaiting_plan"] is True  # persisted for the sidebar after a restart

    # The next turn starts: no longer awaiting.
    store.create_session(yaml_file="w.yaml", task_prompt="ok", session_id="s1")
    store.update_session_status("s1", SessionStatus.RUNNING)
    assert store.list_summaries()[0]["awaiting_plan"] is False
    store.complete_session("s1", {})
    store.add_turn("s1", make_turn("ok", "Xong", exchanges=[{"kind": "delegation", "member": "be", "task": "t", "report": "r"}]))
    summary = store.list_summaries()[0]
    assert summary["awaiting_plan"] is False and summary["has_work"] is True

    # Changed files count as work too, also after a restore from disk.
    store.create_session(yaml_file="w.yaml", task_prompt="x", session_id="s2")
    assert {s["session_id"]: s["has_work"] for s in store.list_summaries()}["s2"] is False
    message = {"type": "artifact_created", "data": {"events": [{"file_name": "a.py"}]}}
    store.record_message("s2", message, json.dumps(message))
    assert {s["session_id"]: s["has_work"] for s in store.list_summaries()}["s2"] is True
    restored = WorkflowSessionStore(history=SessionHistoryStore(tmp_path))
    assert restored.restore_session("s2").files_changed is True

    # Sessions saved before these fields existed report False.
    (tmp_path / "old").mkdir()
    (tmp_path / "old" / "meta.json").write_text(json.dumps({"session_id": "old", "updated_at": 0}), encoding="utf-8")
    old = {s["session_id"]: s for s in restored.list_summaries()}["old"]
    assert old["awaiting_plan"] is False and old["has_work"] is False


class _FakeWS:
    def __init__(self):
        self.sent = []

    async def send_message(self, session_id, message):
        self.sent.append(message)


def test_run_service_emits_plan_proposed_and_saves_a_plan_turn(tmp_path):
    store = WorkflowSessionStore()
    session = store.create_session(yaml_file="w.yaml", task_prompt="Làm web", session_id="s1")
    plan = {"node": "CTO", "summary": "Web", "plan": PLAN}
    context = SimpleNamespace(global_state={"plan_pending": plan})
    executor = SimpleNamespace(
        _get_execution_context=lambda: context,
        get_final_output=lambda: PLAN,
    )
    service = WorkflowRunService(store, SimpleNamespace(cleanup_session=lambda _id: None), SimpleNamespace())
    service._remember_turn("s1", "Làm web", [], executor)
    assert session.turns[-1]["kind"] == "plan" and session.turns[-1]["answer"] == PLAN
    assert service._pending_plan(executor) == plan

    service._remember_turn("s1", "hi", [], SimpleNamespace(_get_execution_context=lambda: SimpleNamespace(global_state={}),
                                                           get_final_output=lambda: "hello"))
    assert "kind" not in session.turns[-1]


def test_full_run_sends_plan_proposed_before_completion(tmp_path, monkeypatch):
    from agentdev.api.services import workflow_run_service as module

    store = WorkflowSessionStore()
    session = store.create_session(yaml_file="w.yaml", task_prompt="Làm web", session_id="s1")
    plan = {"node": "CTO", "summary": "Web", "plan": PLAN}

    class FakeExecutor:
        def __init__(self, *args, **kwargs):
            self.token_tracker = SimpleNamespace(get_token_usage=lambda: {})
            self.attachment_store = None

        async def execute_graph_async(self, task_input):
            return None

        def _get_execution_context(self):
            return SimpleNamespace(global_state={"plan_pending": plan})

        def get_results(self):
            return {}

        def get_final_output(self):
            return PLAN

    monkeypatch.setattr(module, "load_config", lambda path: SimpleNamespace(graph={}, vars={}))
    monkeypatch.setattr(module.GraphConfig, "from_definition", staticmethod(lambda *a, **k: SimpleNamespace(log_level=None, definition=SimpleNamespace(start_nodes=["CTO"]), name="x")))
    monkeypatch.setattr(module, "GraphContext", lambda config: SimpleNamespace(config=config, name="x", final_message=lambda: ""))
    monkeypatch.setattr(module, "WebSocketGraphExecutor", FakeExecutor)
    monkeypatch.setattr(module, "opened_project_folder", lambda s: None)
    service = WorkflowRunService(store, SimpleNamespace(cleanup_session=lambda _id: None), SimpleNamespace())
    monkeypatch.setattr(service, "_build_initial_task_input", lambda *a, **k: "Làm web")
    ws = _FakeWS()
    asyncio.run(service._execute_workflow_async("s1", tmp_path / "w.yaml", "Làm web", ws, [], None))

    types = [m["type"] for m in ws.sent]
    assert types == ["plan_proposed", "workflow_completed"]
    assert ws.sent[0]["data"] == plan
    assert session.turns[-1]["kind"] == "plan"
    assert store.list_summaries()[0]["awaiting_plan"] is True
