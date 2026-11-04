"""Mid-run user messages: classification, live progress snapshot, inbox, handler and agent injection."""

import asyncio
from types import SimpleNamespace

import pytest

from agentdev.api.services.message_handler import MessageHandler
from agentdev.entity.messages import Message, MessageRole
from agentdev.runtime.node.agent.interject import (
    INBOX_KEY,
    KIND_DIRECTIVE,
    KIND_STATUS,
    RunInbox,
    RunProgress,
    build_status,
    classify_note,
    get_run_inbox,
    route_note,
)
from agentdev.runtime.node.agent.team import TeamState
from agentdev.runtime.node.executor.agent_executor import AgentNodeExecutor


@pytest.mark.parametrize("text", [
    "sao làm lâu vậy",
    "sao lam lau vay?",
    "Tiến độ tới đâu rồi",
    "xong chưa",
    "why is it taking so long?",
    "any progress?",
    "进度怎么样了",
])
def test_status_questions(text):
    assert classify_note(text) == KIND_STATUS


@pytest.mark.parametrize("text", [
    "giao diện sao chưa thấy nút đăng nhập",
    "thêm trang quên mật khẩu nữa nhé",
    "the login button is missing, please add one and make the header sticky because users cannot find it",
    "",
])
def test_directives(text):
    assert classify_note(text) == KIND_DIRECTIVE


def test_progress_snapshot_tracks_running_and_done():
    now = [1000.0]
    progress = RunProgress(clock=lambda: now[0])
    progress.start("CTO")
    now[0] += 30
    progress.start("Frontend", "CTO")
    now[0] += 60
    progress.finish("Frontend")
    now[0] += 5
    snap = progress.snapshot()
    assert snap["elapsed"] == 95
    assert [r["node"] for r in snap["running"]] == ["CTO"]
    assert snap["running"][0]["seconds"] == 95
    assert snap["done"] == [{"node": "Frontend", "seconds": 60, "failed": False, "delegated_by": "CTO"}]


def test_status_reply_uses_real_progress_and_team_log():
    now = [0.0]
    progress = RunProgress(clock=lambda: now[0])
    progress.start("CTO")
    progress.start("Backend", "CTO")
    now[0] += 200
    state = TeamState()
    state.add_report("Frontend", "Build the login page", "done")
    gs = {"_run_progress": progress, "_team_state": state}
    text = build_status(gs, lead="CTO", lang="Vietnamese", waiting=True)
    assert "CTO" in text and "Backend" in text and "3 phút 20 giây" in text
    assert "Build the login page" in text
    assert "hơi lâu" in text  # a node over 3 minutes is called out
    assert "chờ bạn trả lời" in text


def test_status_question_does_not_touch_the_team():
    gs = {"_run_progress": RunProgress()}
    kind, reply, note = route_note("sao làm lâu vậy", gs, note_id="n1", lead="CTO")
    assert kind == KIND_STATUS and note is None and reply
    assert INBOX_KEY not in gs


def test_directive_is_queued_and_acknowledged():
    gs = {"_run_progress": RunProgress()}
    kind, reply, note = route_note("giao diện sao chưa thấy nút đăng nhập", gs, note_id="n2", lead="CTO")
    assert kind == KIND_DIRECTIVE and note is not None
    assert "CTO" in reply
    assert [n.id for n in get_run_inbox(gs).pending()] == ["n2"]


def test_lead_takes_each_note_once_and_is_told():
    inbox = RunInbox()
    events = []
    inbox.on_event = events.append
    inbox.post("add a login button", note_id="a")
    assert inbox.has_pending()
    assert [n.text for n in inbox.take_for_lead("CTO")] == ["add a login button"]
    assert not inbox.has_pending() and inbox.take_for_lead("CTO") == []
    assert events == [{"type": "interject_applied", "data": {"note_id": "a", "node": "CTO"}}]


def test_member_sees_a_note_once_without_consuming_it():
    inbox = RunInbox()
    inbox.post("use blue", note_id="a")
    assert len(inbox.take_for_member("Frontend")) == 1
    assert inbox.take_for_member("Frontend") == []
    assert inbox.has_pending()  # the lead still gets it
    assert len(inbox.take_for_member("Backend")) == 1


