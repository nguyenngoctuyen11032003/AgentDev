import threading
import time

import pytest

from agentdev.entity.messages import Message, MessageRole
from agentdev.runtime.node.executor import agent_executor as ae
from agentdev.utils.exceptions import WorkflowCancelledError
from agentdev.workflow.executor.parallel_executor import ParallelExecutor


class _Log:
    def debug(self, *a, **k): pass
    def error(self, *a, **k): pass


def test_old_tool_results_are_clipped_recent_kept():
    big = "x" * 5000
    conv = [Message(role=MessageRole.USER, content="hi")]
    for i in range(5):
        conv.append(Message(role=MessageRole.TOOL, content=big, tool_call_id=str(i)))
    ae.AgentNodeExecutor._compact_old_tool_results(conv, 1)
    tools = [m for m in conv if m.role == MessageRole.TOOL]
    assert all(len(m.content) == 5000 for m in tools[-3:])
    for m in tools[:2]:
        assert m.content.endswith(ae.OLD_TOOL_RESULT_MARKER)
        assert len(m.content) < 2000
        assert m.tool_call_id in ("0", "1")


def test_few_tool_results_untouched():
    conv = [Message(role=MessageRole.TOOL, content="y" * 5000, tool_call_id=str(i)) for i in range(3)]
    ae.AgentNodeExecutor._compact_old_tool_results(conv, 0)
    assert all(len(m.content) == 5000 for m in conv)


def test_parallel_surfaces_first_real_error():
    pe = ParallelExecutor(_Log(), {})

    def run(item):
        if item == "bad":
            raise ValueError("boom")
        time.sleep(0.05)

    with pytest.raises(ValueError):
        pe.execute_items_parallel(["a", "bad", "c"], run, str)


def test_parallel_shared_cancel_event_skips_items():
    pe = ParallelExecutor(_Log(), {})
    ev = threading.Event()
    ev.set()
    pe.cancel_event = ev
    ran = []
    with pytest.raises(WorkflowCancelledError):
        pe.execute_items_parallel(["a", "b"], ran.append, str)
    assert ran == []
