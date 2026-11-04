"""Lab diagnosis: slow / loop / overkill findings and the fix brief."""

from datetime import datetime, timedelta

from agentdev.api.services.lab_diagnosis import build_fix_brief, diagnose_run, node_timeline, summarise_timeline
from agentdev.api.services.workflow_lab import Scenario


def test_timeline_uses_gaps_between_calls():
    start = datetime(2026, 1, 1, 10, 0, 0)
    calls = [
        {"node_id": "A", "timestamp": (start + timedelta(seconds=10)).isoformat(), "total_tokens": 5},
        {"node_id": "B", "timestamp": (start + timedelta(seconds=40)).isoformat(), "total_tokens": 7},
        {"node_id": "B", "timestamp": (start + timedelta(seconds=70)).isoformat(), "total_tokens": 7},
    ]
    top = summarise_timeline(node_timeline(calls, start))
    assert top[0]["node"] == "B" and top[0]["seconds"] == 60 and top[0]["calls"] == 2


def test_greeting_through_whole_line_is_flagged_overkill_and_slow():
    run = {"status": "failed", "seconds": 300, "tokens": 70000,
           "agents": {"Writer": 2, "Reviewer": 2, "Director": 4, "QA": 2, "Archivist": 1},
           "judge": {"pass": False, "reason": "Sai ngôn ngữ", "judged_by": "ai"},
           "timeline": [{"node": "Director", "seconds": 200, "tokens": 1, "model": "m"}]}
    codes = {f["code"] for f in diagnose_run(run, "Chào bạn")}
    assert {"slow", "loop", "overkill", "heavy", "quality"} <= codes


def test_timeout_error_points_to_loop_guards():
    run = {"status": "error", "error": "Run stopped after 10 minutes without finishing: the workflow is probably looping"}
    finding = diagnose_run(run, "x")[0]
    assert finding["code"] == "timeout" and "loop_counter" in finding["fix"]


def test_brief_is_empty_when_all_good_and_complete_when_failing():
    good = {"scenario": 0, "repeat": 1, "status": "passed", "seconds": 10, "tokens": 100, "agents": {"A": 1}}
    scenarios = [Scenario(prompt="Chào", criteria="ngắn", name="Chào hỏi")]
    assert build_fix_brief("wf", [good], scenarios, diagnose_run(good, "Chào"), 1.0, 0.8) == ""
    bad = {**good, "status": "failed", "judge": {"reason": "sai", "pass": False, "judged_by": "ai"}}
    brief = build_fix_brief("wf", [bad], scenarios, diagnose_run(bad, "Chào"), 0.0, 0.8)
    assert "Chào hỏi" in brief and "Tiêu chí đạt: ngắn" in brief and "Yêu cầu khi sửa" in brief
