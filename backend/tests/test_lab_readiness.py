"""Lab readiness: graph checks, strict verdict, baseline/regression, judge manifest, parallel ordering."""

import threading
import time
from pathlib import Path

import pytest

from agentdev.api.services import skill_library, workflow_lab
from agentdev.api.services.lab_diagnosis import compare_baseline, run_budget
from agentdev.api.services.workflow_lab import (
    AUTO_ANSWER,
    LabJob,
    LabRunner,
    Scenario,
    build_output_manifest,
    edge_condition_matches,
    model_tier,
    static_check_data,
)


@pytest.fixture(autouse=True)
def _no_skills(tmp_path, monkeypatch):
    root = tmp_path / "skills"
    root.mkdir()
    monkeypatch.setattr(skill_library, "SKILLS_ROOT", root)
    monkeypatch.setattr(workflow_lab, "_lab_dir", lambda: tmp_path / "lab_jobs")


def _agent(node_id, model="claude-sonnet-5-5", role="r", **params):
    return {"id": node_id, "type": "agent",
            "config": {"connection": "fake", "provider": "fake", "name": model, "role": role, "params": params}}


def _kw(regex, case_sensitive=True):
    return {"type": "keyword", "config": {"regex": [regex], "case_sensitive": case_sensitive}}


def _data(nodes, edges, start="A", end=None):
    return {"version": "0.4.0", "graph": {"id": "wf", "start": [start], "end": end or [], "nodes": nodes, "edges": edges}}


def _checks(data):
    return {c["id"]: c for c in static_check_data(data)["checks"]}


def test_unguarded_cycle_fails_and_loop_counter_fixes_it():
    nodes = [_agent("A"), _agent("B")]
    edges = [{"from": "A", "to": "B"}, {"from": "B", "to": "A"}]
    assert _checks(_data(nodes, edges))["loops"]["status"] == "fail"
    guard = {"id": "G", "type": "loop_counter", "config": {"max_iterations": 2}}
    edges = [{"from": "A", "to": "B"}, {"from": "B", "to": "G"}, {"from": "G", "to": "A"}]
    assert _checks(_data(nodes + [guard], edges))["loops"]["status"] == "pass"


def test_human_node_must_route_automatic_answer_forward():
    human = {"id": "H", "type": "human", "config": {"description": "ok?"}}
    nodes = [_agent("A"), human, _agent("B")]
    ok = [{"from": "A", "to": "H"},
          {"from": "H", "to": "B", "condition": _kw(r"^\s*(OK\s*$|\[Automatic answer)", False)},
          {"from": "H", "to": "A", "condition": _kw(r"^(?!\s*(OK\s*$|\[Automatic answer))", False)}]
    guard = {"id": "G", "type": "loop_counter", "config": {"max_iterations": 2}}
    ok.append({"from": "A", "to": "G"})
    assert _checks(_data(nodes + [guard], ok))["human_auto"]["status"] == "pass"
    bad = [dict(e) for e in ok]
    bad[1] = {"from": "H", "to": "B", "condition": _kw(r"^OK$")}  # automatic answer is not "OK"
    result = _checks(_data(nodes + [guard], bad))["human_auto"]
    assert result["status"] == "fail" and result["nodes"] == ["H"]


def test_edge_condition_semantics():
    assert edge_condition_matches(_kw("approved", False), "APPROVED yes")
    assert not edge_condition_matches(_kw("approved", True), "APPROVED yes")
    assert edge_condition_matches({"type": "keyword", "config": {"none": ["bad"]}}, "good")
    assert not edge_condition_matches({"type": "keyword", "config": {"any": ["x"], "none": ["bad"]}}, "x bad")
    assert edge_condition_matches(_kw(r"\[Automatic answer"), AUTO_ANSWER)


