"""Lab findings name the layer that caused them (workflow / platform / environment / scenario), and only workflow
findings ask the workflow assistant for a fix."""

from agentdev.api.services.lab_diagnosis import (
    build_environment_hints,
    build_fix_brief,
    build_platform_report,
    classify_exception,
    diagnose_job,
    diagnose_run,
    layer_counts,
)
from agentdev.api.services.workflow_lab import Scenario


def _layers(findings):
    return {f["code"]: f["layer"] for f in findings}


# --- error kinds from exception classes (structured, no text matching) ---

def test_exception_classes_give_error_kinds():
    from agentdev.api.services.workflow_lab import LabRunTimeoutError
    from agentdev.runtime.node.agent.account_fallback import QuotaExceededError
    from agentdev.runtime.node.agent.providers._cli_common import CliProviderError, CliTimeoutError
    from agentdev.runtime.node.executor.agent_executor import ModelCallError
    from agentdev.utils.exceptions import WorkflowExecutionError
    from agentdev.utils.token_tracker import BudgetExceededError

    assert classify_exception(LabRunTimeoutError("Run stopped after 10 minutes")) == "timeout"
    assert classify_exception(BudgetExceededError("Vượt giới hạn token")) == "budget_limit"
    assert classify_exception(QuotaExceededError("usage limit reached")) == "quota"
    assert classify_exception(CliProviderError("claude CLI is not logged in")) == "cli"
    assert classify_exception(CliTimeoutError("no answer")) == "provider_timeout"
    try:
        try:
            raise RuntimeError("HTTP 429 Too Many Requests")
        except RuntimeError as inner:
            raise ModelCallError("Agent 'A' could not get an answer") from inner
    except ModelCallError as exc:
        assert classify_exception(exc) == "model_call"
    loop = WorkflowExecutionError("Vòng lặp ... safety limit", details={"kind": "loop_limit"})
    assert classify_exception(loop) == "loop_limit"
    assert classify_exception(WorkflowExecutionError("Edge A->B is missing a condition manager")) == "workflow_error"
    assert classify_exception(OSError("disk full")) == "os_error"


def test_python_bug_anywhere_in_the_chain_is_an_engine_exception():
    from agentdev.runtime.node.executor.agent_executor import ModelCallError

    try:
        try:
            None.text  # noqa: B018 - a provider bug
        except AttributeError as inner:
            raise ModelCallError("Agent 'A' could not get an answer") from inner
    except ModelCallError as exc:
        assert classify_exception(exc) == "engine_exception"
    assert classify_exception(KeyError("node_runs")) == "engine_exception"


# --- layers of findings ---

def test_rate_limit_after_retries_is_environment_not_timeout():
    run = {"status": "error", "error": "Agent 'Writer' stopped after 3 retries: 429 Too Many Requests"}
    findings = diagnose_run(run, "x")
    assert findings[0]["code"] != "timeout"
    assert findings[0]["layer"] == "environment"


def test_structured_error_kind_wins_over_the_text():
    # The text looks like the Lab's loop timeout, but the run says it was a model call failure.
    run = {"status": "error", "error_kind": "model_call", "error": "Run stopped after 2 minutes waiting"}
    finding = diagnose_run(run, "x")[0]
    assert finding["layer"] == "environment" and finding["code"] != "timeout"


def test_each_error_kind_has_its_layer():
    expected = {
        "timeout": "workflow", "loop_limit": "workflow", "budget_limit": "workflow", "workflow_error": "workflow",
        "quota": "environment", "cli": "environment", "provider_timeout": "environment", "model_call": "environment",
        "os_error": "environment", "engine_exception": "platform", "unknown": "platform",
    }
    for kind, layer in expected.items():
        finding = diagnose_run({"status": "error", "error_kind": kind, "error": "boom"}, "x")[0]
        assert finding["layer"] == layer, kind
        assert finding.get("error_kind") == kind


