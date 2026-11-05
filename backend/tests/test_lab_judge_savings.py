"""Lab judge: re-judge on resume, cheaper second looks, stable prompt prefix, smart clipping, judge cost."""

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentdev.api.services import workflow_lab
from agentdev.api.services.workflow_lab import LabRunner, Scenario
from agentdev.runtime.node.agent import account_fallback


@pytest.fixture(autouse=True)
def _lab_store(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow_lab, "_lab_dir", lambda: tmp_path / "lab_jobs")


def _wait(job):
    deadline = time.monotonic() + 20
    while job.status in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(0.02)
    return job.to_dict()


class _Account:
    def current(self):
        return SimpleNamespace(id="acc", label="Acc"), "mid"

    def switch(self, failed_id):
        return False


def _judge_with(monkeypatch, scores):
    """Fake judge call: replies with the next score; records (model, user)."""
    seen = []

    def fake(conn, model, user, system=""):
        seen.append((model, user))
        score = scores.pop(0) if scores else 9
        return json.dumps({"pass": score >= 7, "score": score, "reason": "r"})

    monkeypatch.setattr(workflow_lab, "_judge_call", fake)
    monkeypatch.setattr(account_fallback, "default_model_for", lambda conn: "strong")
    return seen


# ---------------------------------------------------------------------------- 1. resume re-judges


def test_resume_rejudges_unjudged_runs_without_rerunning_them(tmp_path):
    runner = LabRunner(store_dir=tmp_path / "store")
    yaml_path = tmp_path / "wf.yaml"
    yaml_path.write_text("x: 1", encoding="utf-8")

    def down(*a, **k):
        raise RuntimeError("judge down")

    answers = {"a": "Câu trả lời đầy đủ", "b": ""}
    job = runner.start(yaml_path, "wf.yaml", [Scenario("a", "c"), Scenario("b", "c")], 1,
                       run_once=lambda p, s, c: {"answer": answers[s.prompt], "questions": []}, judge=down)
    data = _wait(job)
    assert sorted(r["status"] for r in data["results"]) == ["failed", "unjudged"]
    first_id = next(r["run_id"] for r in data["results"] if r["status"] == "unjudged")
    assert data["resumable"] is True
    runner._jobs.pop(job.id)

    reruns, judged = [], []

    def run_once(path, scenario, cancel):
        reruns.append(scenario.prompt)
        return {"answer": "mới", "questions": []}

    def judge(prompt, criteria, answer, questions, **kwargs):
        judged.append(answer)
        return {"pass": True, "score": 9, "judged_by": "ai"}

    # The empty run b was a real fail (graded): nothing to re-run; a is only judged again.
    resumed = runner.resume(job.id, yaml_path, run_once=run_once, judge=judge)
    after = _wait(resumed)
    assert reruns == [] and judged == ["Câu trả lời đầy đủ"]
    run_a = next(r for r in after["results"] if r["scenario"] == 0)
    assert run_a["status"] == "passed" and run_a["run_id"] == first_id
    assert after["unjudged"] == 0 and after["pass_rate"] == 0.5


