"""Follow-up messages in the same session: the start node (team lead) sees earlier turns."""

import asyncio
import json
from types import SimpleNamespace

import pytest
import yaml

from agentdev.api.services import workflow_run_service as run_service_module
from agentdev.api.services.attachment_service import AttachmentService
from agentdev.api.services.conversation_turns import (
    HEADER,
    NEW_MESSAGE_HEADER,
    build_transcript,
    compose_follow_up_prompt,
    make_turn,
)
from agentdev.api.services.session_execution import SessionExecutionController
from agentdev.api.services.session_history import SessionHistoryStore
from agentdev.api.services.session_store import SessionStatus, WorkflowSessionStore
from agentdev.api.services.workflow_run_service import WorkflowRunService
from agentdev.entity.messages import Message, MessageRole, ToolCallPayload
from agentdev.runtime.node.agent import ModelResponse, ProviderRegistry
from agentdev.runtime.node.executor import agent_executor as agent_executor_module
from agentdev.utils.human_prompt import HumanPromptService, PromptResult


# ---------------------------------------------------------------- transcript


def test_no_history_leaves_prompt_untouched():
    assert compose_follow_up_prompt([], "hello") == "hello"
    assert build_transcript([{"user": "", "answer": ""}]) == ""


def test_transcript_lists_turns_then_new_message():
    turns = [make_turn("Build login", "Login done in app/auth.py", ["spec.pdf"])]
    text = compose_follow_up_prompt(turns, "Now add logout")
    assert HEADER in text
    assert "User: Build login" in text and "spec.pdf" in text
    assert "You answered: Login done in app/auth.py" in text
    assert text.endswith(f"{NEW_MESSAGE_HEADER}\nNow add logout")


def test_transcript_keeps_questions_answered_during_a_turn():
    turn = make_turn("Build a shop", "Shop built with Vue.", exchanges=[{"question": "Plan: React. Approve?", "answer": "ok, use Vue"}])
    text = compose_follow_up_prompt([turn], "add a cart")
    assert "You asked: Plan: React. Approve?\nUser replied: ok, use Vue\nYou answered: Shop built with Vue." in text
    # No exchanges: the stored turn keeps its original shape.
    assert "exchanges" not in make_turn("a", "b", exchanges=[])


def test_transcript_caps_turn_count_and_size():
    turns = [make_turn(f"ask {i}", f"answer {i}") for i in range(15)]
    text = build_transcript(turns, max_turns=10)
    assert "ask 4" not in text and "ask 5" in text and "ask 14" in text
    assert "(5 older turn(s) omitted)" in text

    big = [make_turn(f"q{i}", "x" * 3000) for i in range(10)]
    text = build_transcript(big, max_chars=7000)
    assert len(text) < 7500
    assert "q9" in text and "q0" not in text

    huge = build_transcript([make_turn("q", "y" * 50_000)], max_chars=1000)
    assert len(huge) < 1200


def test_long_answers_keep_start_and_end_and_latest_turn_gets_more_room():
    answer = "START " + "x" * 20_000 + " END"
    text = build_transcript([make_turn("old", answer), make_turn("new", answer)], max_chars=14_000)
    old, new = text.split("--- Turn 2 ---")
    assert "START" in old and "END" in old and "chars omitted" in old
    assert "START" in new and "END" in new
    assert 3_500 < len(old) < 4_500 and 7_500 < len(new) < 8_500


def test_questions_the_lead_asked_keep_a_whole_plan():
    plan = "Plan: " + "step. " * 350  # ~2100 chars
    text = build_transcript([make_turn("Build a shop", "ok", exchanges=[{"question": plan, "answer": "ok"}])])
    assert plan.strip() in text


def test_unfinished_turn_status_is_noted():
    cancelled = {**make_turn("Build it", "half done"), "status": "cancelled"}
    failed = {**make_turn("Build it", ""), "status": "error"}
    done = {**make_turn("Build it", "done"), "status": "completed"}
    assert "cancelled before it finished" in build_transcript([cancelled])
    assert "ended with an error" in build_transcript([failed])
    assert "before it finished" not in build_transcript([done])


def test_make_turn_files_delegations_under_team():
    exchanges = [
        {"question": "Approve?", "answer": "ok"},
        {"kind": "delegation", "member": "Dev", "task": "Build API", "report": "Built"},
    ]
    turn = make_turn("Build", "Done", exchanges=exchanges)
    assert turn["exchanges"] == [{"question": "Approve?", "answer": "ok"}]
    assert turn["team"] == [{"member": "Dev", "task": "Build API", "report": "Built"}]
    assert "team" not in make_turn("a", "b")


