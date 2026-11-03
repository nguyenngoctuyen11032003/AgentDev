"""Regression tests for bugs found in a code review pass."""
from agentdev.entity.configs import Node
from agentdev.entity.messages import Message, MessageRole
from agentdev.runtime.node.agent.memory.blackboard_memory import BlackboardMemory
from agentdev.runtime.node.executor.python_executor import PythonNodeExecutor
from agentdev.runtime.node.executor.base import ExecutionContext
from agentdev.utils.code_execution import UNSAFE_CODE_EXECUTION_ENV


def test_python_node_passes_config_env_to_script(tmp_path, monkeypatch):
    monkeypatch.setenv(UNSAFE_CODE_EXECUTION_ENV, "1")
    context = ExecutionContext(
        tool_manager=None, function_manager=None, log_manager=None,
        global_state={"python_workspace_root": tmp_path / "ws", "vars": {UNSAFE_CODE_EXECUTION_ENV: "1"}},
    )
    node = Node.from_dict({"id": "Runner", "type": "python", "config": {"env": {"MY_CFG_VAR": "hello"}}}, path="node")
    code = "import os; print(os.environ['MY_CFG_VAR'], os.environ['MAC_NODE_ID'])"
    out = PythonNodeExecutor(context).execute(node, [Message(role=MessageRole.USER, content=code)])
    assert out[0].text_content().strip() == "hello Runner"


def test_blackboard_memory_saves_to_bare_filename(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.chdir(tmp_path)
    mem = BlackboardMemory.__new__(BlackboardMemory)
    mem.memory_path = "board.json"
    mem.max_items = 10
    mem.contents = []
    mem.save()  # used to raise FileNotFoundError from os.makedirs("")
    assert (tmp_path / "board.json").exists()
