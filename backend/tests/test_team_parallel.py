"""Parallel delegation: a lead hands independent tasks to several members at once."""

import json
import threading
import time
from types import SimpleNamespace

import pytest
import yaml

from agentdev.entity.configs.base import ConfigError
from agentdev.entity.configs.node.team import AgentTeamConfig
from agentdev.entity.messages import Message, MessageRole, ToolCallPayload
from agentdev.runtime.node.agent import ModelResponse, ProviderRegistry
from agentdev.runtime.node.agent.team import (
    DELEGATE_PARALLEL_TOOL,
    TeamDelegation,
    TeamState,
    resolve_members,
)
from agentdev.runtime.node.executor import agent_executor as agent_executor_module
from agentdev.utils.exceptions import WorkflowCancelledError
from agentdev.utils.human_prompt import HumanPromptService, PromptResult
from agentdev.utils.logger import WorkflowLogger
from agentdev.utils.token_tracker import TokenTracker, TokenUsage


def _node(description=""):
    return SimpleNamespace(node_type="agent", description=description, role="", predecessors=[], successors=[])


def _team(runner, **kwargs):
    nodes = {"cto": _node(), "be": _node("BE"), "fe": _node("FE"), "qa": _node("QA")}
    members = resolve_members("cto", [], nodes)
    opts = dict(max_delegations=10, max_review_rounds=2, plan_approval=False, max_parallel=3)
    opts.update(kwargs)
    return TeamDelegation(lead_id="cto", members=members, runner=runner, prompt_service=None, state=TeamState(), **opts)


class OverlapRunner:
    """Sleeps per call and records how many members ran at the same time."""

    def __init__(self, delay=0.2, fail=()):
        self.delay = delay
        self.fail = set(fail)
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.calls = []
        self.team = None
        self.depths = []

    def __call__(self, member, inputs, lead):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            self.calls.append(member)
            if self.team is not None:
                self.depths.append(self.team.state.depth)
        try:
            time.sleep(self.delay)
            if member in self.fail:
                raise RuntimeError(f"{member} crashed")
            return [Message(role=MessageRole.ASSISTANT, content=f"{member} done")]
        finally:
            with self.lock:
                self.active -= 1


def _tasks(*members):
    return {"tasks": [{"member": m, "task": f"task for {m}"} for m in members]}


# ---------------------------------------------------------------- config / prompt

def test_max_parallel_config():
    assert AgentTeamConfig.from_dict({"enabled": True}, path="t").max_parallel == 3
    assert AgentTeamConfig.from_dict({"max_parallel": 1}, path="t").max_parallel == 1
    for bad in (0, -2, "3", True):
        with pytest.raises(ConfigError):
            AgentTeamConfig.from_dict({"max_parallel": bad}, path="t")
    assert "max_parallel" in AgentTeamConfig.field_specs()


def test_parallel_tool_and_protocol_only_when_enabled():
    team = _team(lambda *a: [])
    names = [s.name for s in team.tool_specs()]
    assert names == ["delegate_task", DELEGATE_PARALLEL_TOOL, "ask_user"]
    schema = team.tool_specs()[1].parameters["properties"]["tasks"]
    assert schema["minItems"] == 2 and schema["items"]["properties"]["member"]["enum"] == ["be", "fe", "qa"]
    assert "delegate_parallel" in team.system_prompt_section() and "INDEPENDENT" in team.system_prompt_section()

    serial = _team(lambda *a: [], max_parallel=1)
    assert DELEGATE_PARALLEL_TOOL not in [s.name for s in serial.tool_specs()]
    assert "delegate_parallel" not in serial.system_prompt_section()
    with pytest.raises(ValueError, match="disabled"):
        serial.execute(DELEGATE_PARALLEL_TOOL, _tasks("be", "fe"))


# ---------------------------------------------------------------- unit

def test_members_run_concurrently_and_reports_keep_task_order():
    runner = OverlapRunner(delay=0.3)
    team = _team(runner)
    runner.team = team
    started = time.monotonic()
    result = team.execute(DELEGATE_PARALLEL_TOOL, _tasks("qa", "be", "fe"))
    elapsed = time.monotonic() - started

    assert runner.max_active == 3
    assert elapsed < 0.8  # three 0.3 s tasks, not 0.9 s in sequence
    assert [r["member"] for r in result["results"]] == ["qa", "be", "fe"]
    assert [r["report"] for r in result["results"]] == ["qa done", "be done", "fe done"]
    assert result["failed"] == [] and result["delegations_left"] == 7
    # Siblings do not add to each other's nesting depth.
    assert runner.depths == [1, 1, 1]
    assert team.state.depth == 0 and team.state.running == set()
    assert team.state.history["be"] == [{"task": "task for be", "report": "be done"}]


