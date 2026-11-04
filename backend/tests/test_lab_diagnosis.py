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
    findings = diagnose_run(run, "Chào bạn")
    assert {"over_budget", "loop", "overkill", "quality"} <= {f["code"] for f in findings}
    assert {f.get("kind") for f in findings if f["code"] == "over_budget"} == {"time", "tokens"}


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


# ---- accuracy regressions (doubt review 2026-11-04) -------------------------------------------------------------

from datetime import timezone

from agentdev.api.services.lab_diagnosis import compare_baseline, over_budget, run_budget

LONG_PROMPT = "Xây dựng một ứng dụng quản lý công việc bằng Vue 3 và FastAPI, có đăng nhập, phân quyền, " \
              "lưu dữ liệu SQLite, viết test và hướng dẫn chạy chi tiết cho người mới bắt đầu."


def _codes(findings):
    return [f["code"] for f in findings]


def _with_budget(run, prompt):
    budget = run_budget(prompt)
    return {**run, "budget_seconds": budget["seconds"], "budget_tokens": budget["tokens"],
            "over_budget": over_budget(run, budget)}


def test_real_request_within_its_budget_is_not_slow_or_heavy():
    assert len(LONG_PROMPT) > 140
    run = _with_budget({"status": "passed", "seconds": 200, "tokens": 100_000, "agents": {"Dev": 1, "QA": 1},
                        "judge": {"pass": True, "judged_by": "ai"}}, LONG_PROMPT)
    assert diagnose_run(run, LONG_PROMPT) == []


def test_time_over_budget_is_reported_once():
    run = _with_budget({"status": "passed", "seconds": 400, "tokens": 1000, "agents": {"Dev": 1},
                        "judge": {"pass": True, "judged_by": "ai"}}, LONG_PROMPT)
    codes = _codes(diagnose_run(run, LONG_PROMPT))
    assert codes.count("over_budget") == 1


def test_cache_reads_do_not_make_a_greeting_heavy():
    start = datetime(2026, 1, 1, 10, 0, 0)
    # Claude CLI shape (claude_cli_provider.extract_token_usage): input includes cache reads.
    calls = [{"node_id": "Lead", "model_name": "sonnet", "input_tokens": 44_000, "output_tokens": 300,
              "total_tokens": 44_300, "timestamp": (start + timedelta(seconds=12)).isoformat(),
              "metadata": {"uncached_input_tokens": 1_500, "cache_creation_input_tokens": 2_500,
                           "cache_read_input_tokens": 40_000, "total_cost_usd": 0.02}}]
    run = _with_budget({"status": "passed", "seconds": 15, "tokens": 44_300, "agents": {"Lead": 1},
                        "timeline": node_timeline(calls, start), "judge": {"pass": True, "judged_by": "ai"}}, "Chào")
    assert run["over_budget"] is False
    assert diagnose_run(run, "Chào") == []


def test_codex_cached_input_is_also_discounted():
    start = datetime(2026, 1, 1, 10, 0, 0)
    calls = [{"node_id": "Dev", "total_tokens": 50_000, "timestamp": (start + timedelta(seconds=5)).isoformat(),
              "metadata": {"cached_input_tokens": 45_000}}]
    run = {"tokens": 50_000, "seconds": 5, "timeline": node_timeline(calls, start)}
    assert over_budget(run, run_budget("Chào")) is False


def test_timezone_aware_timestamp_does_not_crash_timeline():
    start = datetime(2026, 1, 1, 10, 0, 0)
    calls = [{"node_id": "A", "timestamp": datetime(2026, 1, 1, 10, 0, 5, tzinfo=timezone.utc).isoformat()}]
    assert node_timeline(calls, start)[0]["node"] == "A"


def test_parallel_branches_use_node_wall_time_when_available():
    start = datetime(2026, 1, 1, 10, 0, 0)
    # A and B run in parallel for ~60s; B finishes 1s after A, so the gap estimate gives B only 1s.
    calls = [{"node_id": "A", "total_tokens": 10, "timestamp": (start + timedelta(seconds=60)).isoformat()},
             {"node_id": "B", "total_tokens": 10, "timestamp": (start + timedelta(seconds=61)).isoformat()}]
    run = {"status": "passed", "seconds": 400, "tokens": 20, "agents": {"A": 1, "B": 1},
           "budget_seconds": 300, "budget_tokens": 150_000,
           "timeline": node_timeline(calls, start),
           "node_runs": [{"node": "A", "n": 1, "wall_ms": 60_000.0, "status": "ok", "start_ts": start.isoformat()},
                         {"node": "B", "n": 1, "wall_ms": 300_000.0, "status": "ok", "start_ts": start.isoformat()}]}
    slow = [f for f in diagnose_run(run, LONG_PROMPT) if f.get("kind") == "time"][0]
    assert "B (300s" in slow["detail"]


