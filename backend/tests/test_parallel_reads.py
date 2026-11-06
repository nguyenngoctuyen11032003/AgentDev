"""AGENTDEV_PARALLEL_READS: neighbouring pure read-only tool calls of one reply run side by side."""

import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agentdev.entity.messages import ToolCallPayload
from agentdev.entity.tool_spec import ToolSpec
from agentdev.runtime.node.executor import agent_executor as ae
from agentdev.runtime.node.executor.agent_executor import AgentNodeExecutor
from agentdev.utils.exceptions import WorkflowCancelledError

DELAY = 0.25


class SlowTools:
    def __init__(self, fail=()):
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0
        self.order = []
        self.fail = set(fail)

    async def execute_tool(self, name, arguments, config, *, tool_context=None):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.order.append(("start", name, arguments.get("p")))
        time.sleep(DELAY)
        with self.lock:
            self.active -= 1
        if arguments.get("p") in self.fail:
            raise RuntimeError(f"boom {arguments['p']}")
        if name == "cancel_me":
            raise WorkflowCancelledError("stop")
        return f"{name}:{arguments.get('p')}"


def _executor(tools):
    ex = object.__new__(AgentNodeExecutor)
    ex.context = SimpleNamespace(cancel_event=None, global_state={}, log_manager=MagicMock(), tool_manager=tools)
    return ex


def _setup(names):
    specs = [
        ToolSpec(name=n, description="", parameters={}, metadata={"source": "function", "_config_index": 0})
        for n in dict.fromkeys(names)
    ]
    node = SimpleNamespace(id="n", as_config=lambda _cls: SimpleNamespace(tooling=[SimpleNamespace(type="function")]))
    return node, specs


def _calls(items):
    return [
        ToolCallPayload(id=f"c{i}", function_name=name, arguments=json.dumps({"p": p}))
        for i, (name, p) in enumerate(items)
    ]


def _run(items, monkeypatch, flag, fail=()):
    monkeypatch.setenv("AGENTDEV_PARALLEL_READS", flag)
    tools = SlowTools(fail)
    ex = _executor(tools)
    node, specs = _setup([n for n, _ in items])
    start = time.perf_counter()
    messages, _events = ex._execute_tool_batch(node, _calls(items), specs, None)
    return messages, tools, time.perf_counter() - start


READS = [("search_in_files", i) for i in range(4)]


def test_reads_run_side_by_side_and_keep_order(monkeypatch):
    messages, tools, wall = _run(READS, monkeypatch, "1")
    assert tools.peak == 4
    assert wall < DELAY * 2  # about max, not the 4 x DELAY sum
    assert [m.text_content() for m in messages] == [f"search_in_files:{i}" for i in range(4)]
    assert [m.tool_call_id for m in messages] == ["c0", "c1", "c2", "c3"]


def test_flag_off_is_sequential(monkeypatch):
    messages, tools, wall = _run(READS, monkeypatch, "0")
    assert tools.peak == 1 and wall >= DELAY * 4 * 0.9
    assert len(messages) == 4


def test_errors_stay_per_call(monkeypatch):
    messages, tools, _ = _run(READS, monkeypatch, "1", fail=(1,))
    texts = [m.text_content() for m in messages]
    assert texts[0] == "search_in_files:0" and "boom 1" in texts[1] and texts[2] == "search_in_files:2"


def test_writes_are_never_parallel_and_split_runs(monkeypatch):
    items = [("read_file_segment", 0), ("edit_file", 1), ("read_file_segment", 2), ("read_file_segment", 3)]
    messages, tools, _ = _run(items, monkeypatch, "1")
    # the write runs alone and in place: nothing started after it before it started
    assert [o[2] for o in tools.order][:2] == [0, 1]
    assert tools.order[1][1] == "edit_file"
    assert [m.text_content() for m in messages] == [f"{n}:{p}" for n, p in items]


def test_cancel_in_a_read_stops_the_batch(monkeypatch):
    monkeypatch.setattr(ae, "PARALLEL_READ_TOOLS", ae.PARALLEL_READ_TOOLS | {"cancel_me"})
    with pytest.raises(WorkflowCancelledError):
        _run([("search_in_files", 0), ("cancel_me", 1)], monkeypatch, "1")


def test_whitelist_has_no_writers():
    assert not ({"edit_file", "multi_edit", "save_file", "load_file", "delete_path", "run_shell"} & ae.PARALLEL_READ_TOOLS)
