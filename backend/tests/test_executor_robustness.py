"""Agent executor robustness: cancellation, parallel delegate_task, tool limit, fallback chain, skills."""

import json
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml

from agentdev.connections import store as store_module
from agentdev.connections.store import Connection
from agentdev.entity.messages import Message, MessageRole, ToolCallPayload
from agentdev.runtime.node.agent import ModelResponse, ProviderRegistry
from agentdev.runtime.node.agent import account_fallback
from agentdev.runtime.node.agent.account_fallback import QuotaExceededError
from agentdev.runtime.node.agent.providers.cli_cancel import CliCancelled, current_cancel_event
from agentdev.runtime.node.agent.skills import manager as skills_manager_module
from agentdev.runtime.node.agent.skills.manager import AgentSkillManager
from agentdev.runtime.node.executor import agent_executor as agent_executor_module
from agentdev.runtime.node.executor.agent_executor import AgentNodeExecutor
from agentdev.utils.exceptions import WorkflowCancelledError
from agentdev.utils.human_prompt import HumanPromptService, PromptResult


# ---------------------------------------------------------------- helpers

class ScriptedProvider:
    """Replies from a per-node script. A step is text, a list of (tool, args) calls, or an exception."""

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
                {
                    "messages": [(m.role, m.text_content()) for m in conversation],
                    "tools": [s.name for s in tool_specs or []],
                    "cancel_event": current_cancel_event(),
                }
            )
            step = self.scripts[node_id].pop(0)
            count = len(self.seen[node_id])
        if self.barrier is not None and node_id != "CTO":
            self.barrier.wait()
        if isinstance(step, BaseException):
            raise step
        if isinstance(step, list):
            calls = [
                ToolCallPayload(id=f"call-{count}-{i}", function_name=name, arguments=json.dumps(args))
                for i, (name, args) in enumerate(step)
            ]
            return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content="", tool_calls=calls))
        return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=step))

    def extract_token_usage(self, response):
        return None


def _agent(node_id, role, **extra):
    config = {"connection": "fake", "provider": "fake", "name": "fake-model", "role": role, **extra}
    return {"id": node_id, "type": "agent", "description": role, "config": config}


def _write(tmp_path, nodes, start="CTO"):
    definition = {"version": "0.4.0",
                  "graph": {"id": "robust_test", "start": [start], "end": [start], "nodes": nodes, "edges": []}}
    path = tmp_path / "wf.yaml"
    path.write_text(yaml.safe_dump(definition), encoding="utf-8")
    return path


@pytest.fixture()
def scripted(monkeypatch):
    creds = SimpleNamespace(provider="fake", vendor="fake", token="", base_url="")
    monkeypatch.setattr(agent_executor_module, "resolve_connection", lambda _id: creds)
    monkeypatch.setattr(ProviderRegistry, "get_provider", lambda _name: ScriptedProvider)
    monkeypatch.setattr(HumanPromptService, "request", lambda *a, **k: PromptResult(text="ok"))
    ScriptedProvider.seen = {}
    ScriptedProvider.barrier = None
    return ScriptedProvider


def _bare_executor():
    executor = object.__new__(AgentNodeExecutor)
    executor.context = SimpleNamespace(cancel_event=None, global_state={}, log_manager=MagicMock())
    return executor


# ---------------------------------------------------------------- 1. cancellation

@pytest.mark.parametrize("error", [WorkflowCancelledError("stop"), CliCancelled("killed")])
def test_team_tool_does_not_swallow_cancellation(error):
    executor = _bare_executor()

    def execute(_name, _args):
        raise error

    executor._active_teams()["lead"] = SimpleNamespace(execute=execute)
    call = ToolCallPayload(id="c1", function_name="delegate_task", arguments="{}")
    with pytest.raises(WorkflowCancelledError):
        executor._run_team_tool(SimpleNamespace(id="lead"), call, "delegate_task", {}, [])


def test_cli_cancel_is_not_retried_and_stops_the_run(tmp_path, scripted):
    from agentdev.runtime.sdk import run_workflow

    scripted.scripts = {"A": [CliCancelled("killed"), "never"]}
    path = _write(tmp_path, [_agent("A", "worker")], start="A")
    with pytest.raises(Exception) as info:
        run_workflow(path, task_prompt="go")
    chain, exc = [], info.value
    while exc is not None:
        chain.append(type(exc).__name__)
        exc = exc.__cause__ or exc.__context__
    assert "WorkflowCancelledError" in chain or "CliCancelled" in chain
    assert len(scripted.seen["A"]) == 1  # no retry, no account switch
    assert scripted.scripts["A"] == ["never"]


