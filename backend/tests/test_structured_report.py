"""AGENTDEV_STRUCTURED_REPORT: evidence lines and failing commands survive the lead's report cap."""

from agentdev.runtime.node.agent import team as team_mod
from agentdev.runtime.node.agent.report_format import clip_old_result, structure_report

LIMIT = team_mod.MAX_MEMBER_RESULT_CHARS
EVIDENCE = [f"src/module{i}/handler.py:{40 + i} raises KeyError when the id is missing" for i in range(6)]


def _report():
    filler = "\n".join(f"Looked at the module and found nothing odd in step {i}, continuing the review." for i in range(40))
    return (
        "Fixed the login crash.\n\n" + filler + "\n\n## Evidence\n" + "\n".join(EVIDENCE) + "\n\n" + filler
        + "\n\nCommands\n$ pytest -q -x\n2 failed, 14 passed (AssertionError in test_login)\n$ git status\n"
        + "\n" + filler + "\n\n## Open items\n- not verified on Windows\n- DB migration still pending\n"
        + "\n".join(f"Trailing note {i} with some more prose to pad the end of the report." for i in range(20))
    )


def test_old_cut_loses_middle_evidence_new_keeps_it():
    report = _report()
    old = team_mod._truncate(report, LIMIT)
    new = structure_report(report, LIMIT, team_mod._truncate)
    assert sum(line in old for line in EVIDENCE) < len(EVIDENCE)  # the middle goes missing
    assert all(line in new for line in EVIDENCE)
    assert "2 failed, 14 passed" in new
    assert "DB migration still pending" in new
    assert len(new) <= LIMIT + 120


def test_short_report_is_untouched():
    assert structure_report("done. a.py:1 fixed", LIMIT, team_mod._truncate) == "done. a.py:1 fixed"


def test_unstructured_long_text_falls_back_to_head_and_tail():
    text = "word " * 2000
    out = structure_report(text, LIMIT, team_mod._truncate)
    assert out == team_mod._truncate(text.strip(), LIMIT)


def test_newest_evidence_wins_when_too_many():
    lines = [f"a/b{i}.py:{i} issue number {i} " + "x" * 80 for i in range(60)]
    out = structure_report("Summary\n" + "\n".join(lines) + "\n" + "pad " * 600, LIMIT, team_mod._truncate)
    assert "a/b59.py:59" in out and "a/b0.py:0 " not in out


def test_old_result_keeps_head_tail_and_errors():
    body = "START line\n" + "ok line\n" * 400 + "ERROR: disk full at write\n" + "ok line\n" * 400 + "END line"
    out = clip_old_result(body, 1500)
    assert out.startswith("START") and out.endswith("END line") and "ERROR: disk full" in out
    assert len(out) <= 1500 + 120
    assert clip_old_result("short", 1500) == "short"


def test_flag_default_and_switch(monkeypatch):
    from agentdev.runtime.node.agent.report_format import structured_report_enabled

    monkeypatch.setenv("AGENTDEV_STRUCTURED_REPORT", "1")
    assert structured_report_enabled()
    monkeypatch.setenv("AGENTDEV_STRUCTURED_REPORT", "0")
    assert not structured_report_enabled()