def test_model_calls_of_one_execution_are_not_a_loop():
    # node_execution_counts counts model calls (an API agent's tool loop), not node runs.
    run = {"status": "passed", "seconds": 30, "tokens": 100, "agents": {"Coder": 6},
           "node_runs": [{"node": "Coder", "n": 1, "wall_ms": 30_000.0, "status": "ok"}],
           "judge": {"pass": True, "judged_by": "ai"}}
    assert "loop" not in _codes(diagnose_run(run, LONG_PROMPT))
    run["node_runs"] = [{"node": "Coder", "n": i, "wall_ms": 1000.0, "status": "ok"} for i in (1, 2, 3, 4)]
    assert "loop" in _codes(diagnose_run(run, LONG_PROMPT))


def test_basic_grade_failure_is_not_blamed_on_roles():
    run = {"status": "failed", "seconds": 10, "tokens": 0, "agents": {}, "answer": "",
           "judge": {"pass": False, "score": 0, "reason": "AI judge unavailable: no account", "judged_by": "basic"}}
    findings = diagnose_run(run, "Chào")
    assert findings and findings[0]["code"] == "no_answer"
    assert "Giám khảo:" not in findings[0]["detail"]


def test_interrupted_run_is_not_a_workflow_bug():
    finding = diagnose_run({"status": "error", "error": "interrupted"}, "x")[0]
    assert finding["code"] == "interrupted" and finding["severity"] == "warn"


def test_budget_limit_error_points_to_run_limits():
    error = "Vượt giới hạn token: 210000 / 200000. Node tốn nhiều nhất: Dev. (Run budget exceeded: tokens 210000 / 200000. Top node: Dev.)"
    finding = diagnose_run({"status": "error", "error": error}, "x")[0]
    assert finding["code"] == "budget_limit" and "run_limits" in finding["fix"]


def test_brief_shows_the_run_a_finding_is_about():
    scenarios = [Scenario(prompt="Chào", name="S1"), Scenario(prompt="Hỏi", name="S2")]
    ok = {"scenario": 0, "repeat": 1, "status": "passed", "seconds": 5, "tokens": 10, "agents": {"A": 1}}
    slow = {"scenario": 1, "repeat": 1, "status": "passed", "seconds": 500, "tokens": 10, "agents": {"A": 1}}
    runs = [ok] * 5 + [slow]
    findings = [{**f, "scenario": 1, "repeat": 1} for f in diagnose_run(slow, "Hỏi")]
    brief = build_fix_brief("wf", runs, scenarios, findings, 1.0, 0.8)
    assert "Kịch bản: S2" in brief


def test_brief_survives_error_run_with_null_seconds():
    run = {"scenario": 0, "repeat": 1, "status": "error", "error": "boom", "seconds": None}
    brief = build_fix_brief("wf", [run], [Scenario(prompt="x")], diagnose_run(run, "x"), 0.0, 0.8)
    assert "Tổng: 0s" in brief


def test_regression_cost_is_compared_per_run():
    # Twice as many runs at the same per-run cost is not a cost regression.
    assert "cost_usd" not in compare_baseline({"cost_usd": 2.0, "done": 10}, {"cost_usd": 1.0, "done": 5})
    assert "cost_usd" in compare_baseline({"cost_usd": 2.0, "done": 5}, {"cost_usd": 1.0, "done": 5})


def test_huge_cached_loop_is_still_heavy():
    start = datetime(2026, 1, 1, 10, 0, 0)
    calls = [{"node_id": "Dev", "total_tokens": 101_000, "timestamp": (start + timedelta(seconds=i + 1)).isoformat(),
              "metadata": {"cache_read_input_tokens": 100_000}} for i in range(40)]
    run = {"status": "passed", "seconds": 60, "tokens": 40 * 101_000, "agents": {"Dev": 40},
           "timeline": node_timeline(calls, start), "judge": {"pass": True, "judged_by": "ai"}}
    assert over_budget(run, run_budget(LONG_PROMPT))
    assert any(f.get("kind") == "tokens" for f in diagnose_run(run, LONG_PROMPT))


def test_small_per_run_cost_regression_shows_real_numbers():
    from agentdev.api.services.lab_diagnosis import regression_finding
    flags = compare_baseline({"cost_usd": 0.06, "done": 10}, {"cost_usd": 0.04, "done": 10})
    assert "$0.0040/lượt → $0.0060/lượt" in regression_finding(flags)["detail"]


def test_interrupted_only_job_needs_no_fix_brief():
    run = {"scenario": 0, "repeat": 1, "status": "error", "error": "interrupted"}
    findings = [{**f, "scenario": 0, "repeat": 1} for f in diagnose_run(run, "x")]
    assert build_fix_brief("wf", [run], [Scenario(prompt="x")], findings, 0.0, 0.8) == ""
