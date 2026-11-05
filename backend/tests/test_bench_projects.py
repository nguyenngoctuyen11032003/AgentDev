"""Project benchmark: fake mode proves the harness solves, fails and detects damage correctly (no model, no cost)."""

from __future__ import annotations

import json
import pytest

from scripts import bench_projects as bp
from scripts import bench_repo_gen as gen


@pytest.fixture(scope="module")
def report():
    return bp.run_all("fake", "bugfix_team", ["a", "b", "c"], small=True)


def _run(report, label):
    return next(r for r in report["runs"] if r["label"] == label)


def test_scripted_solutions_pass_every_task(report):
    for label in ("a_ok", "b_ok", "c_ok"):
        run = _run(report, label)
        assert run["engine_error"] is None, run
        assert run["success"] is True, run["acceptance"]
        assert run["clean"] is True
        assert run["tests_after"] == "green"
        assert run["model_calls"] >= 1
    assert report["total_cost_usd"] == 0


def test_task_a_starts_red_others_green(report):
    assert _run(report, "a_ok")["tests_before"] == "red"
    assert _run(report, "b_ok")["tests_before"] == "green"
    assert _run(report, "c_ok")["tests_before"] == "green"


def test_wrong_fix_is_detected(report):
    run = _run(report, "a_wrong_fix")
    assert run["success"] is False
    assert run["acceptance"]["checks"]["hidden_clamp_test"] is False
    assert run["tests_after"] == "red"


def test_damage_is_detected(report):
    run = _run(report, "b_damage")
    problems = {(c["path"], c["problem"].split(":")[0]) for c in run["corrupted_files"]}
    assert ("pkg/sub01/m01.py", "bom_added") in problems
    assert ("pkg/sub01/m01.py", "crlf_added") in problems
    assert ("pkg/sub01/m00.py", "syntax_error") in problems
    assert set(run["files_outside_scope"]) == {"pkg/sub01/m00.py", "pkg/sub01/m01.py"}
    assert run["success"] is False and run["clean"] is False


def test_partial_rename_is_detected(report):
    run = _run(report, "c_partial_rename")
    checks = run["acceptance"]["checks"]
    assert checks["old_name_gone"] is False
    assert run["success"] is False
    assert len(_run(report, "c_ok")["files_changed"]) >= 10  # the rename really spans >= 10 files


def test_report_is_serialisable_and_renders(report, tmp_path):
    json.dumps(report)
    assert "a_ok" in bp.render_markdown(report)
    paths = bp.write_outputs(report, tmp_path)
    assert [p.suffix for p in paths] == [".json", ".md"]
    assert all(p.name.startswith("bench-projects-") for p in paths)


def test_fake_run_restores_engine_globals():
    from agentdev.runtime.node.agent import ProviderRegistry
    from agentdev.runtime.node.executor import agent_executor as module
    from agentdev.utils.human_prompt import HumanPromptService

    before = (module.resolve_connection, ProviderRegistry.__dict__["get_provider"],
              HumanPromptService.__dict__["request"])
    undo = bp.install_fake()
    assert module.resolve_connection is not before[0]
    undo()
    after = (module.resolve_connection, ProviderRegistry.__dict__["get_provider"],
             HumanPromptService.__dict__["request"])
    assert after == before


def test_full_size_fixture_is_medium_deterministic_and_git_initialised(tmp_path):
    a = gen.build_repo(tmp_path / "a", seed=7)
    assert 1500 <= a["file_count"] <= 3000
    assert len(a["norm_users"]) >= 10
    assert (tmp_path / "a" / ".git").is_dir()
    b = gen.build_repo(tmp_path / "b", seed=7)
    assert a["norm_users"] == b["norm_users"]
    assert (tmp_path / "a/pkg/sub03/m05.py").read_bytes() == (tmp_path / "b/pkg/sub03/m05.py").read_bytes()
    assert bp.run_pytest(tmp_path / "a")["status"] == "green"
    bug = gen.build_repo(tmp_path / "bug", seed=7, bug=True)
    assert bug["bug"] and bp.run_pytest(tmp_path / "bug")["status"] == "red"


def test_corruption_checks_on_a_scratch_repo(tmp_path):
    repo = tmp_path / "r"
    gen.build_repo(repo, subpackages=1, docs=1)
    (repo / "pkg/sub00/m00.py").write_bytes(b"x = 1\r\n")
    (repo / "pkg/sub00/m01.py").write_bytes(b"def (:\n")  # write_text would add CRLF on Windows
    (repo / "docs").joinpath("new.md").write_bytes(bp.BOM + b"hi\n")
    changes = bp.changed_files(repo)
    assert changes["docs/new.md"] == "A" and changes["pkg/sub00/m00.py"] == "M"
    problems = {(c["path"], c["problem"].split(":")[0]) for c in bp.corrupted_files(repo, changes)}
    assert problems == {("pkg/sub00/m00.py", "crlf_added"), ("pkg/sub00/m01.py", "syntax_error"),
                        ("docs/new.md", "bom_added")}
    assert bp.outside_scope(changes, ["docs/new.md"]) == ["pkg/sub00/m00.py", "pkg/sub00/m01.py"]


def test_real_refuses_paid_workflow(tmp_path):
    wf = tmp_path / "paid.yaml"
    wf.write_text("version: 0.4.0\ngraph:\n  id: p\n  start: [A]\n  end: [G]\n  nodes:\n"
                  "  - {id: A, type: agent, config: {name: m}}\n"
                  "  - {id: G, type: human, config: {description: ok, paid: true}}\n  edges: []\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="paid"):
        bp.run_all("real", str(wf), ["a"])


def test_real_refuses_when_plan_exceeds_max_runs():
    with pytest.raises(SystemExit, match="max-runs"):
        bp.run_all("real", "bugfix_team", ["a", "b", "c"], max_runs=2)


def test_shipped_workflows_have_no_paid_gate():
    import yaml

    for name in ("bugfix_team", "software_company"):
        path = bp.resolve_workflow(name)
        bp.assert_no_paid(yaml.safe_load(path.read_text(encoding="utf-8")), name)


def test_real_model_defaults_to_haiku_and_caps_cost():
    definition = bp.prepare_definition(bp.resolve_workflow("bugfix_team"), "real", bp.REAL_MODEL, 2.5)
    names = {n["config"]["name"] for n in definition["graph"]["nodes"] if n["type"] == "agent"}
    assert names == {"claude-haiku-5-5"}
    assert definition["graph"]["run_limits"]["max_cost_usd"] <= 2.5


def test_report_records_which_nodes_ran(report):
    # A real run with no file edits must be diagnosable: the report lists the agent nodes that took a turn.
    for run in report["runs"]:
        assert "Tech Lead" in run["nodes_run"]
        assert isinstance(run["nodes_run"], list)


def test_report_records_lead_final_text_and_plan_flag(report):
    # To tell "lead stopped at the plan gate" from "lead answered conversationally", each run keeps the lead's
    # final text (truncated) and whether it submitted a plan.
    for run in report["runs"]:
        assert isinstance(run["lead_final"], str) and len(run["lead_final"]) <= 600
        assert run["plan_submitted"] in (True, False)