def test_dead_end_and_model_fit_and_critical_path():
    nodes = [_agent("A"), _agent("Reviewer", model="claude-opus-5-5"), _agent("Stuck")]
    edges = [{"from": "A", "to": "Reviewer"}, {"from": "A", "to": "Stuck"}]
    checks = _checks(_data(nodes, edges, end=["Reviewer"]))
    assert checks["dead_end"]["nodes"] == ["Stuck"] and checks["dead_end"]["status"] == "warn"
    assert checks["model_fit"]["nodes"] == ["Reviewer"]
    assert checks["critical_path"]["estimated_seconds"] == 40 + 90  # A (mid) then Reviewer (top)
    chain = [_agent(f"N{i}", model="claude-opus-5-5") for i in range(3)]
    edges = [{"from": "N0", "to": "N1"}, {"from": "N1", "to": "N2"}]
    slow = _checks(_data(chain, edges, start="N0"))["critical_path"]
    assert slow["estimated_seconds"] == 270 and slow["status"] == "warn"


def test_model_tier():
    assert [model_tier(m) for m in ("claude-haiku-5-5", "gemini-3-flash-preview", "claude-sonnet-5-5",
                                    "claude-fable-5-1", "gpt-6.1-sol")] == ["small", "small", "mid", "top", "top"]


def _wait(job):
    for _ in range(300):
        if job.status not in ("queued", "running"):
            return
        time.sleep(0.02)


def _run(scenarios, repeats, run_once, judge):
    job = LabRunner().start(Path("nope.yaml"), "nope.yaml", scenarios, repeats, run_once=run_once, judge=judge)
    _wait(job)
    return job.to_dict()


def _ok(path, scenario, cancel):
    return {"answer": "ok", "tokens": 10, "seconds": 1, "questions": []}


def test_each_scenario_needs_two_thirds():
    calls = {"a": 0, "b": 0}

    def run_once(path, scenario, cancel):
        calls[scenario.prompt] += 1
        return {"answer": "bad" if scenario.prompt == "b" and calls["b"] > 1 else "ok", "tokens": 1, "questions": []}

    # b passes 1 of 3 runs, a passes 3 of 3: pooled rate 4/6 < 0.8 anyway; use 5 repeats-less case below.
    data = _run([Scenario("a", "c"), Scenario("b", "c")], 3, run_once,
                lambda p, c, a, q: {"pass": a == "ok", "score": 9, "judged_by": "ai"})
    assert data["verdict"] == "not_ready"
    assert any("b" in r and "1/3" in r for r in data["verdict_reasons"])
    assert data["scenarios"][1]["needed"] == 2


def test_basic_judge_only_is_unverified():
    data = _run([Scenario("hi", "c")], 1, _ok, lambda p, c, a, q: {"pass": True, "judged_by": "basic"})
    assert data["verdict"] == "not_ready" and data["unverified"] == 1
    assert any("cơ bản" in r for r in data["verdict_reasons"])
    ai = _run([Scenario("hi", "c")], 1, _ok, lambda p, c, a, q: {"pass": True, "judged_by": "ai"})
    assert ai["verdict"] == "ready" and ai["verdict_reasons"] == []


def test_over_budget_blocks_ready_unless_not_strict(monkeypatch):
    def slow(path, scenario, cancel):
        return {"answer": "ok", "tokens": 10, "seconds": 500, "questions": []}

    judge = lambda p, c, a, q: {"pass": True, "judged_by": "ai"}  # noqa: E731
    data = _run([Scenario("hi", "c")], 1, slow, judge)
    assert data["verdict"] == "not_ready" and data["over_budget_runs"] == 1
    assert data["results"][0]["over_budget"] is True
    assert any(f["code"] == "over_budget" for f in data["findings"])
    monkeypatch.setenv("AGENTDEV_LAB_STRICT", "0")
    assert _run([Scenario("hi", "c")], 1, slow, judge)["verdict"] == "ready"
    # an explicit per-scenario budget wins over the default
    assert run_budget("x" * 500, 900, 5)["seconds"] == 900 and run_budget("hi")["seconds"] == 120
    assert run_budget("x" * 500)["tokens"] == 150_000


