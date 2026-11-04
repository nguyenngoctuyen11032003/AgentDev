"""Regression tests for runtime bugs found in the review of 79f6c08..HEAD."""

import threading
import time
from types import SimpleNamespace

from agentdev.api.services.session_store import WorkflowSession, note_changed_files
from agentdev.entity.configs import GraphDefinition
from agentdev.entity.graph_config import GraphConfig
from agentdev.entity.messages import Message, MessageRole, ToolCallPayload
from agentdev.runtime.node.agent import team as team_mod
from agentdev.runtime.node.agent.team import TeamState
from agentdev.runtime.node.executor import agent_executor as ae
from agentdev.workflow.cycle_manager import CycleManager

BIG = "x" * 5000


# --- 1. a fresh tool batch is never clipped before the model reads it -------------------------

def test_compact_skips_latest_batch():
    conv = [Message(role=MessageRole.USER, content="hi")]
    conv += [Message(role=MessageRole.TOOL, content=BIG, tool_call_id=f"old{i}") for i in range(2)]
    latest = len(conv)
    conv += [Message(role=MessageRole.TOOL, content=BIG, tool_call_id=f"new{i}") for i in range(5)]
    ae.AgentNodeExecutor._compact_old_tool_results(conv, 1, latest)
    assert all(len(m.content) == 5000 for m in conv[latest:])
    assert all(m.content.endswith(ae.OLD_TOOL_RESULT_MARKER) for m in conv[1:latest])


def test_tool_loop_model_sees_full_parallel_batch():
    ex = ae.AgentNodeExecutor.__new__(ae.AgentNodeExecutor)
    calls = [ToolCallPayload(id=f"c{i}", function_name="read", arguments="{}") for i in range(5)]
    seen = []

    def invoke(provider, client, conversation, *rest):
        seen.append([len(m.content) for m in conversation if m.role == MessageRole.TOOL])
        return SimpleNamespace(message=Message(role=MessageRole.ASSISTANT, content="done"))

    ex._ensure_not_cancelled = lambda: None
    ex._clone_with_source = lambda m, nid: m.clone()
    ex._get_tool_loop_limit = lambda node: 10
    ex._execute_tool_batch = lambda node, tcs, specs, sm: (
        [Message(role=MessageRole.TOOL, content=BIG, tool_call_id=c.id) for c in tcs], []
    )
    ex._submitted_plan_answer = lambda node: None
    ex._apply_interjections = lambda node, conv: False
    ex._invoke_provider = invoke
    ex._finalize_tool_trace = lambda msg, trace, ok, nid: msg

    first = Message(role=MessageRole.ASSISTANT, content="", tool_calls=calls)
    ex._handle_tool_calls(SimpleNamespace(id="n"), None, None, [], [], {}, SimpleNamespace(message=first), [], None)
    assert seen == [[5000] * 5]


# --- 2. YAML graph.run_limits reach the runtime via from_definition ----------------------------

def test_from_definition_carries_run_limits():
    limits = {"max_tokens": 1000, "node_max_runs": {"loop": 2}}
    graph = {"id": "g", "nodes": [], "edges": [], "run_limits": limits}
    definition = GraphDefinition.from_dict(graph, path="graph")
    assert GraphConfig.from_definition(definition, name="g", output_root="out").run_limits == limits
    assert GraphConfig.from_dict(graph, name="g", output_root="out").run_limits == limits


# --- 3. a busy member is waited for long enough, but a cancel ends the wait --------------------

def test_member_busy_wait_is_long_and_cancellable():
    assert team_mod.MEMBER_BUSY_WAIT_SECONDS >= 30 * 60
    state = TeamState()
    assert state.claim("dev")
    cancel = threading.Event()
    threading.Timer(0.3, cancel.set).start()
    started = time.monotonic()
    assert state.wait_and_claim("dev", cancel.is_set) is False
    assert time.monotonic() - started < 5


# --- 4. the cycle safety cap never cuts a loop_counter short -----------------------------------

class _Node:
    def __init__(self, node_id, node_type="agent", config=None):
        self.id, self.type, self.config = node_id, node_type, config
        self.predecessors, self.out = [], []

    def iter_outgoing_edges(self):
        return iter(self.out)


def _cycle(*nodes):
    by_id = {n.id: n for n in nodes}
    for a, b in zip(nodes, nodes[1:] + nodes[:1]):
        a.out.append(SimpleNamespace(target=b, trigger=True, condition=None, config=None))
        b.predecessors.append(a)
    mgr = CycleManager()
    mgr.initialize_cycles([set(by_id)], by_id)
    return next(iter(mgr.cycles.values()))


def test_cycle_cap_covers_loop_counter_limit():
    info = _cycle(_Node("A"), _Node("G", "loop_counter", SimpleNamespace(max_iterations=50)))
    assert info.get_max_iterations() == 51


