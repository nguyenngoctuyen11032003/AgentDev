"""Resuming an interrupted run: checkpoint recording, "continue" intent, resume context, persistence."""

import pytest

from agentdev.api.services import run_checkpoint as rc
from agentdev.api.services.conversation_turns import NEW_MESSAGE_HEADER, compose_follow_up_prompt, make_turn
from agentdev.api.services.session_history import SessionHistoryStore
from agentdev.api.services.session_store import SessionStatus, WorkflowSessionStore
from agentdev.api.services.workflow_run_service import WorkflowRunService


@pytest.mark.parametrize(
    "text",
    ["tiếp tục", "Tiếp tục làm", "tiếp tục làm đi", "làm tiếp nhé", "Tiếp tục!", "tiep tuc", "continue", "Continue please",
     "go on", "keep going", "resume", "继续", "tiếp tục làm phần test"],
)
def test_resume_intent_detected(text):
    assert rc.is_resume_intent(text)


@pytest.mark.parametrize(
    "text",
    ["", "   ", "viết cho tôi một hàm sắp xếp", "hello", "ok", "đồng ý", "why did it stop", "go online and search for the news now",
     "tiếp theo bạn hãy giải thích kết quả này một cách thật chi tiết cho tôi nhé nhé nhé"],
)
def test_other_messages_are_not_resume(text):
    assert not rc.is_resume_intent(text)


def _entry(event, node, **details):
    return {"event_type": event, "node_id": node, "details": details}


def _recorder(saves=None):
    cp = rc.new_checkpoint("Phân tích dự án X", ["spec.pdf"])
    team = {"team": [{"member": "Dev", "task": "Viết API", "report": "API xong"}], "exchanges": []}
    return rc.RunCheckpointRecorder(cp, (saves.append if saves is not None else (lambda _c: None)), lambda: team)


def test_recorder_tracks_nodes_notes_and_team():
    saves = []
    rec = _recorder(saves)
    rec.on_log(_entry("NODE_START", "lead"))
    rec.on_log(_entry("NODE_START", "analyst"))
    rec.on_log(_entry("NODE_END", "analyst", output="Phát hiện 3 lỗi"))
    rec.on_log(_entry("MODEL_CALL", "lead", stage="after", output="Kết luận tạm: sửa lỗi auth trước"))
    rec.on_log(_entry("MODEL_CALL", "lead", stage="before", output="ignored"))
    rec.on_log(_entry("EDGE_PROCESS", "lead"))  # ignored event

    cp = rec.checkpoint
    assert cp["nodes"]["analyst"]["status"] == "done"
    assert cp["nodes"]["analyst"]["output"] == "Phát hiện 3 lỗi"
    assert cp["nodes"]["lead"]["status"] == "running"
    assert [n["text"] for n in cp["notes"]] == ["Kết luận tạm: sửa lỗi auth trước"]
    assert cp["team"][0]["member"] == "Dev"
    assert saves  # progress was saved


def test_recorder_never_raises():
    rec = rc.RunCheckpointRecorder(rc.new_checkpoint("x"), lambda _c: 1 / 0)
    rec.on_log(_entry("NODE_START", "n"))  # the save fails; the run must not


def test_finish_interrupted_marks_running_nodes_cut_off():
    rec = _recorder()
    rec.on_log(_entry("NODE_START", "lead"))
    rec.on_log(_entry("NODE_START", "dev"))
    rec.on_log(_entry("NODE_END", "dev", output="done"))
    cp = rec.finish(rc.STATE_INTERRUPTED, "User stopped")
    assert rc.is_interrupted(cp)
    assert cp["nodes"]["lead"]["status"] == "interrupted"
    assert cp["nodes"]["dev"]["status"] == "done"
    assert cp["reason"] == "User stopped"


