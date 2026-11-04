"""Prompt caching is prefix based: the static part of the system prompt must come first and be byte-identical
between turns; only the small per-message block (plan rule, language) may differ, and it goes last."""

import os
from types import SimpleNamespace
from unittest.mock import MagicMock

from agentdev.runtime.node.agent.team import (
    LEAD_PROTOCOL,
    LEAD_TURN_BLOCK,
    PLAN_RULE_ON,
    PLAN_RULE_QUESTION,
    USER_RESPONSE_RULES,
)
from agentdev.runtime.node.executor.agent_executor import LOADED_SKILLS_HEADING, AgentNodeExecutor
from tests.test_team_logic import _state, _team


def _skill(root, name, body):
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {name} skill.\n---\n{body}", encoding="utf-8")


def _executor(team):
    executor = object.__new__(AgentNodeExecutor)
    executor.context = SimpleNamespace(cancel_event=None, global_state={}, log_manager=MagicMock())
    executor._active_teams = lambda: {"lead": team}
    return executor


def _build(monkeypatch, tmp_path, message):
    from agentdev.runtime.node.agent.skills import manager as skills_manager_module

    monkeypatch.setattr(skills_manager_module, "DEFAULT_SKILLS_ROOT", tmp_path)
    mgr = skills_manager_module.AgentSkillManager(allow=["big"], available_tool_names=[])
    team = _team(state=_state(message))
    node = SimpleNamespace(id="lead", role="You are the lead PM.", description="")
    return _executor(team)._build_system_prompt(node, mgr), team


def test_static_prefix_identical_across_turns(monkeypatch, tmp_path):
    _skill(tmp_path, "big", "BIG-SKILL-BODY " * 200)
    # Turn 1: a new feature request (plan rule on); turn 2: a plain question in another language.
    p1, t1 = _build(monkeypatch, tmp_path, "Build me a full web shop with payments")
    p2, t2 = _build(monkeypatch, tmp_path, "What does the cart module do?")
    assert t1._plan_rule() != t2._plan_rule()
    assert PLAN_RULE_ON in p1 and PLAN_RULE_QUESTION in p2

    common = len(os.path.commonprefix([p1, p2]))
    static_len = min(len(p1), len(p2)) - max(len(LEAD_TURN_BLOCK) + len(PLAN_RULE_ON), 0)
    first_turn_marker = p1.index("## This message")
    assert common >= first_turn_marker  # everything before the per-turn block is shared byte for byte
    assert common >= static_len
    # The per-turn block is the tail of the prompt, after role, protocol, roster, skills and rules.
    for anchor in ("You are the lead PM.", "# You lead a team", "## Your team", LOADED_SKILLS_HEADING, "BIG-SKILL-BODY", "# How you answer"):
        assert 0 <= p1.index(anchor) < first_turn_marker
    assert p1.rindex("## This message") > p1.index(USER_RESPONSE_RULES)
    assert "## This message" not in p1[:first_turn_marker]


def test_all_sections_still_present(monkeypatch, tmp_path):
    _skill(tmp_path, "big", "BIG-SKILL-BODY")
    prompt, team = _build(monkeypatch, tmp_path, "Build me a full web shop")
    for text in (
        "You are the lead PM.",
        "## First, classify the message",
        "## Rules",
        "## Your team",
        team._plan_rule(),
        LOADED_SKILLS_HEADING,
        "BIG-SKILL-BODY",
        USER_RESPONSE_RULES,
    ):
        assert text in prompt
    assert team.system_prompt_section() in prompt or all(
        part in prompt for part in team.system_prompt_parts() if part
    )


def test_section_equals_static_plus_per_turn_and_full_protocol():
    team = _team(state=_state("Build me a web shop"))
    static, per_turn = team.system_prompt_parts()
    assert team.system_prompt_section() == static + "\n\n" + per_turn
    assert "## This message" not in static and per_turn.startswith("## This message")
    assert "## This message" in LEAD_PROTOCOL


def test_prompt_is_stable_within_one_turn(monkeypatch, tmp_path):
    _skill(tmp_path, "big", "BIG-SKILL-BODY")
    a, _ = _build(monkeypatch, tmp_path, "Build me a full web shop")
    b, _ = _build(monkeypatch, tmp_path, "Build me a full web shop")
    assert a == b
