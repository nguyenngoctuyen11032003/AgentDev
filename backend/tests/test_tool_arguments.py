"""A model calling a function tool with wrong argument names is the model's mistake, not an AgentDev bug: the
tool manager raises ToolArgumentError (not TypeError) so the Lab does not report it as a platform problem."""

import pytest

from agentdev.api.services.lab_diagnosis import PYTHON_BUG_TYPES
from agentdev.runtime.node.agent.tool.tool_manager import ToolArgumentError, bind_tool_arguments


def _tool(path: str, limit: int = 10):
    return path, limit


def test_wrong_argument_names_raise_tool_argument_error():
    with pytest.raises(ToolArgumentError) as info:
        bind_tool_arguments(_tool, {"file": "a.txt"})
    assert "path" in str(info.value) or "file" in str(info.value)
    assert type(info.value).__name__ not in PYTHON_BUG_TYPES


def test_right_arguments_pass_and_a_bug_inside_the_tool_stays_a_bug():
    bind_tool_arguments(_tool, {"path": "a.txt"})

    def broken(path: str):
        return None.upper()  # a real bug in the tool body

    bind_tool_arguments(broken, {"path": "x"})
    with pytest.raises(AttributeError):
        broken(path="x")


def test_uninspectable_callables_are_not_blocked():
    bind_tool_arguments(print, {"sep": " "})  # builtins may have no signature: never refuse them
