"""Tool-call argument coercion by schema, native-call rescue shapes, and CLI temp dir cleanup."""

import json
import os
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agentdev.entity.messages import ToolCallPayload
from agentdev.entity.tool_spec import ToolSpec
from agentdev.runtime.node.agent.providers import _cli_common as cc
from agentdev.runtime.node.agent.providers._native import native_calls_of_listed_tools
from agentdev.runtime.node.agent.tool.arg_coercion import ToolArgumentError, coerce_arguments
from agentdev.runtime.node.executor.agent_executor import AgentNodeExecutor

READ_SCHEMA = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "start_line": {"type": "integer"},
        "ratio": {"type": "number"},
        "recursive": {"type": "boolean"},
        "tasks": {"type": "array", "items": {"type": "object", "properties": {"n": {"type": "integer"}}}},
        "opts": {"type": "object"},
    },
}


# ---- 1. coercion ----------------------------------------------------------------------------------------------

def test_string_numbers_and_booleans_are_coerced():
    out = coerce_arguments(
        {"path": "a.py", "start_line": "12", "ratio": "0.5", "recursive": "true", "unknown": "7"}, READ_SCHEMA
    )
    assert out == {"path": "a.py", "start_line": 12, "ratio": 0.5, "recursive": True, "unknown": "7"}
    assert isinstance(out["start_line"], int) and out["recursive"] is True
    assert coerce_arguments({"recursive": "False", "start_line": "3.0"}, READ_SCHEMA) == {
        "recursive": False,
        "start_line": 3,
    }


def test_json_strings_become_arrays_and_objects_with_nested_coercion():
    out = coerce_arguments({"tasks": '[{"n": "2"}]', "opts": '{"a": 1}'}, READ_SCHEMA)
    assert out == {"tasks": [{"n": 2}], "opts": {"a": 1}}


def test_correct_values_and_empty_schema_are_untouched():
    args = {"start_line": 5, "recursive": False}
    assert coerce_arguments(args, READ_SCHEMA) == args
    assert coerce_arguments({"x": "1"}, {}) == {"x": "1"}
    assert coerce_arguments({"x": "1"}, None) == {"x": "1"}


@pytest.mark.parametrize(
    "args",
    [{"start_line": "abc"}, {"recursive": "maybe"}, {"tasks": "not json"}, {"start_line": [1]}, {"start_line": "1.5"}],
)
def test_uncoercible_values_raise_a_clear_error(args):
    with pytest.raises(ToolArgumentError) as err:
        coerce_arguments(args, READ_SCHEMA)
    assert next(iter(args)) in str(err.value)
    assert isinstance(err.value, ValueError)


def _exec(tools):
    ex = object.__new__(AgentNodeExecutor)
    ex.context = SimpleNamespace(cancel_event=None, global_state={}, log_manager=MagicMock(), tool_manager=tools)
    return ex


class RecordingTools:
    def __init__(self):
        self.seen = []

    async def execute_tool(self, name, arguments, config, *, tool_context=None):
        self.seen.append(arguments)
        return arguments["start_line"] < 100  # crashes for a string, like the real tools did


def _batch(arguments):
    tools = RecordingTools()
    ex = _exec(tools)
    spec = ToolSpec(name="read_file_segment", description="", parameters=READ_SCHEMA,
                    metadata={"source": "function", "_config_index": 0})
    node = SimpleNamespace(id="n", as_config=lambda _cls: SimpleNamespace(tooling=[SimpleNamespace(type="function")]))
    call = ToolCallPayload(id="c0", function_name="read_file_segment", arguments=json.dumps(arguments))
    messages, _ = ex._execute_tool_batch(node, [call], [spec], None)
    return tools, messages


def test_dispatch_coerces_before_the_tool_runs():
    tools, messages = _batch({"path": "a", "start_line": "7"})
    assert tools.seen == [{"path": "a", "start_line": 7}]
    assert "error" not in messages[0].text_content().lower()


def test_dispatch_reports_uncoercible_argument_without_running_the_tool():
    tools, messages = _batch({"path": "a", "start_line": "seven"})
    assert tools.seen == []
    text = messages[0].text_content()
    assert "start_line" in text and "integer" in text


# ---- 2. rescue shapes ------------------------------------------------------------------------------------------

def _stdout(name, args):
    event = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": args}]}}
    return json.dumps(event)


NAMES = ["delegate_task", "delegate_parallel"]


def test_rescued_single_task_list_maps_to_delegate_task():
    raw = json.dumps([{"member": "Code Scout", "task": "look"}])
    assert native_calls_of_listed_tools(_stdout("delegate_parallel", {"tasks": raw}), NAMES) == [
        ("delegate_task", {"member": "Code Scout", "task": "look"})
    ]
    one = {"tasks": [{"member": "A", "task": "t"}]}
    assert native_calls_of_listed_tools(_stdout("delegate_parallel", one), NAMES) == [
        ("delegate_task", {"member": "A", "task": "t"})
    ]
    bare = {"tasks": {"member": "A", "task": "t"}}
    assert native_calls_of_listed_tools(_stdout("delegate_parallel", bare), NAMES) == [
        ("delegate_task", {"member": "A", "task": "t"})
    ]