def test_old_jobs_without_error_kind_fall_back_to_the_text_table():
    cases = {
        "Run stopped after 10 minutes without finishing: the workflow is probably looping": "workflow",
        "Vượt giới hạn token: 9 / 5. (Run budget exceeded: tokens 9 / 5.)": "workflow",
        "claude CLI is not logged in. Run `claude login`.": "environment",
        "Error code: 429 - rate_limit_error": "environment",
        "You've hit your usage limit": "environment",
        "Traceback (most recent call last): AttributeError: 'NoneType' object has no attribute 'x'": "platform",
    }
    for error, layer in cases.items():
        assert diagnose_run({"status": "error", "error": error}, "x")[0]["layer"] == layer, error


def test_interrupted_is_still_dropped_from_the_brief():
    run = {"scenario": 0, "repeat": 1, "status": "error", "error": "interrupted"}
    findings = diagnose_run(run, "x")
    assert findings[0]["code"] == "interrupted"
    assert build_fix_brief("wf", [run], [Scenario(prompt="x")], findings, 0.0, 0.8) == ""
    assert layer_counts(findings) == {"workflow": 0, "platform": 0, "environment": 0, "scenario": 0}


def test_workflow_findings_are_workflow():
    run = {"status": "failed", "seconds": 300, "tokens": 70000,
           "agents": {"Writer": 2, "Reviewer": 2, "Director": 4, "QA": 2, "Archivist": 1},
           "judge": {"pass": False, "reason": "Sai ngôn ngữ", "judged_by": "ai"}}
    layers = _layers(diagnose_run(run, "Chào bạn"))
    assert layers["loop"] == layers["overkill"] == layers["quality"] == layers["over_budget"] == "workflow"


def test_slow_run_because_of_retries_is_not_a_workflow_problem():
    run = {"status": "error", "error_kind": "model_call", "error": "429", "seconds": 900}
    findings = diagnose_run(run, "Chào")
    assert {f["layer"] for f in findings} == {"environment"}


def test_tool_platform_errors_from_structured_evidence():
    run = {"status": "failed", "judge": {"pass": False, "reason": "thiếu file", "judged_by": "ai"},
           "evidence": [
               {"node": "Coder", "tool": "deploy_app", "ok": False, "error_code": "TOOL_NOT_FOUND"},
               {"node": "Coder", "tool": "run_shell", "ok": False, "exit_code": 1},  # normal work, not platform
           ]}
    findings = diagnose_run(run, "Viết app")
    platform = [f for f in findings if f["layer"] == "platform"]
    assert len(platform) == 1 and platform[0]["code"] == "tool_error" and "deploy_app" in platform[0]["detail"]
    run["evidence"] = [{"node": "Coder", "tool": "read_file", "ok": False, "exception_type": "FileNotFoundError"}]
    assert not [f for f in diagnose_run(run, "Viết app") if f["layer"] == "platform"]
    run["evidence"] = [{"node": "Coder", "tool": "read_file", "ok": False, "exception_type": "AttributeError"}]
    assert [f for f in diagnose_run(run, "Viết app") if f["layer"] == "platform"]


def test_flaky_judge_and_vague_criteria_are_scenario_layer():
    runs = [
        {"scenario": 0, "repeat": 1, "status": "passed", "judge": {"pass": True, "judged_by": "ai"}},
        {"scenario": 0, "repeat": 2, "status": "failed", "judge": {"pass": False, "reason": "chưa đủ", "judged_by": "ai"}},
        {"scenario": 1, "repeat": 1, "status": "passed", "judge": {"pass": True, "judged_by": "ai"}},
    ]
    findings = diagnose_job(runs, {0: "Viết thơ", 1: "Chào"}, {0: "Một bài thơ tiếng Việt có vần, 4 câu", 1: "tốt"})
    by_code = {}
    for f in findings:
        by_code.setdefault(f["code"], []).append(f)
    assert by_code["judge_flaky"][0]["layer"] == "scenario" and by_code["judge_flaky"][0]["scenario"] == 0
    assert all(f["layer"] == "scenario" for f in by_code["quality"])  # the flaky scenario's failure
    assert by_code["criteria_vague"][0]["scenario"] == 1
    missing = diagnose_job([runs[2]], {1: "Chào"}, {1: ""})
    assert [f["code"] for f in missing] == ["criteria_missing"] and missing[0]["layer"] == "scenario"


