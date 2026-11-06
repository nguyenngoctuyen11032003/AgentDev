"""Lab quality rubric: the judge grades six dimensions, the size of the request sets the time budget, weak
dimensions become findings with a fix direction for the workflow assistant."""

import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentdev.api.services import lab_quality, workflow_lab
from agentdev.api.services.lab_quality import quality_findings, quality_profile, task_domain
from agentdev.api.services.workflow_lab import LabJob, LabRunner, Scenario
from agentdev.runtime.node.agent import account_fallback


@pytest.fixture(autouse=True)
def _lab_store(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow_lab, "_lab_dir", lambda: tmp_path / "lab_jobs")


class _Account:
    def current(self):
        return SimpleNamespace(id="acc", label="Acc"), "mid"

    def switch(self, failed_id):
        return False


def _dims(**scores):
    return {k: {"score": scores.get(k, 9), "note": f"note {k}"} for k in lab_quality.DIMENSIONS}


def _reply(monkeypatch, payload):
    seen = []

    def fake(conn, model, user, system=""):
        seen.append(user)
        return json.dumps(payload)

    monkeypatch.setattr(workflow_lab, "_judge_call", fake)
    monkeypatch.setattr(account_fallback, "default_model_for", lambda conn: "mid")
    return seen


# ---------------------------------------------------------------------------- kind of task


@pytest.mark.parametrize("prompt,hint,expected", [
    ("Làm video quảng cáo 30 giây cho quán cà phê, có kịch bản và phân cảnh", "", "video"),
    ("Viết app todo bằng React có thêm/xoá/lọc và test", "", "code"),
    ("Viết bài blog 800 chữ về du lịch Đà Lạt", "", "content"),
    ("Làm cho tôi cái này nhé", "video_production phòng sản xuất video", "video"),
    ("Xin chào", "", "general"),
])
def test_task_domain(prompt, hint, expected):
    assert task_domain(prompt, hint) == expected


# ---------------------------------------------------------------------------- judge


def test_judge_sends_rubric_and_run_facts_and_keeps_dimensions(monkeypatch):
    seen = _reply(monkeypatch, {"pass": True, "score": 8, "reason": "ổn", "scope": "large",
                                "dimensions": _dims(craft=6), "missing": ["chưa có test"], "fixes": ["thêm node test"]})
    verdict = workflow_lab._judge("Viết app todo bằng React", "có index.html", "Xong rồi", [], account=_Account(),
                                  facts="- time: 40s")
    assert "## Rubric (kind of task: code)" in seen[0] and "no placeholder/TODO" in seen[0]
    assert "## Run facts" in seen[0] and "- time: 40s" in seen[0]
    assert verdict["pass"] is True
    assert verdict["domain"] == "code" and verdict["scope"] == "large"
    assert verdict["dimensions"]["craft"] == {"score": 6.0, "note": "note craft"}
    assert verdict["missing"] == ["chưa có test"] and verdict["fixes"] == ["thêm node test"]


def test_generous_score_cannot_pass_when_requirements_are_not_met(monkeypatch):
    _reply(monkeypatch, {"pass": True, "score": 8, "reason": "đẹp", "dimensions": _dims(requirements=4)})
    verdict = workflow_lab._judge("Viết app todo", "đủ 3 chức năng", "Có 1 chức năng", [], account=_Account())
    assert verdict["pass"] is False and verdict["core_gate"] == ["requirements"]


def test_old_style_verdict_without_dimensions_still_works(monkeypatch):
    _reply(monkeypatch, {"pass": True, "score": 9, "reason": "ok"})
    verdict = workflow_lab._judge("Xin chào", "chào lại", "Chào bạn", [], account=_Account())
    assert verdict["pass"] is True and verdict["dimensions"] == {} and verdict["scope"] == ""


def test_parse_dimensions_ignores_unknown_and_clamps():
    dims = lab_quality.parse_dimensions({"dimensions": {"craft": {"score": "75/100"}, "bogus": {"score": 1},
                                                         "correctness": 120, "verification": {"score": "n/a"}}})
    assert dims == {"craft": {"score": 7.5, "note": ""}, "correctness": {"score": 10.0, "note": ""}}


# ---------------------------------------------------------------------------- findings


def _run(index, status, seconds=100, scope="medium", missing=None, fixes=None, domain="code", **scores):
    return {"scenario": index, "repeat": 1, "status": status, "seconds": seconds, "answer": "a",
            "judge": {"judged_by": "ai", "pass": status == "passed", "score": 6, "reason": "r", "domain": domain,
                      "scope": scope, "dimensions": lab_quality.parse_dimensions({"dimensions": _dims(**scores)}),
                      "missing": missing or [], "fixes": fixes or []}}