def test_team_digest_shown_for_the_last_two_turns_only():
    turns = [
        make_turn(f"ask {i}", f"answer {i}", team=[{"member": f"m{i}", "task": f"task {i}", "report": f"report {i}"}])
        for i in range(3)
    ]
    text = build_transcript(turns)
    assert "task 0" not in text and "- m1: task 1" in text and "- m2: task 2\n  Report: report 2" in text
    many = make_turn("big", "done", team=[{"member": "Dev", "task": "t" * 2000, "report": "r" * 9000}] * 8)
    assert len(build_transcript([many])) < 9_000


# ---------------------------------------------------------------- session store


def test_turns_survive_follow_up_and_restart(tmp_path):
    history = SessionHistoryStore(root=tmp_path / "sessions")
    store = WorkflowSessionStore(history=history)
    store.create_session(session_id="s1", yaml_file="team.yaml", task_prompt="Build login")
    store.add_turn("s1", make_turn("Build login", "done"))

    # A follow-up relaunch in the same session keeps turns and title.
    session = store.create_session(session_id="s1", yaml_file="team.yaml", task_prompt="Add logout")
    assert session.turns == [make_turn("Build login", "done")]
    assert session.title == "Build login"

    restarted = WorkflowSessionStore(history=SessionHistoryStore(root=tmp_path / "sessions"))
    assert restarted.restore_session("s1").turns == [make_turn("Build login", "done")]


def test_new_session_has_no_turns(tmp_path):
    store = WorkflowSessionStore(history=SessionHistoryStore(root=tmp_path / "sessions"))
    session = store.create_session(session_id="fresh", yaml_file="team.yaml", task_prompt="Hello there")
    assert session.turns == [] and session.title == "Hello there"


def test_greeting_title_is_replaced_by_the_first_real_request(tmp_path):
    store = WorkflowSessionStore(history=SessionHistoryStore(root=tmp_path / "sessions"))
    store.create_session(session_id="hi", yaml_file="team.yaml", task_prompt="chào bạn")
    store.add_turn("hi", make_turn("chào bạn", "Chào bạn!"))

    # Another greeting keeps it; the first real request names the conversation
    assert store.create_session(session_id="hi", yaml_file="team.yaml", task_prompt="cảm ơn nhé").title == "chào bạn"
    store.add_turn("hi", make_turn("cảm ơn nhé", "Không có gì"))
    long_request = "Làm luôn: tạo một trang HTML đơn giản hiển thị đồng hồ số, một file index.html. " + "x" * 80
    session = store.create_session(session_id="hi", yaml_file="team.yaml", task_prompt=f"\n  {long_request}\nchi tiết")
    assert session.title == long_request[:79].rstrip() + "…"
    store.add_turn("hi", make_turn(long_request, "done"))

    # From then on follow-ups keep it, like any other title
    assert store.create_session(session_id="hi", yaml_file="team.yaml", task_prompt="Thêm nút dừng").title == session.title
    restored = WorkflowSessionStore(history=SessionHistoryStore(root=tmp_path / "sessions"))
    assert next(m for m in restored.list_summaries() if m["session_id"] == "hi")["title"] == session.title


def test_greeting_title_the_user_chose_is_kept(tmp_path):
    history = SessionHistoryStore(root=tmp_path / "sessions")
    store = WorkflowSessionStore(history=history)
    store.create_session(session_id="hi", yaml_file="team.yaml", task_prompt="hello")
    store.add_turn("hi", make_turn("hello", "Hi!"))
    history.rename("hi", "hello")  # typed by the user in the sidebar
    session = store.create_session(session_id="hi", yaml_file="team.yaml", task_prompt="Build a login page")
    assert session.title == "hello"


# ---------------------------------------------------------------- end to end


class ScriptedProvider:
    scripts = {}
    seen = {}

    def __init__(self, config):
        self.config = config

    def create_client(self):
        return None

    def call_model(self, client, conversation, timeline, tool_specs=None, **kwargs):
        node_id = self.config.node_id
        self.seen.setdefault(node_id, []).append([m.text_content() for m in conversation])
        step = self.scripts[node_id].pop(0)
        if isinstance(step, tuple):
            name, args = step
            call = ToolCallPayload(id=f"call-{len(self.seen[node_id])}", function_name=name, arguments=json.dumps(args))
            return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content="", tool_calls=[call]))
        return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=step))

    def extract_token_usage(self, response):
        return None


class FakeSocketManager:
    def __init__(self):
        self.sent = []

    async def send_message(self, session_id, message):
        self.sent.append(message)

    def send_message_sync(self, session_id, message):
        self.sent.append(message)

    def record_user_message(self, session_id, text, attachment_ids=None):
        pass


