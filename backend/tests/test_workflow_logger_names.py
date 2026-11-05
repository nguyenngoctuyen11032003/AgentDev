"""Each workflow run / chat session must log under its own name.

Regression: get_workflow_logger cached the first StructuredLogger, so every
later run (and unrelated chat sessions) logged as the first Lab job.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor

import pytest

from agentdev.utils import structured_logger as sl
from agentdev.utils.logger import WorkflowLogger


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records: list[dict] = []

    def emit(self, record):
        self.records.append(json.loads(record.getMessage()))


@pytest.fixture
def capture(monkeypatch):
    monkeypatch.setattr(sl, "_workflow_logger", None)
    cap = _Capture()
    root = logging.getLogger()
    root.addHandler(cap)
    old_level = root.level
    root.setLevel(logging.DEBUG)
    try:
        yield cap
    finally:
        root.removeHandler(cap)
        root.setLevel(old_level)


def _names_by_workflow(cap):
    return {(r["workflow_id"], r["logger"]) for r in cap.records if r.get("workflow_id")}


def test_sequential_runs_log_under_their_own_name(capture):
    first = WorkflowLogger("lab_bugfix_team_1", log_to_console=False)
    first.info("first run")
    second = WorkflowLogger("lab_project_planning_2", log_to_console=False)
    second.info("second run")
    chat = WorkflowLogger("session_87f238bb", log_to_console=False)
    chat.info("chat turn")

    assert _names_by_workflow(capture) == {
        ("lab_bugfix_team_1", "lab_bugfix_team_1"),
        ("lab_project_planning_2", "lab_project_planning_2"),
        ("session_87f238bb", "session_87f238bb"),
    }


def test_pool_reuse_keeps_names_separate(capture):
    def run(name):
        WorkflowLogger(name, log_to_console=False).info(f"run {name}")

    names = [f"lab_job_{i}" for i in range(6)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(run, names))
    run("session_after_lab")

    assert _names_by_workflow(capture) == {(n, n) for n in names + ["session_after_lab"]}


def test_workflow_loggers_share_one_base(capture):
    a = WorkflowLogger("a_run", log_to_console=False).structured_logger
    base = sl._workflow_logger
    b = WorkflowLogger("b_run", log_to_console=False).structured_logger
    assert sl._workflow_logger is base
    assert a.logger is b.logger is base.logger
    assert (a.name, b.name) == ("a_run", "b_run")