def _interrupted():
    rec = _recorder()
    rec.on_log(_entry("NODE_START", "lead"))
    rec.on_log(_entry("NODE_START", "analyst"))
    rec.on_log(_entry("NODE_END", "analyst", output="Phát hiện 3 lỗi"))
    rec.on_log(_entry("MODEL_CALL", "lead", stage="after", output="Kết luận tạm: sửa auth trước"))
    return rec.finish(rc.STATE_INTERRUPTED, "Interrupted by a server restart")


def test_resume_note_summarises_done_and_cut_off_work():
    note = rc.build_resume_note(_interrupted(), resume_requested=True)
    assert "Phân tích dự án X" in note  # the original request
    assert "server restart" in note
    assert "analyst: Phát hiện 3 lỗi" in note  # finished step with its output
    assert "lead" in note.split("Cut off while running")[1].split("\n")[0]
    assert "Dev" in note and "API xong" in note  # team reports
    assert "Kết luận tạm" in note  # intermediate notes
    assert "do NOT start over" in note
    assert rc.RESUME_REQUESTED in note


def test_resume_note_when_message_is_not_continue():
    note = rc.build_resume_note(_interrupted(), resume_requested=False)
    assert rc.RESUME_NOT_REQUESTED in note and rc.RESUME_REQUESTED not in note


def test_resume_note_skips_team_when_asked_and_ignores_finished_runs():
    assert "Reports already received" not in rc.build_resume_note(_interrupted(), resume_requested=True, include_team=False)
    done = rc.RunCheckpointRecorder(rc.new_checkpoint("x"), lambda _c: None).finish(rc.STATE_COMPLETED)
    assert rc.build_resume_note(done, resume_requested=True) == ""
    assert rc.build_resume_note(None, resume_requested=True) == ""


def test_resume_note_is_bounded():
    cp = _interrupted()
    for i in range(40):
        cp["nodes"][f"n{i}"] = {"status": "done", "output": "x" * 5000}
    assert len(rc.build_resume_note(cp, resume_requested=True)) < rc.MAX_RESUME_CHARS + 800


def test_continue_keeps_original_request_and_done_nodes():
    first = _interrupted()
    second = rc.new_checkpoint("tiếp tục", previous=first)
    assert second["original_prompt"] == "Phân tích dự án X"
    assert second["nodes"]["analyst"]["carried"] is True
    assert "lead" not in second["nodes"]  # a cut-off node is redone, not carried
    note = rc.build_resume_note(rc.RunCheckpointRecorder(second, lambda _c: None).finish("interrupted", "again"),
                                resume_requested=True)
    assert "Phân tích dự án X" in note and "analyst" in note


def test_prompt_with_resume_note_without_earlier_turns():
    note = rc.build_resume_note(_interrupted(), resume_requested=True)
    prompt = compose_follow_up_prompt([], "tiếp tục làm", note)
    assert prompt.index("[RESUME") < prompt.index(NEW_MESSAGE_HEADER) < prompt.index("tiếp tục làm")


def test_prompt_with_turns_and_resume_note_keeps_transcript():
    turns = [make_turn("Phân tích dự án X", "mới được một nửa")]
    turns[0]["status"] = "cancelled"
    note = rc.build_resume_note(_interrupted(), resume_requested=True)
    prompt = compose_follow_up_prompt(turns, "continue", note)
    assert "cancelled before it finished" in prompt
    assert prompt.index("--- Turn 1 ---") < prompt.index("[RESUME") < prompt.index(NEW_MESSAGE_HEADER)


def test_turn_resume_note_for_sessions_without_checkpoint():
    stopped = [{"user": "a", "answer": "b", "status": "cancelled"}]
    assert "interrupted" in rc.build_turn_resume_note(stopped)
    assert rc.build_turn_resume_note([{"user": "a", "answer": "b", "status": "completed"}]) == ""
    assert rc.build_turn_resume_note([]) == ""


class _Session:
    def __init__(self, turns=(), prior=None):
        self.turns = list(turns)
        self.prior_checkpoint = prior


