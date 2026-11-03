"""One-time fix: sessions saved with a greeting title ("chào bạn") get titled by their first real request."""

import json

from agentdev.api.services.session_history import RETITLE_MARKER, SessionHistoryStore
from agentdev.api.services.session_store import WorkflowSession, WorkflowSessionStore
from agentdev.runtime.node.agent.team import is_small_talk


def _save(root, session_id, title, user_texts, *, custom=False, turns_only=False):
    folder = root / session_id
    folder.mkdir(parents=True)
    meta = {"session_id": session_id, "title": title, "status": "completed", "updated_at": 1.0, "message_count": 3}
    if custom:
        meta["title_custom"] = True
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    if turns_only:
        turns = [{"user": text, "answer": "..."} for text in user_texts]
        (folder / "turns.json").write_text(json.dumps({"turns": turns}, ensure_ascii=False), encoding="utf-8")
        return
    lines = []
    for text in user_texts:
        lines.append(json.dumps({"type": "user_message", "data": {"text": text}}))
        lines.append(json.dumps({"type": "log", "data": "hello"}))
    (folder / "messages.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _meta(root, session_id):
    return json.loads((root / session_id / "meta.json").read_text(encoding="utf-8"))


def test_greeting_title_takes_first_real_request(tmp_path):
    _save(tmp_path, "s1", "chào bạn", ["chào bạn", "cảm ơn nhé", "Làm trang HTML đồng hồ số\nchi tiết thêm", "ok"])
    store = WorkflowSessionStore(SessionHistoryStore(tmp_path))

    titles = {item["session_id"]: item["title"] for item in store.list_summaries()}

    assert titles["s1"] == "Làm trang HTML đồng hồ số"
    meta = _meta(tmp_path, "s1")
    assert meta["title"] == "Làm trang HTML đồng hồ số" and "title_custom" not in meta
    assert meta["message_count"] == 3  # nothing but the title changes


def test_turns_file_is_used_when_there_is_no_message_log(tmp_path):
    _save(tmp_path, "s1", "hi", ["hi", "Fix the login bug"], turns_only=True)
    WorkflowSessionStore(SessionHistoryStore(tmp_path)).list_summaries()
    assert _meta(tmp_path, "s1")["title"] == "Fix the login bug"


def test_custom_title_and_greetings_only_and_real_titles_are_kept(tmp_path):
    _save(tmp_path, "custom", "chào bạn", ["chào bạn", "Viết test đăng nhập"], custom=True)
    _save(tmp_path, "greet", "xin chào", ["xin chào", "cảm ơn!"])
    _save(tmp_path, "real", "Viết test đăng nhập", ["Viết test đăng nhập", "Thêm 1 test nữa"])

    WorkflowSessionStore(SessionHistoryStore(tmp_path)).list_summaries()

    assert _meta(tmp_path, "custom")["title"] == "chào bạn"
    assert _meta(tmp_path, "greet")["title"] == "xin chào"
    assert _meta(tmp_path, "real")["title"] == "Viết test đăng nhập"


def test_corrupt_folders_are_skipped(tmp_path):
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "meta.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "nomsgs").mkdir()
    (tmp_path / "nomsgs" / "meta.json").write_text(json.dumps({"session_id": "nomsgs", "title": "hi"}), encoding="utf-8")
    (tmp_path / "stray.txt").write_text("x", encoding="utf-8")
    _save(tmp_path, "s1", "hello", ["hello", "garbage line follows", "Build a todo app"])
    with open(tmp_path / "s1" / "messages.jsonl", "a", encoding="utf-8") as handle:
        handle.write("{broken\n[1, 2]\n")

    changed = SessionHistoryStore(tmp_path).retitle_small_talk_sessions(is_small_talk)

    assert changed == {"s1": "garbage line follows"}
    assert _meta(tmp_path, "nomsgs")["title"] == "hi"


def test_runs_once_per_folder(tmp_path):
    _save(tmp_path, "s1", "chào bạn", ["chào bạn", "Làm web landing"])
    history = SessionHistoryStore(tmp_path)
    assert history.retitle_small_talk_sessions(is_small_talk) == {"s1": "Làm web landing"}
    assert (tmp_path / RETITLE_MARKER).is_file()

    # A session saved later with a greeting title is left to the live rule: no rescan
    _save(tmp_path, "s2", "chào bạn", ["chào bạn", "Làm web khác"])
    assert history.retitle_small_talk_sessions(is_small_talk) == {}
    assert SessionHistoryStore(tmp_path).retitle_small_talk_sessions(is_small_talk) == {}
    assert _meta(tmp_path, "s2")["title"] == "chào bạn"
    assert _meta(tmp_path, "s1")["title"] == "Làm web landing"


def test_store_scans_only_on_first_listing_and_updates_live_copy(tmp_path, monkeypatch):
    _save(tmp_path, "s1", "chào bạn", ["chào bạn", "Làm web landing"])
    history = SessionHistoryStore(tmp_path)
    store = WorkflowSessionStore(history)
    store._sessions["s1"] = WorkflowSession(session_id="s1", yaml_file="team.yaml", task_prompt="", title="chào bạn")
    calls = []
    original = history.retitle_small_talk_sessions
    monkeypatch.setattr(history, "retitle_small_talk_sessions", lambda fn: calls.append(1) or original(fn))

    store.list_summaries()
    store.list_summaries()

    assert len(calls) == 1
    assert store._sessions["s1"].title == "Làm web landing"
    assert {item["session_id"]: item["title"] for item in store.list_summaries()}["s1"] == "Làm web landing"