def test_max_parallel_caps_workers():
    runner = OverlapRunner(delay=0.15)
    team = _team(runner, max_parallel=2)
    result = team.execute(DELEGATE_PARALLEL_TOOL, _tasks("be", "fe", "qa"))
    assert runner.max_active == 2
    assert len(result["results"]) == 3 and result["failed"] == []


def test_duplicate_members_are_rejected_before_anything_runs():
    runner = OverlapRunner(delay=0)
    team = _team(runner)
    with pytest.raises(ValueError, match="more than once"):
        team.execute(DELEGATE_PARALLEL_TOOL, _tasks("be", "fe", "be"))
    assert runner.calls == [] and team.delegations == 0
    with pytest.raises(ValueError, match="at least 2"):
        team.execute(DELEGATE_PARALLEL_TOOL, _tasks("be"))
    with pytest.raises(ValueError, match="not on your team"):
        team.execute(DELEGATE_PARALLEL_TOOL, _tasks("be", "ghost"))
    with pytest.raises(ValueError, match="task is required"):
        team.execute(DELEGATE_PARALLEL_TOOL, {"tasks": [{"member": "be", "task": "x"}, {"member": "fe", "task": " "}]})
    assert runner.calls == [] and team.delegations == 0


def test_each_parallel_task_counts_toward_the_limit():
    runner = OverlapRunner(delay=0)
    team = _team(runner, max_delegations=3)
    assert team.execute(DELEGATE_PARALLEL_TOOL, _tasks("be", "fe"))["delegations_left"] == 1
    with pytest.raises(ValueError, match="only 1 of 3"):
        team.execute(DELEGATE_PARALLEL_TOOL, _tasks("be", "qa"))
    assert team.execute("delegate_task", {"member": "qa", "task": "test"})["delegations_left"] == 0
    with pytest.raises(ValueError, match="limit"):
        team.execute(DELEGATE_PARALLEL_TOOL, _tasks("be", "fe"))
    assert sorted(runner.calls) == ["be", "fe", "qa"]


def test_one_failure_keeps_the_other_reports():
    runner = OverlapRunner(delay=0.05, fail={"fe"})
    team = _team(runner)
    result = team.execute(DELEGATE_PARALLEL_TOOL, _tasks("be", "fe", "qa"))
    by_member = {r["member"]: r for r in result["results"]}
    assert by_member["be"]["report"] == "be done" and by_member["qa"]["report"] == "qa done"
    assert "fe crashed" in by_member["fe"]["error"]
    assert result["failed"] == ["fe"]
    assert "fe" not in team.state.history and team.state.running == set()


def test_busy_member_is_reported_not_run_twice():
    runner = OverlapRunner(delay=0)
    team = _team(runner)
    team.state.running.add("fe")  # e.g. a nested lead is using it right now
    result = team.execute(DELEGATE_PARALLEL_TOOL, _tasks("be", "fe"))
    assert result["failed"] == ["fe"] and "already working" in result["results"][1]["error"]
    assert runner.calls == ["be"]


def test_cancellation_propagates():
    def runner(member, inputs, lead):
        if member == "fe":
            raise WorkflowCancelledError("stopped")
        return [Message(role=MessageRole.ASSISTANT, content="ok")]

    team = _team(runner)
    with pytest.raises(WorkflowCancelledError):
        team.execute(DELEGATE_PARALLEL_TOOL, _tasks("be", "fe"))
    assert team.state.running == set()


def test_needs_user_decision_bubbles_up():
    team = _team(lambda m, i, l: [Message(role=MessageRole.ASSISTANT, content="DECISION NEEDED: A or B?" if m == "be" else "ok")])
    result = team.execute(DELEGATE_PARALLEL_TOOL, _tasks("be", "fe"))
    assert result["needs_user_decision"] is True and result["results"][0]["needs_user_decision"] is True


# ---------------------------------------------------------------- shared runtime state

def test_logger_path_survives_out_of_order_exits():
    logger = WorkflowLogger("w", use_structured_logging=False, log_to_console=False)
    logger.enter_node("cto", [])
    logger.enter_node("be", [])
    logger.enter_node("fe", [])
    logger.exit_node("be", "")  # be finishes first while fe is still running
    assert logger.current_path == ["cto", "fe"]
    logger.exit_node("fe", "")
    logger.exit_node("cto", "")
    assert logger.current_path == []