def test_weak_dimension_becomes_finding_with_domain_fix_and_judge_fix():
    runs = [_run(0, "failed", craft=4, fixes=["reviewer chấm theo checklist code"]), _run(1, "passed", craft=6)]
    findings = {f["code"]: f for f in quality_findings(runs)}
    craft = findings["weak_craft"]
    assert craft["severity"] == "warn" and craft["layer"] == "workflow"  # average 5: weak, not poor (< 5)
    assert "5/10" in craft["detail"] and "note craft" in craft["detail"]
    assert "TODO/stub" in craft["fix"] and "reviewer chấm theo checklist code" in craft["fix"]
    assert "weak_requirements" not in findings


def test_video_task_gets_video_fix_direction():
    findings = quality_findings([_run(0, "failed", domain="video", craft=5)])
    assert "hook 3 giây" in findings[0]["fix"]


def test_large_request_done_too_fast_with_missing_parts_is_flagged():
    runs = [_run(0, "failed", seconds=60, scope="large", missing=["thiếu trang đăng nhập", "thiếu test"])]
    shallow = [f for f in quality_findings(runs) if f["code"] == "shallow_for_scope"]
    assert shallow and "60s" in shallow[0]["detail"] and "thiếu trang đăng nhập" in shallow[0]["detail"]
    # Same speed on a small request is fine.
    assert not [f for f in quality_findings([_run(0, "failed", seconds=60, scope="small", missing=["x"])])
                if f["code"] == "shallow_for_scope"]


def test_profile_skips_runs_without_ai_dimensions():
    basic = {"scenario": 0, "status": "failed", "judge": {"judged_by": "basic"}}
    assert quality_profile([basic]) is None
    profile = quality_profile([basic, _run(0, "passed", craft=8, verification=6)])
    assert profile["runs"] == 1 and profile["weak"] == ["verification"]


# ---------------------------------------------------------------------------- job summary


def _job(results, scenario):
    job = LabJob(id="q1", workflow="w", scenarios=[scenario], repeats=len(results), store_dir=Path(tempfile.mkdtemp()))
    job._baseline, job._baseline_loaded = None, True
    for entry in results:
        job.add_result(entry)
    job.status, job.finished_at = "completed", time.time()
    return job.to_dict()


def test_large_scope_widens_the_time_budget_unless_the_scenario_sets_one():
    run = _run(0, "passed", seconds=600, scope="large")
    data = _job([run], Scenario(prompt="Viết app quản lý kho đầy đủ"))
    assert data["results"][0]["budget_seconds"] == 900 and not data["results"][0]["over_budget"]
    fixed = _job([_run(0, "passed", seconds=600, scope="large")], Scenario(prompt="Viết app", max_seconds=200))
    assert fixed["results"][0]["budget_seconds"] == 200 and fixed["results"][0]["over_budget"]


def test_poor_dimension_blocks_ready_and_goes_into_the_fix_brief():
    runs = [dict(_run(0, "passed", correctness=8, verification=3, missing=["thiếu README"],
                      fixes=["bắt chạy test"]), repeat=k + 1) for k in range(3)]
    for r in runs:
        r["status"] = "passed"
    data = _job(runs, Scenario(prompt="Viết API Python", criteria="có endpoint /items, có test"))
    assert data["quality"]["dimensions"]["verification"] == 3.0
    assert data["verdict"] == "not_ready"
    assert any("Có kiểm chứng" in r for r in data["verdict_reasons"])
    brief = data["fix_brief"]
    assert "### Chất lượng theo tiêu chí" in brief and "Có kiểm chứng: 3/10 ← cần sửa" in brief
    assert "Đã kiểm chứng: <lệnh>" in brief  # the code-specific direction for verification


def test_runner_passes_domain_and_facts_to_the_judge(tmp_path):
    yaml_path = tmp_path / "video_wf.yaml"
    yaml_path.write_text("graph:\n  id: video_wf\n  description: Phòng sản xuất video\n  nodes: []\n", encoding="utf-8")
    seen = {}

    def judge(prompt, criteria, answer, questions, domain="", facts=""):
        seen.update(domain=domain, facts=facts)
        return {"pass": True, "score": 9, "reason": "ok", "judged_by": "ai"}

    def run_once(path, scenario, cancel):
        return {"status": "done", "answer": "xong", "seconds": 42, "tokens": 1000, "agents": {"Writer": 2}}

    runner = LabRunner(store_dir=tmp_path / "store")
    job = runner.start(yaml_path, "video_wf.yaml", [Scenario(prompt="Làm cho tôi cái này")], 1,
                       run_once=run_once, judge=judge)
    deadline = time.monotonic() + 20
    while job.status in ("queued", "running") and time.monotonic() < deadline:
        time.sleep(0.02)
    assert seen["domain"] == "video"
    assert "- time: 42s" in seen["facts"] and "Writer ×2" in seen["facts"]