def test_baseline_regression_and_listing(tmp_path):
    runner = LabRunner()
    first = runner.start(Path("nope.yaml"), "wf.yaml", [Scenario("a", "c")], 1, run_once=_ok,
                         judge=lambda p, c, a, q: {"pass": True, "judged_by": "ai"})
    _wait(first)
    time.sleep(0.1)
    assert first.to_dict()["verdict"] == "ready" and first.to_dict()["baseline"] is None

    def slower(path, scenario, cancel):
        return {"answer": "ok", "tokens": 10, "seconds": 50, "cost_usd": 1.0, "questions": []}

    second = runner.start(Path("nope.yaml"), "wf.yaml", [Scenario("a", "c")], 1, run_once=slower,
                          judge=lambda p, c, a, q: {"pass": True, "judged_by": "ai"})
    _wait(second)
    data = second.to_dict()
    assert data["baseline"]["id"] == first.id
    assert "avg_seconds" in data["regression"]
    assert any(f["code"] == "regression" for f in data["findings"])
    assert "regression" in data["fix_brief"]
    rows = runner.list_jobs("wf.yaml")
    assert [r["id"] for r in rows] == [second.id, first.id] and rows[0]["status"] == "completed"
    assert runner.list_jobs("other.yaml") == []
    assert compare_baseline({"pass_rate": 0.7}, {"pass_rate": 0.9})["pass_rate"]["was"] == 0.9
    assert compare_baseline({"pass_rate": 0.85}, {"pass_rate": 0.9}) == {}


def test_job_stores_workflow_hash(tmp_path):
    yaml_path = tmp_path / "w.yaml"
    yaml_path.write_text("a: 1", encoding="utf-8")
    job = LabRunner().start(yaml_path, "w.yaml", [Scenario("a", "c")], 1, run_once=_ok,
                            judge=lambda p, c, a, q: {"pass": True})
    _wait(job)
    time.sleep(0.05)
    data = job.to_dict()
    assert len(data["workflow_hash"]) == 64 and data["finished_at"]


def test_output_manifest_lists_files_and_skips_binaries(tmp_path):
    assert build_output_manifest(tmp_path / "missing") == ""
    (tmp_path / "script.md").write_text("# Kịch bản\nCảnh 1", encoding="utf-8")
    (tmp_path / "img.png").write_bytes(b"\x89PNG\x00\x01binary")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "a.txt").write_text("x" * 2000, encoding="utf-8")
    text = build_output_manifest(tmp_path)
    assert "- script.md" in text and "- img.png" in text and "- sub/a.txt (2000 bytes)" in text
    assert "Cảnh 1" in text and "binary" not in text
    assert text.count("x") <= 600 + 20


def test_rubric_requires_score_seven():
    assert workflow_lab._rubric_pass({"pass": True, "score": 8})
    assert not workflow_lab._rubric_pass({"pass": True, "score": 6})
    assert workflow_lab._rubric_pass({"pass": True})
    assert not workflow_lab._rubric_pass({"pass": "yes", "score": 9})


def test_parallel_runs_keep_stable_order_and_cancel():
    def run_once(path, scenario, cancel):
        time.sleep(0.2 if scenario.prompt == "a" else 0.01)  # the first scenario finishes last
        return {"answer": scenario.prompt, "tokens": 1, "questions": []}

    data = _run([Scenario("a", "c"), Scenario("b", "c"), Scenario("c", "c")], 2, run_once,
                lambda p, c, a, q: {"pass": True, "judged_by": "ai"})
    assert [(r["repeat"], r["scenario"]) for r in data["results"]] == [(1, 0), (1, 1), (1, 2), (2, 0), (2, 1), (2, 2)]
    assert data["status"] == "completed" and data["done"] == 6

    gate = threading.Event()

    def blocking(path, scenario, cancel):
        gate.wait(5)
        if cancel.is_set():
            raise RuntimeError("cancelled")
        return {"answer": "ok", "tokens": 1, "questions": []}

    runner = LabRunner()
    job = runner.start(Path("nope.yaml"), "nope.yaml", [Scenario("a", "c")] * 4, 2, run_once=blocking,
                       judge=lambda p, c, a, q: {"pass": True})
    time.sleep(0.1)
    runner.cancel(job.id)
    gate.set()
    _wait(job)
    assert job.status == "cancelled" and len(job.results) <= 3
    assert isinstance(job, LabJob)