def test_cycle_cap_default_without_loop_counter():
    info = _cycle(_Node("A"), _Node("B"))
    assert info.max_iterations is None and info.get_max_iterations() == 20
    small = _cycle(_Node("A"), _Node("G", "loop_counter", SimpleNamespace(max_iterations=3)))
    assert small.get_max_iterations() == 20


# --- 5. deleted files leave the "files changed so far" digest ----------------------------------

def _artifact(path, change_type, size=10):
    return {"type": "artifact_created", "data": {"events": [
        {"relative_path": path, "change_type": change_type, "size": size}]}}


def test_deleted_file_removed_from_changed_files():
    session = WorkflowSession(session_id="s", yaml_file="w.yaml", task_prompt="t")
    note_changed_files(session, _artifact("a.py", "created"))
    note_changed_files(session, _artifact("b.py", "modified"))
    note_changed_files(session, _artifact("a.py", "deleted"))
    assert session.changed_files == {"b.py": 10}


# --- clipping old tool results must not break a resumed Claude CLI session ---------------------

def _two_batch_loop(provider):
    """Run a tool loop of two 4-call batches; return the tool-result lengths of the second model call."""
    ex = ae.AgentNodeExecutor.__new__(ae.AgentNodeExecutor)
    batch = lambda tag: [ToolCallPayload(id=f"{tag}{i}", function_name="read", arguments="{}") for i in range(4)]
    seen = []

    def invoke(prov, client, conversation, *rest):
        seen.append([len(m.content) for m in conversation if m.role == MessageRole.TOOL])
        calls = batch("b") if len(seen) == 1 else []
        return SimpleNamespace(message=Message(role=MessageRole.ASSISTANT, content="" if calls else "done",
                                               tool_calls=calls))

    ex._ensure_not_cancelled = lambda: None
    ex._clone_with_source = lambda m, nid: m.clone()
    ex._get_tool_loop_limit = lambda node: 10
    ex._execute_tool_batch = lambda node, tcs, specs, sm: (
        [Message(role=MessageRole.TOOL, content=BIG, tool_call_id=c.id) for c in tcs], []
    )
    ex._submitted_plan_answer = lambda node: None
    ex._apply_interjections = lambda node, conv: False
    ex._invoke_provider = invoke
    ex._finalize_tool_trace = lambda msg, trace, ok, nid: msg
    first = Message(role=MessageRole.ASSISTANT, content="", tool_calls=batch("a"))
    ex._handle_tool_calls(SimpleNamespace(id="n"), provider, None, [], [], {}, SimpleNamespace(message=first), ["spec"], None)
    return seen[-1]


def test_resumed_cli_session_keeps_old_tool_results_unclipped():
    from agentdev.runtime.node.agent.providers.claude_cli_provider import ClaudeCliProvider

    prov = ClaudeCliProvider.__new__(ClaudeCliProvider)
    prov.params = {}
    assert prov.keeps_tool_history(["spec"]) is True
    assert _two_batch_loop(prov) == [5000] * 8  # nothing clipped: the session already holds them


def test_stateless_provider_still_clips_old_tool_results():
    lens = _two_batch_loop(SimpleNamespace())
    assert all(n < 5000 for n in lens[:4])  # first batch (already seen): clipped
    assert lens[4:] == [5000] * 4  # latest batch: unseen, kept whole


def test_session_reuse_off_allows_clipping():
    from agentdev.runtime.node.agent.providers.claude_cli_provider import ClaudeCliProvider

    prov = ClaudeCliProvider.__new__(ClaudeCliProvider)
    prov.params = {"session_reuse": False}
    assert prov.keeps_tool_history(["spec"]) is False


# --- 5. a loop that never exits must fail the run, not report success --------------------------

def test_endless_cycle_fails_instead_of_reporting_success(tmp_path, monkeypatch):
    import pytest

    from agentdev.runtime import sdk
    from agentdev.utils.exceptions import WorkflowExecutionError

    monkeypatch.chdir(tmp_path)
    regex = r"^(?!\s*ok)"
    flow = tmp_path / "endless.yaml"
    flow.write_text(
        "version: 0.4.0\n"
        "graph:\n"
        "  id: endless\n"
        "  start: [Maker]\n"
        "  end: [Done]\n"
        "  nodes:\n"
        "    - {id: Maker, type: literal, config: {content: draft, role: assistant}}\n"
        "    - {id: Judge, type: literal, config: {content: please revise, role: user}}\n"
        "    - {id: Done, type: literal, config: {content: finished, role: assistant}}\n"
        "  edges:\n"
        "    - {from: Maker, to: Judge}\n"
        f"    - {{from: Judge, to: Maker, condition: {{type: keyword, config: {{regex: ['{regex}'], case_sensitive: false}}}}}}\n"
        "    - {from: Judge, to: Done, condition: {type: keyword, config: {regex: ['^\s*ok'], case_sensitive: false}}}\n",
        encoding="utf-8",
    )
    with pytest.raises(WorkflowExecutionError):
        sdk.run_workflow(flow, task_prompt="t", session_name="endless")
