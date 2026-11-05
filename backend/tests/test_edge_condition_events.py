"""Edge conditions: a condition that raises must not fire the edge (fail-closed), and the run stream
gets a structured event for both an evaluation error and a real handoff."""

from types import SimpleNamespace

from agentdev.entity.enums import EventType, LogLevel
from agentdev.entity.messages import Message, MessageRole
from agentdev.entity.configs.node.node import EdgeLink
from agentdev.runtime.edge.conditions.base import ConditionFactoryContext, EdgeConditionManager
from agentdev.utils.log_manager import LogManager
from agentdev.utils.logger import WorkflowLogger


class _Manager(EdgeConditionManager):
    def __init__(self, evaluator):
        super().__init__(config=None, ctx=ConditionFactoryContext(), execution_context=None)
        self._evaluator = evaluator

    def process(self, edge_link, source_result, from_node, log_manager):
        self._process_with_condition(
            self._evaluator,
            label="test",
            metadata={},
            edge_link=edge_link,
            source_result=source_result,
            from_node=from_node,
            log_manager=log_manager,
        )


class _Node:
    def __init__(self, node_id):
        self.id = node_id
        self.inputs = []

    def append_input(self, payload):
        self.inputs.append(payload)


def _run(evaluator, *, trigger=True):
    log_manager = LogManager(WorkflowLogger("wf", LogLevel.DEBUG, log_to_console=False))
    source, target = _Node("A"), _Node("B")
    link = EdgeLink(target=target, trigger=trigger)
    _Manager(evaluator).process(link, Message(role=MessageRole.ASSISTANT, content="hi"), source, log_manager)
    events = [e for e in log_manager.get_logger().logs if e.event_type is not None]
    return link, target, events


def _of(events, kind):
    return [e for e in events if e.event_type == kind]


def _boom(_):
    raise RuntimeError("bad condition")


def test_raising_condition_does_not_fire_edge():
    link, target, events = _run(_boom)
    assert link.triggered is False
    assert target.inputs == []
    errors = _of(events, EventType.EDGE_CONDITION_ERROR)
    assert len(errors) == 1
    assert errors[0].level == LogLevel.WARNING
    assert errors[0].node_id == "A"
    assert errors[0].details["from"] == "A"
    assert errors[0].details["to"] == "B"
    assert "bad condition" in errors[0].details["error"]
    assert _of(events, EventType.HANDOFF) == []


def test_fired_edge_emits_handoff():
    link, target, events = _run(lambda _: True)
    assert link.triggered is True
    handoffs = _of(events, EventType.HANDOFF)
    assert len(handoffs) == 1
    assert handoffs[0].details["from"] == "A"
    assert handoffs[0].details["to"] == "B"


def test_unmet_condition_emits_no_handoff():
    link, _, events = _run(lambda _: False)
    assert link.triggered is False
    assert _of(events, EventType.HANDOFF) == []


def test_non_trigger_edge_carries_data_but_emits_no_handoff():
    link, target, events = _run(lambda _: True, trigger=False)
    assert link.triggered is False
    assert len(target.inputs) == 1
    assert _of(events, EventType.HANDOFF) == []