# ---------------------------------------------------------------- 3. parallel delegate_task

def test_two_delegate_task_calls_run_concurrently_in_order(tmp_path, scripted):
    from agentdev.runtime.sdk import run_workflow

    scripted.barrier = threading.Barrier(2, timeout=10)  # fails unless both members overlap
    scripted.scripts = {
        "CTO": [
            [("delegate_task", {"member": "BE", "task": "Build API"}),
             ("delegate_task", {"member": "FE", "task": "Build page"})],
            "Both done.",
        ],
        "BE": ["API done"],
        "FE": ["page done"],
    }
    path = _write(tmp_path, [
        _agent("CTO", "lead", team={"enabled": True, "plan_approval": False, "max_parallel": 3}),
        _agent("BE", "backend"),
        _agent("FE", "frontend"),
    ])
    result = run_workflow(path, task_prompt="Build orders")

    assert result.final_message.text_content() == "Both done."
    tool_results = [text for role, text in scripted.seen["CTO"][1]["messages"] if role == MessageRole.TOOL]
    assert len(tool_results) == 2
    assert "API done" in tool_results[0] and "page done" in tool_results[1]


# ---------------------------------------------------------------- 4. tool loop limit

def test_tool_limit_ends_with_a_status_report(tmp_path, scripted):
    from agentdev.runtime.sdk import run_workflow

    delegate = [("delegate_task", {"member": "BE", "task": "Build API"})]
    scripted.scripts = {
        "CTO": [delegate, delegate, "Status: API built, page still open."],
        "BE": ["API done", "more"],
    }
    path = _write(tmp_path, [
        _agent("CTO", "lead", team={"enabled": True, "plan_approval": False}, params={"tool_loop_limit": 1}),
        _agent("BE", "backend"),
    ])
    result = run_workflow(path, task_prompt="Build orders")

    assert result.final_message.text_content() == "Status: API built, page still open."
    last = scripted.seen["CTO"][-1]
    assert last["tools"] == []
    assert "status report" in last["messages"][-1][1]
    assert len(scripted.seen["BE"]) == 1  # the call over the limit was not executed


# ---------------------------------------------------------------- 6. account fallback chain

class FakeStore:
    def __init__(self, conns):
        self.conns = {c.id: c for c in conns}

    def list(self):
        return list(self.conns.values())

    def get(self, conn_id):
        return self.conns.get(conn_id)

    def default_connection(self):
        return None


def test_fallback_walks_the_chain_and_restores_user_model(tmp_path, monkeypatch):
    from agentdev.runtime.sdk import run_workflow

    claude = Connection(id="claude-main", vendor="anthropic", label="Claude", auth_type="oauth")
    codex = Connection(id="codex-main", vendor="openai", label="Codex")
    claude2 = Connection(id="claude-2", vendor="anthropic", label="Claude 2", auth_type="oauth")
    fake_store = FakeStore([claude, codex, claude2])
    monkeypatch.setattr(store_module, "get_store", lambda: fake_store)
    monkeypatch.setattr(account_fallback, "get_store", lambda: fake_store)
    defaults = {"openai": "gpt-codex", "anthropic": "claude-default"}
    monkeypatch.setattr(agent_executor_module, "default_model_for", lambda conn: defaults[conn.vendor])
    creds = {cid: SimpleNamespace(provider=cid, vendor=c.vendor, token="", base_url="")
             for cid, c in fake_store.conns.items()}
    monkeypatch.setattr(agent_executor_module, "resolve_connection", lambda cid: creds[cid])
    calls = []

    def provider_for(conn_id, exhausted):
        class Provider:
            def __init__(self, config):
                self.config = config

            def create_client(self):
                return None

            def call_model(self, client, conversation, timeline, tool_specs=None, **kwargs):
                calls.append((conn_id, self.config.name))
                if exhausted:
                    raise QuotaExceededError(f"{conn_id} usage limit reached")
                return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=f"via {conn_id}"))

            def extract_token_usage(self, response):
                return None

        return Provider

    providers = {"claude-main": provider_for("claude-main", True), "codex-main": provider_for("codex-main", True),
                 "claude-2": provider_for("claude-2", False)}
    monkeypatch.setattr(ProviderRegistry, "get_provider", lambda name: providers[name])
    node = {"id": "A", "type": "agent",
            "config": {"connection": "claude-main", "provider": "anthropic", "name": "claude-x", "role": "r"}}
    path = _write(tmp_path, [node], start="A")

    result = run_workflow(path, task_prompt="go")

    assert result.final_message.text_content() == "via claude-2"
    # Claude -> Codex -> Claude 2; back on Anthropic the user's model returns, not the vendor default.
    assert calls == [("claude-main", "claude-x"), ("codex-main", "gpt-codex"), ("claude-2", "claude-x")]


