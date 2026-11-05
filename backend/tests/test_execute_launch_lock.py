"""Two launches racing on one session (double click, two tabs) must start exactly one run."""

import asyncio

import yaml

from agentdev.api import state
from agentdev.api.models import WorkflowRequest
from agentdev.api.routes import execute
from agentdev.api.services import workflow_run_service as run_service_module
from agentdev.api.services.attachment_service import AttachmentService
from agentdev.api.services.session_execution import SessionExecutionController
from agentdev.api.services.session_history import SessionHistoryStore
from agentdev.api.services.session_store import WorkflowSessionStore
from agentdev.api.services.websocket_manager import WebSocketManager
from agentdev.api.services.workflow_run_service import WorkflowRunService


def _setup(tmp_path, monkeypatch):
    yaml_dir = tmp_path / "yaml"
    yaml_dir.mkdir()
    (yaml_dir / "team.yaml").write_text(yaml.safe_dump({"version": "0.4.0", "graph": {"id": "g"}}), encoding="utf-8")
    monkeypatch.setattr(run_service_module, "YAML_DIR", yaml_dir)
    store = WorkflowSessionStore(history=SessionHistoryStore(root=tmp_path / "sessions"))
    service = WorkflowRunService(store, SessionExecutionController(store), AttachmentService())
    manager = WebSocketManager(session_store=store, workflow_run_service=service)
    manager.active_connections["s1"] = object()
    monkeypatch.setattr(state, "websocket_manager", manager)

    runs = []

    async def fake_execute(self, session_id, *args, **kwargs):
        runs.append(session_id)
        await asyncio.sleep(0.05)

    monkeypatch.setattr(WorkflowRunService, "_execute_workflow_async", fake_execute)

    async def no_send(session_id, message):
        return None

    monkeypatch.setattr(manager, "send_message", no_send)
    monkeypatch.setattr(manager, "record_user_message", lambda *a, **k: None)
    return service, runs


def test_two_concurrent_execute_requests_start_one_run(tmp_path, monkeypatch):
    service, runs = _setup(tmp_path, monkeypatch)
    request = WorkflowRequest(session_id="s1", yaml_file="team.yaml", task_prompt="build it")

    async def scenario():
        first, second = await asyncio.gather(execute.execute_workflow(request), execute.execute_workflow(request))
        await asyncio.sleep(0.2)  # let the spawned run(s) finish
        return first, second

    first, second = asyncio.run(scenario())
    assert isinstance(first, dict) and first["status"] == "started"
    assert second.status_code == 409
    assert b"run_in_progress" in second.body
    assert runs == ["s1"]
    # The claim is released once the run started: a later follow-up is accepted again.
    assert "s1" not in service._launching
    assert service.reserve_launch("s1")


def test_launch_cancelled_before_it_started_releases_the_claim(tmp_path, monkeypatch):
    service, runs = _setup(tmp_path, monkeypatch)
    request = WorkflowRequest(session_id="s1", yaml_file="team.yaml", task_prompt="build it")

    async def scenario():
        first = await execute.execute_workflow(request)
        # The spawned launch is cancelled before it ever ran (shutdown, loop teardown...)
        for task in list(execute._BACKGROUND_TASKS):
            task.cancel()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        second = await execute.execute_workflow(request)
        await asyncio.sleep(0.2)
        return first, second

    first, second = asyncio.run(scenario())
    assert first["status"] == "started"
    assert isinstance(second, dict) and second["status"] == "started"
    assert runs == ["s1"]


def test_stale_claim_expires(tmp_path, monkeypatch):
    service, _runs = _setup(tmp_path, monkeypatch)
    clock = [1000.0]
    monkeypatch.setattr(run_service_module.time, "monotonic", lambda: clock[0])
    assert service.reserve_launch("s1")
    assert not service.reserve_launch("s1")
    clock[0] += run_service_module.LAUNCH_CLAIM_TTL_SECONDS + 1
    assert service.reserve_launch("s1")  # nothing ever started under the old claim


def test_old_launch_finishing_does_not_release_a_newer_claim(tmp_path, monkeypatch):
    service, _runs = _setup(tmp_path, monkeypatch)
    old = service.reserve_launch("s1")
    service.release_launch("s1", old)
    new = service.reserve_launch("s1")
    service.release_launch("s1", old)  # late done-callback of the old launch
    assert not service.reserve_launch("s1")
    service.release_launch("s1", new)
    assert service.reserve_launch("s1")


def test_stop_between_accepted_launch_and_task_start_cancels_it(tmp_path, monkeypatch):
    service, runs = _setup(tmp_path, monkeypatch)
    sent = []

    async def capture(session_id, message):
        sent.append(message)

    monkeypatch.setattr(state.websocket_manager, "send_message", capture)
    request = WorkflowRequest(session_id="s1", yaml_file="team.yaml", task_prompt="build it")

    async def scenario():
        first = await execute.execute_workflow(request)
        # Stop clicked right after the POST returned, before the launch task ran
        assert service.request_cancel("s1", reason="User requested cancellation") is True
        await asyncio.sleep(0.2)
        return first

    first = asyncio.run(scenario())
    assert first["status"] == "started"
    assert runs == []  # the run never started
    assert [m["type"] for m in sent] == ["workflow_cancelled"]
    assert service.reserve_launch("s1")  # and the session is free again