def test_error_runs_do_not_make_a_scenario_flaky():
    runs = [
        {"scenario": 0, "repeat": 1, "status": "passed", "judge": {"pass": True, "judged_by": "ai"}},
        {"scenario": 0, "repeat": 2, "status": "error", "error_kind": "model_call", "error": "429"},
    ]
    codes = {f["code"] for f in diagnose_job(runs, {0: "Viết thơ"}, {0: "Một bài thơ tiếng Việt có vần, 4 câu"})}
    assert "judge_flaky" not in codes


# --- the fix brief by layer (acceptance a, b, c) ---

SCENARIOS = [Scenario(prompt="Viết bài thơ", criteria="Một bài thơ tiếng Việt có vần, 4 câu", name="Thơ")]


def _brief(runs):
    findings = diagnose_job(runs, {0: SCENARIOS[0].prompt}, {0: SCENARIOS[0].criteria})
    return findings, build_fix_brief("wf", runs, SCENARIOS, findings, 0.0, 0.8)


def test_a_rate_limit_only_job_asks_for_no_workflow_fix():
    runs = [{"scenario": 0, "repeat": 1, "status": "error", "error_kind": "model_call",
             "error": "Agent 'Writer' stopped after 3 retries: 429 Too Many Requests"}]
    findings, brief = _brief(runs)
    assert brief == ""
    hints = build_environment_hints(findings)
    assert hints and hints[0]["code"] == "error" and "429" in hints[0]["detail"]
    assert build_platform_report("wf", runs, SCENARIOS, findings) == ""


def test_b_loop_job_keeps_the_workflow_brief():
    runs = [{"scenario": 0, "repeat": 1, "status": "failed", "seconds": 50, "tokens": 1000,
             "agents": {"Writer": 5, "Reviewer": 5},
             "node_runs": [{"node": "Writer", "wall_ms": 1000}] * 5 + [{"node": "Reviewer", "wall_ms": 1000}] * 5,
             "judge": {"pass": False, "reason": "chưa xong", "judged_by": "ai"}}]
    findings, brief = _brief(runs)
    assert "[loop]" in brief and "nguyên nhân gốc trong quy trình" in brief and "loop_counter" in brief
    assert "Lỗi môi trường" not in brief and "Nghi lỗi nền tảng" not in brief


def test_c_platform_and_workflow_job_asks_only_for_the_workflow_part():
    runs = [
        {"scenario": 0, "repeat": 1, "status": "failed", "seconds": 50, "tokens": 1000,
         "agents": {"Writer": 5}, "node_runs": [{"node": "Writer", "wall_ms": 1000}] * 5,
         "judge": {"pass": False, "reason": "chưa xong", "judged_by": "ai"}},
        {"scenario": 0, "repeat": 2, "status": "error", "error_kind": "engine_exception",
         "error": "'NoneType' object has no attribute 'text'",
         "evidence": [{"node": "Writer", "tool": "save_file", "ok": False, "error_code": "TOOL_NOT_FOUND"}],
         "node_runs": [{"node": "Writer", "wall_ms": 1000}]},
    ]
    findings, brief = _brief(runs)
    fix_part = brief.split("### Nghi lỗi nền tảng")[0]
    assert "[loop]" in fix_part
    assert "NoneType" not in fix_part and "TOOL_NOT_FOUND" not in fix_part
    assert "### Nghi lỗi nền tảng" in brief and "không sửa quy trình" in brief.split("### Nghi lỗi nền tảng")[1]
    report = build_platform_report("wf", runs, SCENARIOS, findings)
    assert "NoneType" in report and "save_file" in report and "Writer" in report
    assert "Thơ" in report and "Cách tái hiện" in report
    assert layer_counts(findings)["platform"] >= 2 and layer_counts(findings)["workflow"] >= 1


def test_brief_says_no_fix_needed_is_not_produced_for_scenario_only():
    runs = [
        {"scenario": 0, "repeat": 1, "status": "passed", "judge": {"pass": True, "judged_by": "ai"}},
        {"scenario": 0, "repeat": 2, "status": "failed", "judge": {"pass": False, "reason": "x", "judged_by": "ai"}},
    ]
    findings, brief = _brief(runs)
    assert brief == "" and layer_counts(findings)["scenario"] >= 1