class _Exec(AgentNodeExecutor):
    """Only the interjection helpers: no graph, no provider."""

    def __init__(self, global_state):
        self.context = SimpleNamespace(global_state=global_state)

    def _append_user_message(self, conversation, content, *, node_id):
        conversation.append(Message(role=MessageRole.USER, content=content, metadata={"source": node_id}))


def test_lead_conversation_gets_the_note_before_next_model_call():
    gs = {}
    get_run_inbox(gs).post("add a login button", note_id="a")
    executor = _Exec(gs)
    node = SimpleNamespace(id="CTO")
    conversation = []
    assert executor._interjection_pending(node)
    assert executor._apply_interjections(node, conversation) is True
    assert "add a login button" in conversation[-1].text_content()
    assert not executor._interjection_pending(node)
    assert executor._apply_interjections(node, conversation) is False


def test_member_gets_read_only_heads_up(monkeypatch):
    from agentdev.runtime.node.executor import agent_executor

    gs = {}
    get_run_inbox(gs).post("use blue", note_id="a")
    monkeypatch.setattr(agent_executor, "is_delegated_call", lambda: True)
    executor = _Exec(gs)
    conversation = []
    assert executor._interjection_pending(SimpleNamespace(id="FE")) is False
    assert executor._apply_interjections(SimpleNamespace(id="FE"), conversation) is True
    assert "use blue" in conversation[-1].text_content()
    assert get_run_inbox(gs).has_pending()


class _WS:
    def __init__(self):
        self.sent, self.notes = [], []

    async def send_message(self, session_id, message):
        self.sent.append(message)

    def send_message_sync(self, session_id, message):
        self.sent.append(message)

    def record_user_note(self, session_id, text):
        self.notes.append(text)


def _handler(session):
    store = SimpleNamespace(get_session=lambda sid: session)
    return MessageHandler(store, SimpleNamespace())


def _live_session(waiting=False):
    gs = {"_run_progress": RunProgress()}
    return SimpleNamespace(
        executor=SimpleNamespace(runtime_context=SimpleNamespace(global_state=gs)),
        graph=SimpleNamespace(start_nodes=["CTO"]),
        cancel_event=SimpleNamespace(is_set=lambda: False),
        waiting_for_input=waiting,
    ), gs


def _send(handler, ws, text):
    asyncio.run(handler.handle_message("s1", {"type": "interject", "data": {"id": "n1", "text": text}}, ws))


def test_handler_answers_status_instantly_from_lead():
    session, gs = _live_session()
    ws = _WS()
    _send(_handler(session), ws, "sao làm lâu vậy")
    reply = ws.sent[-1]
    assert reply["type"] == "lead_note_reply"
    assert reply["data"]["lead"] == "CTO" and reply["data"]["kind"] == KIND_STATUS and reply["data"]["note_id"] == "n1"
    assert ws.notes == ["sao làm lâu vậy"]
    assert not get_run_inbox(gs).has_pending()


def test_handler_queues_directive_for_the_lead():
    session, gs = _live_session()
    ws = _WS()
    _send(_handler(session), ws, "thêm nút đăng nhập vào giao diện")
    assert ws.sent[-1]["data"]["kind"] == KIND_DIRECTIVE
    assert get_run_inbox(gs).has_pending()
    # the lead picking it up is reported over the socket
    get_run_inbox(gs).take_for_lead("CTO")
    assert ws.sent[-1] == {"type": "interject_applied", "data": {"note_id": "n1", "node": "CTO"}}


def test_handler_rejects_when_no_run_or_empty():
    ws = _WS()
    idle = SimpleNamespace(executor=None, graph=None, cancel_event=SimpleNamespace(is_set=lambda: False), waiting_for_input=False)
    _send(_handler(idle), ws, "hello there")
    error = ws.sent[-1]["data"]
    assert error["code"] == "not_running" and error["note_id"] == "n1" and error["fatal"] is False
    _send(_handler(idle), ws, "   ")
    assert ws.sent[-1]["data"]["code"] == "empty_input"
