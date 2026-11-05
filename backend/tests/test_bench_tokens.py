"""Fake mode of the token benchmark: runs the real engine with a fake provider (no model, no cost)."""

from __future__ import annotations

import json

import pytest

from scripts import bench_tokens


@pytest.fixture(scope="module")
def report():
    return bench_tokens.run_all("fake", ["chat", "followup", "team"], max_usd=0.5, max_runs=3)


def _run(report, scenario, label=None):
    sc = next(s for s in report["scenarios"] if s["name"] == scenario)
    return next(r for r in sc["runs"] if label is None or r["label"] == label)


def test_all_scenarios_ran_without_error(report):
    assert [s["name"] for s in report["scenarios"]] == ["chat", "followup", "team"]
    for sc in report["scenarios"]:
        for run in sc["runs"]:
            assert run["error"] is None, run
            assert run["totals"]["calls"] >= 1
    assert report["total_cost_usd"] == 0
    json.dumps(report)  # serialisable, and holds no prompt text


def test_history_grows_and_static_head_is_stable(report):
    sizes = [r["nodes"][0]["input_chars"] for r in next(s for s in report["scenarios"] if s["name"] == "followup")["runs"]]
    assert sizes[0] < sizes[1] < sizes[2]
    turn2 = _run(report, "followup", "turn 2")
    assert turn2["nodes"][0]["prompt"]["history_chars"] > 0
    assert turn2["static_head_identical_to_previous"] is True


def test_team_has_four_nodes_with_preloaded_skills(report):
    run = _run(report, "team")
    assert [n["node"] for n in run["nodes"]] == ["Plan", "Worker1", "Worker2", "Merge"]
    assert all(n["prompt"]["skills_chars"] > 0 for n in run["nodes"])


def test_no_volatile_part_in_static_head(report):
    assert not report["structure_issues"], report["structure_issues"]
    for sc in report["scenarios"]:
        for run in sc["runs"]:
            assert not any(n["cache_breaking_order"] for n in run["nodes"])


def test_volatile_detection_and_markdown():
    assert bench_tokens._volatile_hits("generated 2026-11-05T12:00:00 id 0123456789abcdef0123")
    assert not bench_tokens._volatile_hits("Be brief. Answer in the user's language.")


def test_markdown_and_baseline_are_stable(report, tmp_path):
    md = bench_tokens.render_markdown(report, stable=True)
    assert "generated" not in md and "| sec |" not in md
    paths = bench_tokens.write_outputs(report, tmp_path, baseline=True)
    names = {p.name for p in paths}
    assert bench_tokens.BASELINE_NAME in names
    assert any(n.endswith(".json") for n in names) and any(n.startswith("bench-tokens-2") for n in names)


def test_real_mode_refuses_over_budget_before_running():
    with pytest.raises(SystemExit, match="max-runs"):
        bench_tokens.run_all("real", ["chat", "followup", "team"], max_usd=0.5, max_runs=3)


def test_followup_long_reports_shared_prefix_ratio():
    rep = bench_tokens.run_all("fake", ["followup_long"], max_usd=0.5, max_runs=6)
    runs = rep["scenarios"][0]["runs"]
    assert len(runs) == 6 and all(r["error"] is None for r in runs)
    ratios = [r["shared_prefix_ratio"] for r in runs[1:]]
    assert all(0 <= x <= 1 for x in ratios)
    assert sum(ratios[:4]) / 4 > 0.4  # the first turns keep the whole earlier history as prefix