# ---------------------------------------------------------------- 7. skill activation

SKILL_BODY = "UNIQUE-SKILL-BODY: always write tests first."


@pytest.fixture()
def skills_root(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    skill = root / "demo"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo\ndescription: Demo skill. Use when testing.\n"
        "allowed-tools: Bash(npx impeccable *) Read\n---\n" + SKILL_BODY + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(skills_manager_module, "DEFAULT_SKILLS_ROOT", root)
    return root


def test_skill_body_sent_once_at_the_end(tmp_path, scripted, skills_root):
    from agentdev.runtime.sdk import run_workflow

    activate = [("activate_skill", {"skill_name": "demo"})]
    scripted.scripts = {"A": [activate, activate, "done"]}
    path = _write(tmp_path, [_agent("A", "worker", skills={"enabled": True, "allow": ["demo"]})], start="A")
    result = run_workflow(path, task_prompt="go")

    assert result.final_message.text_content() == "done"
    after_first = scripted.seen["A"][1]["messages"]
    role, text = after_first[-1]
    assert role == MessageRole.USER and "[Skill instructions: demo]" in text and SKILL_BODY in text
    tool_text = next(t for r, t in after_first if r == MessageRole.TOOL)
    assert json.loads(tool_text) == {"skill": "demo", "loaded": True}
    final_convo = scripted.seen["A"][2]["messages"]
    assert sum(SKILL_BODY in t for _r, t in final_convo) == 1  # re-activation adds nothing
    assert not any(SKILL_BODY in t for r, t in final_convo if r == MessageRole.SYSTEM)
    assert '"already_active": true' in [t for r, t in final_convo if r == MessageRole.TOOL][-1]


# ---------------------------------------------------------------- 8. skill compatibility

def test_claude_code_allowed_tools_are_advisory(skills_root):
    manager = AgentSkillManager(available_tool_names=[])
    assert [s.name for s in manager.discover()] == ["demo"]
    assert manager.discover()[0].allowed_tools == ("Bash(npx impeccable *)", "Read")
    result = manager.activate_skill("demo")
    assert "path" not in result and str(skills_root) not in json.dumps(result)
    assert result["allowed_tools"] == []
    assert manager.enforced_tools(manager.discover()[0]) == ()

    with_read = AgentSkillManager(available_tool_names=["Read", "write_file"])
    assert with_read.enforced_tools(with_read.discover()[0]) == ("Read",)
    assert with_read.discovery_warnings() == []


# ---------------------------------------------------------------- 9. role + description + skills end to end

def test_member_works_from_role_description_and_skills(tmp_path, scripted, skills_root):
    from agentdev.runtime.sdk import run_workflow

    (skills_root / "demo" / "reference").mkdir()
    (skills_root / "demo" / "reference" / "rules.md").write_text("rule", encoding="utf-8")
    fe = _agent("FE", "You are the frontend engineer.", skills={"enabled": True, "allow": ["demo"]})
    fe["description"] = "Frontend dev (Vue)\nAlways mobile first; WCAG AA."
    activate = [("activate_skill", {"skill_name": "demo"})]
    scripted.scripts = {
        "CTO": [[("delegate_task", {"member": "FE", "task": "Build the login page"})], "All done."],
        "FE": [activate, "login page built; applied demo"],
    }
    path = _write(tmp_path, [_agent("CTO", "lead", team={"enabled": True, "plan_approval": False}), fe])
    result = run_workflow(path, task_prompt="Build login")
    assert result.final_message.text_content() == "All done."

    # The lead sees the member's skills in its roster, so it can route by skill.
    cto_system = [t for r, t in scripted.seen["CTO"][0]["messages"] if r == MessageRole.SYSTEM][0]
    assert "`FE`: Frontend dev (Vue) — skills: demo" in cto_system

    # The member's own prompt carries role, full description and the binding skill rules.
    fe_first = scripted.seen["FE"][0]["messages"]
    fe_system = "\n".join(t for r, t in fe_first if r == MessageRole.SYSTEM)
    assert "You are the frontend engineer." in fe_system
    assert "Always mobile first; WCAG AA." in fe_system
    assert "MUST be loaded first" in fe_system and "<name>demo</name>" in fe_system
    assert "Build the login page" in "\n".join(t for r, t in fe_first if r != MessageRole.SYSTEM)

    # Activating the skill delivers its body and its reference files.
    after = scripted.seen["FE"][1]["messages"][-1][1]
    assert SKILL_BODY in after and "reference/rules.md" in after
