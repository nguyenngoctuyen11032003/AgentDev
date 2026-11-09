"""The chat's mode menu: manual / plan / auto / bypass change how much a turn asks before acting."""

import pytest

from agentdev.api.models import WorkflowRequest
from agentdev.api.services.attachment_service import AttachmentService
from agentdev.api.services.prompt_channel import WebPromptChannel
from agentdev.api.services.session_execution import SessionExecutionController
from agentdev.api.services.session_store import WorkflowSessionStore
from agentdev.runtime.node.agent.team import SUBMIT_PLAN_TOOL
from agentdev.utils.attachments import AttachmentStore
from agentdev.utils.run_mode import (
    RUN_MODE_AUTO_ANSWER,
    RUN_MODE_KEY,
    answers_automatically,
    normalize_run_mode,
    plan_approval_for,
)

from tests.test_plan_gate import PLAN, ScriptedProvider, lead_workflow  # noqa: F401  (fixture)


def test_unknown_mode_falls_back_to_manual():
    assert normalize_run_mode(None) == "manual"
    assert normalize_run_mode("ROOT") == "manual"
    assert normalize_run_mode(" Bypass ") == "bypass"


@pytest.mark.parametrize(
    "mode, configured, expected",
    [("manual", True, True), ("manual", False, False), ("plan", False, True), ("auto", True, False), ("bypass", True, False)],
)
def test_plan_approval_per_mode(mode, configured, expected):
    assert plan_approval_for(mode, configured) is expected


def test_auto_keeps_human_gates_bypass_does_not():
    lead_question = {"node_type": "agent", "kind": "lead_question"}
    gate = {"node_type": "human"}
    assert not answers_automatically("manual", lead_question)
    assert not answers_automatically("plan", lead_question)
    assert answers_automatically("auto", lead_question)
    assert not answers_automatically("auto", gate)
    assert answers_automatically("bypass", gate)


def test_auto_answer_keeps_the_prefix_approval_gates_route_on():
    # Gates in front of paid steps send "[Automatic answer" to their skip branch (workflow lint)
    assert RUN_MODE_AUTO_ANSWER.startswith("[Automatic answer")
    # ...and never reads as consent to spend money
    assert "costs money" in RUN_MODE_AUTO_ANSWER and "do not start" in RUN_MODE_AUTO_ANSWER


def test_auto_answer_never_says_create_video():
    # The video workflow's Render Approval only renders on "tạo video"
    import re
    assert not re.search(r"^\s*((ok|có|co|đồng ý|dong y)\W*)?(tạo|tao)\s+video", RUN_MODE_AUTO_ANSWER, re.I)


def test_execute_request_defaults_to_manual_and_rejects_unknown_modes():
    assert WorkflowRequest(yaml_file="w.yaml", task_prompt="x").mode == "manual"
    assert WorkflowRequest(yaml_file="w.yaml", task_prompt="x", mode="auto").mode == "auto"
    with pytest.raises(Exception):
        WorkflowRequest(yaml_file="w.yaml", task_prompt="x", mode="root")


class _Sockets:
    def __init__(self):
        self.sent = []

    def send_message_sync(self, session_id, message):
        self.sent.append(message)


def _channel(tmp_path, mode):
    store = WorkflowSessionStore()
    store.create_session(session_id="m1", yaml_file="solo.yaml", task_prompt="x")
    controller = SessionExecutionController(store)

    def never(_sid, **_kw):
        raise AssertionError("must not wait for the user")

    sockets = _Sockets()
    channel = WebPromptChannel(
        session_id="m1",
        session_controller=controller,
        websocket_manager=sockets,
        attachment_service=AttachmentService(root=tmp_path / "a"),
        attachment_store=AttachmentStore(tmp_path / "s"),
        run_mode=mode,
    )
    return channel, controller, sockets, never


def test_bypass_answers_a_gate_without_waiting_and_tells_the_chat(tmp_path, monkeypatch):
    channel, controller, sockets, never = _channel(tmp_path, "bypass")
    monkeypatch.setattr(controller, "wait_for_human_input", never)
    result = channel.request(node_id="Script Approval", task="Duyệt?", metadata={"node_type": "human"})
    assert result.text == RUN_MODE_AUTO_ANSWER
    assert [m["type"] for m in sockets.sent] == ["auto_answered"]
    assert sockets.sent[0]["data"]["node_id"] == "Script Approval"