def test_token_tracker_is_thread_safe():
    tracker = TokenTracker("w")

    def work(node):
        for _ in range(500):
            tracker.record_usage(node, "m", TokenUsage(input_tokens=1, output_tokens=1, total_tokens=2))

    threads = [threading.Thread(target=work, args=(f"n{i}",)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert tracker.total_usage.total_tokens == 4000
    assert len(tracker.get_token_usage()["call_history"]) == 2000


def test_tool_context_overlays_node_id_without_touching_global_state():
    base = {"python_workspace_root": "/ws"}
    ctx = agent_executor_module._NodeToolContext(base, "be")
    assert ctx["node_id"] == "be" and ctx.get("python_workspace_root") == "/ws"
    ctx["note"] = 1
    ctx.setdefault("other", 2)
    assert "node_id" not in base and base["note"] == 1 and base["other"] == 2


# ---------------------------------------------------------------- end to end

class ParallelProvider:
    """Scripted per node; members wait on a barrier so the run fails unless they overlap."""

    scripts = {}
    seen = {}
    barrier = None
    lock = threading.Lock()

    def __init__(self, config):
        self.config = config

    def create_client(self):
        return None

    def call_model(self, client, conversation, timeline, tool_specs=None, **kwargs):
        node_id = self.config.node_id
        with self.lock:
            self.seen.setdefault(node_id, []).append(
                {"conversation": [m.text_content() for m in conversation], "tools": [s.name for s in tool_specs or []]}
            )
            step = self.scripts[node_id].pop(0)
            count = len(self.seen[node_id])
        if node_id != "CTO":
            self.barrier.wait()  # raises BrokenBarrierError (timeout) if members ran one at a time
        if isinstance(step, tuple):
            name, args = step
            call = ToolCallPayload(id=f"call-{count}", function_name=name, arguments=json.dumps(args))
            return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content="", tool_calls=[call]))
        return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=step))

    def extract_token_usage(self, response):
        return None


@pytest.fixture()
def parallel_workflow(tmp_path, monkeypatch):
    def agent(node_id, role, team=None):
        config = {"connection": "fake", "provider": "fake", "name": "fake-model", "role": role}
        if team:
            config["team"] = team
        return {"id": node_id, "type": "agent", "description": role, "config": config}

    definition = {
        "version": "0.4.0",
        "graph": {
            "id": "team_parallel_test",
            "start": ["CTO"],
            "end": ["CTO"],
            "nodes": [
                agent("CTO", "You are the CTO.", team={"enabled": True, "plan_approval": False, "max_parallel": 3}),
                agent("Backend Dev", "Backend developer"),
                agent("Frontend Dev", "Frontend developer"),
                agent("Data Engineer", "Data engineer"),
            ],
            "edges": [],
        },
    }
    path = tmp_path / "team.yaml"
    path.write_text(yaml.safe_dump(definition), encoding="utf-8")
    creds = SimpleNamespace(provider="fake", vendor="fake", token="", base_url="")
    monkeypatch.setattr(agent_executor_module, "resolve_connection", lambda _id: creds)
    monkeypatch.setattr(ProviderRegistry, "get_provider", lambda _name: ParallelProvider)
    monkeypatch.setattr(HumanPromptService, "request", lambda *a, **k: PromptResult(text="ok"))
    ParallelProvider.seen = {}
    ParallelProvider.barrier = threading.Barrier(3, timeout=10)
    return path


def test_lead_runs_members_in_parallel_end_to_end(parallel_workflow):
    from agentdev.runtime.sdk import run_workflow

    ParallelProvider.scripts = {
        "CTO": [
            (
                "delegate_parallel",
                {
                    "tasks": [
                        {"member": "Backend Dev", "task": "Build /orders API"},
                        {"member": "Frontend Dev", "task": "Build orders page"},
                        {"member": "Data Engineer", "task": "Create orders table"},
                    ]
                },
            ),
            "Đã xong cả ba phần.",
        ],
        "Backend Dev": ["API /orders done"],
        "Frontend Dev": ["Orders page done"],
        "Data Engineer": ["orders table created"],
    }

    result = run_workflow(parallel_workflow, task_prompt="Làm tính năng đơn hàng")

    assert result.final_message.text_content() == "Đã xong cả ba phần."
    cto_calls = ParallelProvider.seen["CTO"]
    assert "delegate_parallel" in cto_calls[0]["tools"]
    tool_result = next(text for text in cto_calls[1]["conversation"] if "API /orders done" in text)
    assert "Orders page done" in tool_result and "orders table created" in tool_result
    assert '"failed": []' in tool_result
    for member, task in (("Backend Dev", "Build /orders API"), ("Frontend Dev", "Build orders page")):
        convo = ParallelProvider.seen[member][0]["conversation"]
        assert any(task in text for text in convo)
        assert "delegate_parallel" not in ParallelProvider.seen[member][0]["tools"]
    assert ParallelProvider.scripts["CTO"] == []