def test_resume_reruns_unjudged_run_that_has_no_answer(tmp_path):
    runner = LabRunner(store_dir=tmp_path / "store")
    yaml_path = tmp_path / "wf.yaml"
    yaml_path.write_text("x: 1", encoding="utf-8")
    job = runner.start(yaml_path, "wf.yaml", [Scenario("a", "c")], 1,
                       run_once=lambda *a: {"answer": "ok", "questions": []},
                       judge=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    _wait(job)
    job.results[0]["answer"] = ""  # e.g. a record whose answer was lost
    job.status = "cancelled"
    runner._save(job)
    runner._jobs.pop(job.id)
    reruns = []
    resumed = runner.resume(job.id, yaml_path,
                            run_once=lambda p, s, c: reruns.append(s.prompt) or {"answer": "ok", "questions": []},
                            judge=lambda *a, **k: {"pass": True, "score": 9, "judged_by": "ai"})
    assert _wait(resumed)["passed"] == 1 and reruns == ["a"]


# ---------------------------------------------------------------------------- 2a. second look only at 6-7


@pytest.mark.parametrize("first,calls", [(6, 2), (7, 2), (8, 1), (9, 1), (5, 1)])
def test_strong_rejudge_only_for_scores_6_and_7(monkeypatch, first, calls):
    seen = _judge_with(monkeypatch, [first, 9])
    workflow_lab._judge("p", "c", "answer", [], account=_Account())
    assert len(seen) == calls


# ---------------------------------------------------------------------------- 2b. stable prefix


def test_judge_prompt_keeps_scenario_part_as_a_stable_prefix(monkeypatch):
    seen = _judge_with(monkeypatch, [9, 9])
    workflow_lab._judge("Làm web", "có index.html", "answer one", [{"node": "Lead", "question": "ok?"}],
                        account=_Account())
    workflow_lab._judge("Làm web", "có index.html", "a different answer", [], account=_Account())
    first, second = seen[0][1], seen[1][1]
    prefix = workflow_lab._judge_prefix("Làm web", "có index.html")
    assert first.startswith(prefix) and second.startswith(prefix)
    assert "có index.html" in prefix and "answer" not in prefix


# ---------------------------------------------------------------------------- 2c. smart clipping


def test_clip_answer_keeps_head_tail_and_criteria_passages():
    filler = "\n\n".join(f"Đoạn đệm số {i} không liên quan gì cả." * 4 for i in range(400))
    key = "Tệp index.html đã được tạo và kiểm thử bằng npm test thành công."
    answer = "MỞ ĐẦU\n\n" + filler + "\n\n" + key + "\n\n" + filler + "\n\nKẾT THÚC"
    clipped = workflow_lab._clip_answer(answer, "Có index.html; chạy npm test")
    assert len(answer) > 50_000 and len(clipped) <= workflow_lab.JUDGE_ANSWER_CHARS + 200
    assert clipped.startswith("MỞ ĐẦU") and clipped.rstrip().endswith("KẾT THÚC")
    assert key in clipped
    assert "[… đã lược bớt" in clipped and "ký tự …]" in clipped
    short = "ngắn"
    assert workflow_lab._clip_answer(short, "x") == short


# ---------------------------------------------------------------------------- 2d. judge cost


def test_judge_cost_and_tokens_are_added_to_the_job(monkeypatch):
    def judge(prompt, criteria, answer, questions, **kwargs):
        return {"pass": True, "score": 9, "judged_by": "ai", "tokens": 1200, "cost_usd": 0.02}

    job = LabRunner().start(Path("x.yaml"), "x.yaml", [Scenario("a", "c"), Scenario("b", "c")], 1,
                            run_once=lambda *a: {"answer": "ok", "questions": [], "tokens": 100, "cost_usd": 0.1},
                            judge=judge)
    data = _wait(job)
    assert data["judge_cost_usd"] == 0.04 and data["judge_tokens"] == 2400
    assert data["cost_usd"] == pytest.approx(0.24) and data["total_tokens"] == 2600


def test_judge_records_usage_reported_by_the_account_call(monkeypatch):
    def fake(conn, model, user, system=""):
        workflow_lab._record_judge_usage(tokens=500, cost_usd=0.003)
        return '{"pass": true, "score": 9, "reason": "ok"}'

    monkeypatch.setattr(workflow_lab, "_judge_call", fake)
    verdict = workflow_lab._judge("p", "c", "answer", [], account=_Account())
    assert verdict["tokens"] == 500 and verdict["cost_usd"] == 0.003 and verdict["calls"] == 1


def test_judge_without_reported_cost_keeps_cost_zero(monkeypatch):
    def fake(conn, model, user, system=""):
        workflow_lab._record_judge_usage(tokens=300, cost_usd=None)
        return '{"pass": true, "score": 9, "reason": "ok"}'

    monkeypatch.setattr(workflow_lab, "_judge_call", fake)
    verdict = workflow_lab._judge("p", "c", "answer", [], account=_Account())
    assert verdict["tokens"] == 300 and verdict["cost_usd"] == 0.0


# ---------------------------------------------------------------------------- review fixes


def test_clip_answer_never_exceeds_the_limit_with_many_matching_lines():
    mid = "\n".join(("video" if i % 2 == 0 else "x" * 33) for i in range(4000))
    answer = "H" * 3000 + "\n" + mid + "\n" + "T" * 2000
    clipped = workflow_lab._clip_answer(answer, "must include video script")
    assert len(clipped) <= workflow_lab.JUDGE_ANSWER_CHARS
    assert clipped.startswith("H" * 100) and clipped.endswith("T" * 100)


def test_clip_answer_finds_a_keyword_in_a_middle_without_newlines():
    answer = "a" * 3000 + "b" * 5000 + " video script " + "c" * 5000 + "d" * 2000
    clipped = workflow_lab._clip_answer(answer, "must include video script")
    assert "video script" in clipped and len(clipped) <= workflow_lab.JUDGE_ANSWER_CHARS


def _job_with_baseline(results, baseline):
    import tempfile
    from agentdev.api.services.workflow_lab import LabJob
    job = LabJob(id="j1", workflow="w", scenarios=[Scenario(prompt="p")], repeats=len(results),
                 store_dir=Path(tempfile.mkdtemp()))
    job._baseline, job._baseline_loaded = baseline, True
    for entry in results:
        job.add_result(entry)
    job.status, job.finished_at = "completed", time.time()
    return job.to_dict()


def test_all_unjudged_job_reports_no_pass_rate_regression():
    runs = [{"scenario": 0, "repeat": k + 1, "status": "unjudged", "answer": "x", "seconds": 10, "cost_usd": 0.05,
             "judge": {"verdict": "unjudged", "judged_by": "basic"}} for k in range(2)]
    data = _job_with_baseline(runs, {"pass_rate": 1.0, "avg_seconds": 10, "cost_usd": 0.10, "done": 2})
    assert "pass_rate" not in data["regression"]


def test_cost_regression_compares_run_cost_only_on_both_sides():
    runs = [{"scenario": 0, "repeat": k + 1, "status": "passed", "answer": "x", "seconds": 10, "cost_usd": 0.05,
             "judge": {"pass": True, "judged_by": "ai", "cost_usd": 0.05}} for k in range(2)]
    # New-style baseline: same run cost (0.10) plus 0.10 of judging -> no regression either way.
    data = _job_with_baseline(runs, {"pass_rate": 1.0, "avg_seconds": 10, "cost_usd": 0.20,
                                     "judge_cost_usd": 0.10, "done": 2})
    assert "cost_usd" not in data["regression"] and data["run_cost_usd"] == 0.1
    # Old baseline without judge_cost_usd: its cost is all run cost; ours (0.10) is the same.
    old = _job_with_baseline(runs, {"pass_rate": 1.0, "avg_seconds": 10, "cost_usd": 0.10, "done": 2})
    assert "cost_usd" not in old["regression"]


def test_compare_baseline_skips_pass_rate_when_none():
    from agentdev.api.services.lab_diagnosis import compare_baseline
    assert compare_baseline({"pass_rate": None}, {"pass_rate": 1.0}) == {}


def test_resume_does_not_rejudge_when_output_folder_is_gone(tmp_path):
    runner = LabRunner(store_dir=tmp_path / "store")
    yaml_path = tmp_path / "wf.yaml"
    yaml_path.write_text("x: 1", encoding="utf-8")
    gone = tmp_path / "out_deleted"
    job = runner.start(yaml_path, "wf.yaml", [Scenario("a", "c")], 1,
                       run_once=lambda *a: {"answer": "built it", "questions": [], "output_dir": str(gone)},
                       judge=lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    data = _wait(job)
    assert data["results"][0]["status"] == "unjudged" and data["resumable"] is False
    runner._jobs.pop(job.id)
    with pytest.raises(ValueError):
        runner.resume(job.id, yaml_path, run_once=lambda *a: {"answer": "x"}, judge=lambda *a, **k: {"pass": True})


def test_failed_strong_rejudge_leaves_the_run_unjudged(monkeypatch):
    def fake(conn, model, user, system=""):
        if model == "strong":
            raise RuntimeError("strong model down")
        return '{"pass": true, "score": 7, "reason": "ok"}'

    monkeypatch.setattr(workflow_lab, "_judge_call", fake)
    monkeypatch.setattr(account_fallback, "default_model_for", lambda conn: "strong")
    with pytest.raises(workflow_lab.JudgeUnparsable):
        workflow_lab._judge("p", "c", "answer", [], account=_Account())


@pytest.mark.parametrize("score,passes,border", [
    (75, True, True), (95, True, False), (60, False, True), ("7/10", True, True), ("70/100", True, True),
    ("5/10", False, False), (8, True, False), (7.9, True, True), (6, False, True),
])
def test_scores_are_normalised_to_ten(score, passes, border):
    assert workflow_lab._rubric_pass({"pass": True, "score": score}) is passes
    assert workflow_lab._borderline({"score": score}) is border


def test_two_concurrent_resumes_start_one_job(tmp_path):
    import threading as th
    runner = LabRunner(store_dir=tmp_path / "store")
    yaml_path = tmp_path / "wf.yaml"
    yaml_path.write_text("x: 1", encoding="utf-8")
    job = runner.start(yaml_path, "wf.yaml", [Scenario("a", "c")], 1,
                       run_once=lambda *a: (_ for _ in ()).throw(RuntimeError("boom")),
                       judge=lambda *a, **k: {"pass": True})
    _wait(job)
    job.status = "cancelled"
    runner._save(job)
    runner._jobs.pop(job.id)
    gate, started, outcomes = th.Barrier(2), [], []
    real_load = runner._load

    def slow_load(job_id):
        data = real_load(job_id)
        time.sleep(0.2)  # widen the window between the "already running" check and registration
        return data

    runner._load = slow_load

    def run_once(path, scenario, cancel):
        started.append(1)
        time.sleep(0.3)
        return {"answer": "ok", "questions": []}

    def go():
        gate.wait()
        try:
            runner.resume(job.id, yaml_path, run_once=run_once, judge=lambda *a, **k: {"pass": True, "score": 9})
            outcomes.append("ok")
        except ValueError:
            outcomes.append("refused")
        except Exception as exc:  # noqa: BLE001 - surfaced by the assertion below
            outcomes.append(repr(exc))

    threads = [th.Thread(target=go) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert sorted(outcomes) == ["ok", "refused"], outcomes
    _wait(runner._jobs[job.id])
    assert len(started) == 1


def test_resumable_follows_output_folder_deleted_after_first_read(tmp_path):
    """``resumable`` reads the disk (output folder of unjudged runs): it must not be served stale from the cache."""
    from agentdev.api.services.workflow_lab import LabJob
    out = tmp_path / "out"
    out.mkdir()
    job = LabJob(id="j2", workflow="w", scenarios=[Scenario(prompt="p")], repeats=1, store_dir=tmp_path / "store")
    job._baseline, job._baseline_loaded = None, True
    job.add_result({"scenario": 0, "repeat": 1, "status": "unjudged", "answer": "x", "output_dir": str(out)})
    job.status, job.finished_at = "completed", time.time()
    assert job.to_dict()["resumable"] is True
    out.rmdir()
    assert job.to_dict()["resumable"] is False