def test_auto_still_waits_on_a_human_gate(tmp_path, monkeypatch):
    channel, controller, sockets, _ = _channel(tmp_path, "auto")
    monkeypatch.setattr(controller, "wait_for_human_input", lambda sid, **kw: {"text": "OK"})
    result = channel.request(node_id="Script Approval", task="Duyệt?", metadata={"node_type": "human"})
    assert result.text == "OK"
    assert sockets.sent[0]["type"] == "human_input_required"


def _run_in_mode(path, prompt, mode):
    from agentdev.entity.graph_config import GraphConfig
    from agentdev.runtime.sdk import ensure_schema_registry_populated
    from agentdev.validation.check import load_config
    from agentdev.workflow.graph import GraphExecutor
    from agentdev.workflow.graph_context import GraphContext

    ensure_schema_registry_populated()
    design = load_config(path)
    config = GraphConfig.from_definition(design.graph, name="run_mode_test", output_root=path.parent / "out", source_path=str(path), vars=design.vars)
    executor = GraphExecutor(GraphContext(config=config))
    executor._get_execution_context().global_state[RUN_MODE_KEY] = mode
    executor._execute(prompt)
    return executor


def test_plan_mode_turns_the_plan_step_on(lead_workflow):  # noqa: F811
    ScriptedProvider.scripts = {"CTO": [(SUBMIT_PLAN_TOOL, {"plan": PLAN, "summary": "s"})], "Backend Dev": [], "Tester": []}
    executor = _run_in_mode(lead_workflow(plan_approval=False), "Làm web bán hàng mới", "plan")
    assert SUBMIT_PLAN_TOOL in ScriptedProvider.seen["CTO"][0]["tools"]
    assert executor.get_final_output_message().text_content() == PLAN


def test_auto_mode_skips_the_plan_step(lead_workflow):  # noqa: F811
    ScriptedProvider.scripts = {"CTO": ["Xong."], "Backend Dev": [], "Tester": []}
    _run_in_mode(lead_workflow(plan_approval=True), "Làm web bán hàng mới", "auto")
    assert SUBMIT_PLAN_TOOL not in ScriptedProvider.seen["CTO"][0]["tools"]


def test_gate_event_tells_the_chat_it_is_a_paid_gate(tmp_path, monkeypatch):
    # The Run screen must mark a paid gate before the person answers: the event carries the flag
    channel, controller, sockets, _ = _channel(tmp_path, "manual")
    monkeypatch.setattr(controller, "wait_for_human_input", lambda sid, **kw: {"text": "no"})
    channel.request(node_id="Render Approval", task="Tạo video?", metadata={"node_type": "human", "paid": True})
    data = sockets.sent[0]["data"]
    assert sockets.sent[0]["type"] == "human_input_required"
    assert data["node_type"] == "human" and data["paid"] is True


def test_lead_question_event_is_not_a_paid_gate(tmp_path, monkeypatch):
    channel, controller, sockets, _ = _channel(tmp_path, "manual")
    monkeypatch.setattr(controller, "wait_for_human_input", lambda sid, **kw: {"text": "React"})
    channel.request(node_id="CTO", task="Which stack?", metadata={"node_type": "agent", "kind": "lead_question"})
    data = sockets.sent[0]["data"]
    assert data["node_type"] == "agent" and data["paid"] is False


def test_paid_gate_timeout_is_a_refusal_not_proceed(tmp_path, monkeypatch):
    # Silence is never approval: a paid gate that times out must get the paid refusal, so even an unconditional
    # edge out of it does not start the paid step (function_manager blocks on AUTO_SKIP_PAID).
    from agentdev.api.services.session_execution import NO_REPLY_TEXT
    from agentdev.utils.human_prompt import AUTO_SKIP_PAID

    channel, controller, sockets, _ = _channel(tmp_path, "manual")
    monkeypatch.setattr(controller, "wait_for_human_input",
                        lambda sid, **kw: {"text": NO_REPLY_TEXT, "attachments": [], "timed_out": True})
    result = channel.request(node_id="Render Approval", task="Tạo video?", metadata={"node_type": "human", "paid": True})
    assert AUTO_SKIP_PAID in result.text and "Proceed" not in result.text
    assert sockets.sent[-1]["type"] == "human_input_timeout"


def test_free_gate_timeout_keeps_the_no_reply_text(tmp_path, monkeypatch):
    from agentdev.api.services.session_execution import NO_REPLY_TEXT

    channel, controller, sockets, _ = _channel(tmp_path, "manual")
    monkeypatch.setattr(controller, "wait_for_human_input",
                        lambda sid, **kw: {"text": NO_REPLY_TEXT, "attachments": [], "timed_out": True})
    result = channel.request(node_id="Review", task="OK?", metadata={"node_type": "human"})
    assert result.text == NO_REPLY_TEXT
