"""A condition function that cannot be found must not fire the edge (fail-closed)."""
from agentdev.entity.enums import EventType, LogLevel
from agentdev.entity.messages import Message, MessageRole
from agentdev.entity.configs.node.node import EdgeLink
from agentdev.entity.configs.edge.edge_condition import FunctionEdgeConditionConfig
from agentdev.runtime.edge.conditions.base import ConditionFactoryContext
from agentdev.runtime.edge.conditions.function_manager import FunctionEdgeConditionManager
from agentdev.utils.log_manager import LogManager
from agentdev.utils.logger import WorkflowLogger

class _Node:
    def __init__(self, i): self.id=i; self.inputs=[]
    def append_input(self, p): self.inputs.append(p)

def test_missing_condition_function_fails_closed():
    lm = LogManager(WorkflowLogger("wf", LogLevel.DEBUG, log_to_console=False))
    cfg = FunctionEdgeConditionConfig(name="typo_is_approved", path="p")
    m = FunctionEdgeConditionManager(cfg, ConditionFactoryContext(function_manager=None, log_manager=lm), None)
    link = EdgeLink(target=_Node("B"), trigger=True)
    m.process(link, Message(role=MessageRole.ASSISTANT, content="REJECTED"), _Node("A"), lm)
    kinds = [e.event_type for e in lm.get_logger().logs if e.event_type]
    assert link.triggered is False
    assert EventType.HANDOFF not in kinds and EventType.EDGE_CONDITION_ERROR in kinds


def test_true_literal_any_case_or_whitespace_always_fires():
    """Runtime must agree with the lint/editor: "True", " true " are the always-true condition."""
    for name in ("True", " true", "TRUE "):
        lm = LogManager(WorkflowLogger("wf", LogLevel.DEBUG, log_to_console=False))
        cfg = FunctionEdgeConditionConfig(name=name, path="p")
        m = FunctionEdgeConditionManager(cfg, ConditionFactoryContext(function_manager=None, log_manager=lm), None)
        link = EdgeLink(target=_Node("B"), trigger=True)
        m.process(link, Message(role=MessageRole.ASSISTANT, content="x"), _Node("A"), lm)
        assert link.triggered is True, name