def test_guarded_feedback_loop_through_human_is_not_a_human_auto_failure():
    # writer -> human -> loop_counter -> writer: every human edge stays in the loop, the counter ends it
    human = {"id": "H", "type": "human", "config": {"description": "ok?"}}
    guard = {"id": "G", "type": "loop_counter", "config": {"max_iterations": 2}}
    edges = [{"from": "W", "to": "H"}, {"from": "H", "to": "G"}, {"from": "G", "to": "W"}]
    checks = _checks(_data([_agent("W"), human, guard], edges, start="W"))
    assert checks["human_auto"]["status"] == "pass" and checks["loops"]["status"] == "pass"
    # the same loop without the counter still fails both checks
    edges = [{"from": "W", "to": "H"}, {"from": "H", "to": "W"}]
    checks = _checks(_data([_agent("W"), human], edges, start="W"))
    assert checks["human_auto"]["status"] == "fail" and checks["loops"]["status"] == "fail"


def test_new_failures_ignores_problems_already_in_the_saved_file():
    from agentdev.api.services.workflow_lab import new_failures

    human = {"id": "H", "type": "human", "config": {"description": "ok?"}}
    strict = {"from": "H", "to": "B", "condition": _kw(r"^OK$")}
    saved = _data([_agent("A"), _agent("B"), human],
                  [{"from": "A", "to": "B"}, {"from": "B", "to": "A"}, {"from": "A", "to": "H"}, strict])
    edited = _data([_agent("A"), _agent("B"), human, _agent("C")],
                   [{"from": "A", "to": "B"}, {"from": "B", "to": "A"}, {"from": "A", "to": "H"}, strict,
                    {"from": "B", "to": "C"}])
    report = static_check_data(edited)
    assert {c["id"] for c in report["checks"] if c["status"] == "fail"} >= {"loops", "human_auto"}
    assert [c["id"] for c in new_failures(report, saved)] == []
    # a new file (no baseline) keeps every failure
    assert {c["id"] for c in new_failures(report, None)} >= {"loops", "human_auto"}
    # a loop / gate the edit adds is still reported
    worse = _data(edited["graph"]["nodes"] + [_agent("D"), _agent("E"), {"id": "H2", "type": "human", "config": {}}],
                  edited["graph"]["edges"] + [{"from": "C", "to": "D"}, {"from": "D", "to": "C"},
                                              {"from": "C", "to": "H2"},
                                              {"from": "H2", "to": "E", "condition": _kw(r"^OK$")}])
    new = {c["id"]: c for c in new_failures(static_check_data(worse), saved)}
    assert new["loops"]["loops"] == [["C", "D"]] and new["human_auto"]["nodes"] == ["H2"]


def test_concurrent_saves_of_one_job_do_not_collide(tmp_path, monkeypatch):
    replaced = []
    real_replace = workflow_lab.os.replace
    failed_once = {}

    def flaky_replace(src, dst):
        replaced.append(Path(src).name)
        if not failed_once:  # a reader holding the file on Windows
            failed_once["x"] = True
            raise PermissionError("in use")
        return real_replace(src, dst)

    monkeypatch.setattr(workflow_lab.os, "replace", flaky_replace)
    store = tmp_path / "jobs"
    runner = LabRunner(store_dir=store)
    job = LabJob(id="abcdef123456", workflow="wf.yaml", scenarios=[Scenario("a", "c")], repeats=1)
    threads = [threading.Thread(target=runner._save, args=(job,)) for _ in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(replaced)) == len(replaced) - 1  # unique temp file per write (one retried)
    assert sorted(p.name for p in store.iterdir()) == ["abcdef123456.json"]  # no temp file left behind
    assert runner.get("abcdef123456") is not None