def _agent(node_id, role, team=None):
    config = {"connection": "fake", "provider": "fake", "name": "fake-model", "role": role}
    if team:
        config["team"] = team
    return {"id": node_id, "type": "agent", "description": role, "config": config}


@pytest.fixture()
def run_service(tmp_path, monkeypatch):
    yaml_dir = tmp_path / "yaml"
    yaml_dir.mkdir()
    definition = {
        "version": "0.4.0",
        "graph": {
            "id": "team_chat",
            "start": ["CTO"],
            "end": ["CTO"],
            "nodes": [_agent("CTO", "You are the CTO.", team={"enabled": True}), _agent("Dev", "Developer")],
            "edges": [],
        },
    }
    (yaml_dir / "team.yaml").write_text(yaml.safe_dump(definition), encoding="utf-8")
    monkeypatch.setattr(run_service_module, "YAML_DIR", yaml_dir)

    creds = SimpleNamespace(provider="fake", vendor="fake", token="", base_url="")
    monkeypatch.setattr(agent_executor_module, "resolve_connection", lambda _id: creds)
    monkeypatch.setattr(ProviderRegistry, "get_provider", lambda _name: ScriptedProvider)
    monkeypatch.setattr(HumanPromptService, "request", lambda self, *a, **k: PromptResult(text="ok"))
    ScriptedProvider.seen = {}

    store = WorkflowSessionStore(history=SessionHistoryStore(root=tmp_path / "sessions"))
    controller = SessionExecutionController(store)
    service = WorkflowRunService(store, controller, AttachmentService())
    return service, store


def _run(service, prompt, session_id="chat-1"):
    socket = FakeSocketManager()
    asyncio.run(service.start_workflow(session_id, "team.yaml", prompt, socket))
    assert [m["type"] for m in socket.sent if m["type"] in ("workflow_completed", "error")] == ["workflow_completed"], socket.sent
    return socket


def test_follow_up_gives_the_lead_earlier_turns_but_not_members(run_service):
    service, store = run_service
    ScriptedProvider.scripts = {
        "CTO": [
            ("delegate_task", {"member": "Dev", "task": "Implement /login"}),
            "Login API is done in app/auth.py.",
            ("delegate_task", {"member": "Dev", "task": "Add a logout button"}),
            "Logout button added.",
        ],
        "Dev": ["Implemented /login", "Added logout"],
    }

    _run(service, "Build a login API")
    first_cto = ScriptedProvider.seen["CTO"][0]
    assert not any(HEADER in text for text in first_cto)
    (first_turn,) = store.get_session("chat-1").turns
    assert (first_turn["user"], first_turn["answer"], first_turn["status"]) == (
        "Build a login API", "Login API is done in app/auth.py.", "completed"
    )
    # The turn remembers what the team did.
    assert first_turn["team"] == [{"member": "Dev", "task": "Implement /login", "report": "Implemented /login"}]

    _run(service, "ok, now also add a logout button")
    follow_up = "\n".join(ScriptedProvider.seen["CTO"][2])
    assert "User: Build a login API" in follow_up
    assert "You answered: Login API is done in app/auth.py." in follow_up
    assert f"{NEW_MESSAGE_HEADER}\nok, now also add a logout button" in follow_up
    assert "What the team did:\n- Dev: Implement /login\n  Report: Implemented /login" in follow_up

    # Members are briefed by the lead only; the transcript is not forwarded to them,
    # but a member's own report from the earlier turn is repeated in its brief.
    dev_brief = "\n".join(ScriptedProvider.seen["Dev"][1])
    assert HEADER not in dev_brief and "Add a logout button" in dev_brief
    assert "from earlier messages of this conversation" in dev_brief and "Implemented /login" in dev_brief
    assert "documents (UI text, docs, messages) in English" in dev_brief

    session = store.get_session("chat-1")
    assert len(session.turns) == 2 and session.status == SessionStatus.COMPLETED
    assert session.title == "Build a login API"


def test_run_in_progress_rejects_a_second_start(run_service):
    service, store = run_service
    store.create_session(session_id="busy", yaml_file="team.yaml", task_prompt="x")
    store.get_session("busy").executor = object()
    socket = FakeSocketManager()
    asyncio.run(service.start_workflow("busy", "team.yaml", "again", socket))
    assert socket.sent[-1]["type"] == "error" and "already in progress" in socket.sent[-1]["data"]["message"]
    assert socket.sent[-1]["data"]["code"] == "run_in_progress"
    assert store.get_session("busy").task_prompt == "x"