def test_service_resume_note_dispatch():
    cp = _interrupted()
    assert rc.RESUME_REQUESTED in WorkflowRunService._resume_note(_Session(prior=cp), "tiếp tục")
    assert rc.RESUME_NOT_REQUESTED in WorkflowRunService._resume_note(_Session(prior=cp), "làm việc khác")
    legacy = _Session(turns=[{"user": "a", "answer": "", "status": "error"}])
    assert "interrupted" in WorkflowRunService._resume_note(legacy, "continue")
    assert WorkflowRunService._resume_note(legacy, "làm việc khác") == ""


def test_checkpoint_survives_restart_and_is_marked_interrupted(tmp_path):
    root = tmp_path / "sessions"
    store = WorkflowSessionStore(history=SessionHistoryStore(root=root))
    store.create_session(session_id="s1", yaml_file="t.yaml", task_prompt="Phân tích X")
    store.update_session_status("s1", SessionStatus.RUNNING)
    cp = rc.new_checkpoint("Phân tích X")
    store.begin_checkpoint("s1", cp)
    rec = rc.RunCheckpointRecorder(cp, lambda c: store.save_checkpoint("s1", c))
    rec.on_log(_entry("NODE_START", "lead"))
    rec.on_log(_entry("NODE_START", "analyst"))
    rec.on_log(_entry("NODE_END", "analyst", output="xong phần 1"))
    assert store.get_session_snapshot("s1")["resumable"] is False  # still running

    # The process dies; a new store loads the session from disk.
    fresh = WorkflowSessionStore(history=SessionHistoryStore(root=root))
    session = fresh.restore_session("s1")
    assert session.status == SessionStatus.CANCELLED
    assert rc.is_interrupted(session.checkpoint)
    assert session.checkpoint["reason"] == "Interrupted by a server restart"
    assert session.checkpoint["nodes"]["analyst"]["output"] == "xong phần 1"
    assert fresh.get_session_snapshot("s1")["resumable"] is True
    assert next(s for s in fresh.list_summaries() if s["session_id"] == "s1")["resumable"] is True

    # The "continue" launch hands the interrupted checkpoint to the new run and starts a fresh one.
    fresh.create_session(session_id="s1", yaml_file="t.yaml", task_prompt="tiếp tục")
    new_cp = rc.new_checkpoint("tiếp tục", previous=fresh.get_session("s1").checkpoint)
    fresh.begin_checkpoint("s1", new_cp)
    s = fresh.get_session("s1")
    assert rc.is_interrupted(s.prior_checkpoint)
    assert s.checkpoint["state"] == rc.STATE_RUNNING
    assert s.checkpoint["nodes"]["analyst"]["carried"] is True


def test_completed_run_is_not_resumable(tmp_path):
    store = WorkflowSessionStore(history=SessionHistoryStore(root=tmp_path / "sessions"))
    store.create_session(session_id="s2", yaml_file="t.yaml", task_prompt="x")
    cp = rc.new_checkpoint("x")
    store.begin_checkpoint("s2", cp)
    store.save_checkpoint("s2", rc.RunCheckpointRecorder(cp, lambda _c: None).finish(rc.STATE_COMPLETED), persist_meta=True)
    store.update_session_status("s2", SessionStatus.COMPLETED)
    assert store.get_session_snapshot("s2")["resumable"] is False


def test_resume_note_is_compact():
    from agentdev.api.services.run_checkpoint import MAX_RESUME_CHARS, build_resume_note

    cp = {
        "state": "interrupted",
        "original_prompt": "big job",
        "nodes": {f"n{i}": {"status": "done", "output": "line one\n" + "z" * 5000} for i in range(30)},
        "team": [{"member": f"m{i}", "task": "t" * 500, "report": "r" * 2000} for i in range(8)],
    }
    note = build_resume_note(cp, resume_requested=True)
    assert len(note) < MAX_RESUME_CHARS + 600
    assert "n29: line one" in note or "n29" in note