def test_rescued_several_tasks_stay_parallel_with_a_real_list():
    tasks = [{"member": "A", "task": "t"}, {"member": "B", "task": "u"}]
    out = native_calls_of_listed_tools(_stdout("delegate_parallel", {"tasks": json.dumps(tasks)}), NAMES)
    assert out == [("delegate_parallel", {"tasks": tasks})]


def test_single_task_without_delegate_task_in_names_is_left_alone():
    one = {"tasks": [{"member": "A", "task": "t"}]}
    assert native_calls_of_listed_tools(_stdout("delegate_parallel", one), ["delegate_parallel"]) == [
        ("delegate_parallel", one)
    ]


def test_normal_parallel_call_validation_is_unchanged():
    from agentdev.runtime.node.agent.team import TeamDelegation as AgentTeam

    team = object.__new__(AgentTeam)
    with pytest.raises(ValueError, match="at least 2"):
        team._parse_parallel_tasks([{"member": "A", "task": "t"}])
    with pytest.raises(ValueError, match="at least 2"):
        team._parse_parallel_tasks("[]")


# ---- 3. temp dir cleanup ---------------------------------------------------------------------------------------

def test_make_tempdir_is_owned_and_removed_on_error():
    with pytest.raises(RuntimeError):
        with cc.make_tempdir() as path:
            assert os.path.basename(path).startswith("agentdev-cli-")
            assert os.path.exists(os.path.join(path, cc.OWNER_MARKER))
            raise RuntimeError("boom")
    assert not os.path.exists(path)


def test_workdir_recreated_after_close_is_still_cleaned():
    class Owner:
        pass

    owner = Owner()
    state = cc.CliRunState(owner)
    first = state.workdir()
    state.close()
    assert not os.path.exists(first)
    second = state.workdir()  # a late call after close
    assert os.path.isdir(second)
    state.close()
    assert not os.path.exists(second)


def test_live_dirs_are_removed_at_exit():
    path = cc.make_owned_dir()
    assert path in cc.live_dirs()
    cc.cleanup_live_dirs()
    assert not os.path.exists(path)


def test_remove_tree_retries_a_locked_folder(monkeypatch, tmp_path):
    target = tmp_path / "agentdev-cli-x"
    target.mkdir()
    calls = {"n": 0}
    real = cc.shutil.rmtree

    def flaky(path, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise PermissionError("in use")
        return real(path, *a, **k)

    monkeypatch.setattr(cc.shutil, "rmtree", flaky)
    monkeypatch.setattr(cc.time, "sleep", lambda _s: None)
    assert cc.remove_tree(str(target)) is True
    assert not target.exists()


def _old(path, age_s):
    t = time.time() - age_s
    os.utime(path, (t, t))


def test_sweep_removes_only_stale_owned_dirs(tmp_path):
    day = 86400
    owned = tmp_path / "agentdev-cli-owned"
    owned.mkdir()
    (owned / cc.OWNER_MARKER).write_text("x")
    legacy = tmp_path / "agentdev-cli-legacy"
    legacy.mkdir()
    (legacy / "agentdev_system_ab12cd34.txt").write_text("x")
    empty = tmp_path / "agentdev-cli-empty"
    empty.mkdir()
    foreign = tmp_path / "agentdev-cli-foreign"
    foreign.mkdir()
    (foreign / "mywork.docx").write_text("x")
    fresh = tmp_path / "agentdev-cli-fresh"
    fresh.mkdir()
    (fresh / cc.OWNER_MARKER).write_text("x")
    other = tmp_path / "somebody-else"
    other.mkdir()
    in_use = tmp_path / "agentdev-cli-inuse"
    in_use.mkdir()
    (in_use / cc.OWNER_MARKER).write_text("x")
    for p in (owned, legacy, empty, foreign, other, in_use):
        _old(p, 2 * day)
    cc._LIVE.add(str(in_use))
    try:
        removed = cc.sweep_stale_tempdirs(root=str(tmp_path), max_age_s=day)
    finally:
        cc._LIVE.discard(str(in_use))
    assert removed == 3
    assert not owned.exists() and not legacy.exists() and not empty.exists()
    assert foreign.exists() and fresh.exists() and other.exists() and in_use.exists()


# ---- 4. PARALLEL_READS default (section 14) ---------------------------------------------------------------------

def test_parallel_reads_default_on_and_env_zero_disables(monkeypatch):
    from agentdev.runtime.node.executor.agent_executor import parallel_reads_enabled

    monkeypatch.delenv("AGENTDEV_PARALLEL_READS", raising=False)
    assert parallel_reads_enabled() is True
    for off in ("0", "false", "off", "no"):
        monkeypatch.setenv("AGENTDEV_PARALLEL_READS", off)
        assert parallel_reads_enabled() is False