def test_execute_endpoint_returns_409_when_a_run_is_in_progress(run_service, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from agentdev.api import state
    from agentdev.api.routes import execute
    from agentdev.api.services.websocket_manager import WebSocketManager

    service, store = run_service
    manager = WebSocketManager(session_store=store, workflow_run_service=service)
    manager.active_connections["busy3"] = object()
    store.create_session(session_id="busy3", yaml_file="team.yaml", task_prompt="x")
    store.get_session("busy3").executor = object()
    monkeypatch.setattr(state, "websocket_manager", manager)
    app = FastAPI()
    app.include_router(execute.router)
    response = TestClient(app).post(
        "/api/workflow/execute",
        json={"session_id": "busy3", "yaml_file": "team.yaml", "task_prompt": "again"},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "A run is already in progress in this session", "code": "run_in_progress"}


def _patch_run(monkeypatch, run, final_output):
    executor_cls = run_service_module.WebSocketGraphExecutor
    monkeypatch.setattr(executor_cls, "execute_graph_async", run)
    monkeypatch.setattr(executor_cls, "get_final_output", lambda self: final_output)


def test_cancelled_run_saves_turn_with_status_and_partial_answer(run_service, monkeypatch):
    service, store = run_service

    async def cancel_midway(self, task_input):
        session = store.get_session("cx")
        session.cancel_reason = "User requested cancellation"
        session.cancel_event.set()

    _patch_run(monkeypatch, cancel_midway, "half done")
    socket = FakeSocketManager()
    asyncio.run(service.start_workflow("cx", "team.yaml", "Build a login API", socket))
    assert socket.sent[-1]["type"] == "workflow_cancelled"
    turns = store.get_session("cx").turns
    assert turns == [{**make_turn("Build a login API", "half done"), "status": "cancelled"}]
    # A follow-up like "continue" gets that context.
    assert "User: Build a login API" in compose_follow_up_prompt(turns, "continue")


def test_failed_run_saves_turn_with_error_status(run_service, monkeypatch):
    service, store = run_service

    async def boom(self, task_input):
        raise RuntimeError("provider crashed")

    _patch_run(monkeypatch, boom, "")
    socket = FakeSocketManager()
    asyncio.run(service.start_workflow("ex", "team.yaml", "Build a login API", socket))
    assert socket.sent[-1]["type"] == "error"
    assert store.get_session("ex").turns == [{**make_turn("Build a login API", ""), "status": "error"}]


def test_pinned_brief_survives_many_turns():
    from agentdev.api.services.conversation_turns import MAX_BRIEF_CHARS

    turns = [make_turn("BUILD SHOP SCOPE-X", "ok")]
    turns.append({**make_turn("go", "PLAN-Y: step one"), "kind": "plan"})
    turns.append(make_turn("ok", "done", exchanges=[{"question": "DB?", "answer": "use postgres-Z"}]))
    turns += [make_turn(f"msg {i}", f"ans {i}") for i in range(12)]
    text = compose_follow_up_prompt(turns, "next")
    assert "PROJECT BRIEF" in text and "BUILD SHOP SCOPE-X" in text
    assert "PLAN-Y" in text and "postgres-Z" in text
    assert text.index("PROJECT BRIEF") < text.index("Earlier in this conversation")
    assert "msg 0" not in text.split("Earlier in this conversation")[1]
    from agentdev.api.services.conversation_turns import build_project_brief

    assert len(build_project_brief([make_turn("x" * 50_000, "y")] * 3)) <= MAX_BRIEF_CHARS


def test_files_digest_rendered_and_capped():
    files = {f"src/f{i}.py": i * 10 for i in range(60)}
    text = compose_follow_up_prompt([make_turn("hi", "hello")], "more", changed_files=files)
    assert "src/f59.py (590 bytes)" in text and "src/f0.py" not in text
    assert text.count("\n- src/") == 40 and "earlier file(s)" in text
    assert "src/" not in compose_follow_up_prompt([make_turn("hi", "hello")], "more")


def test_notes_taken_mid_run_reach_the_next_turn():
    turn = make_turn("Build a shop", "Shop built.", notes=["use Postgres, not SQLite", "  "])
    assert turn["notes"] == ["use Postgres, not SQLite"]
    text = compose_follow_up_prompt([turn], "add a cart")
    assert "User added while you worked: use Postgres, not SQLite" in text
    assert "notes" not in make_turn("a", "b")


def test_follow_up_keeps_changed_files(tmp_path):
    store = WorkflowSessionStore(history=SessionHistoryStore(root=tmp_path / "sessions"))
    first = store.create_session(session_id="cf", yaml_file="team.yaml", task_prompt="Build login")
    first.changed_files["app/auth.py"] = 120
    session = store.create_session(session_id="cf", yaml_file="team.yaml", task_prompt="Add logout")
    assert session.changed_files == {"app/auth.py": 120}
