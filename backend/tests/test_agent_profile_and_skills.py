"""Agents work from their role, task description and ticked skills."""

from types import SimpleNamespace

from agentdev.runtime.node.agent.team import MEMBER_PROTOCOL, resolve_members
from agentdev.runtime.node.executor.agent_executor import (
    NATIVE_SKILL_USAGE_RULES,
    SKILL_USAGE_RULES,
    AgentNodeExecutor,
)


def _node(role="", description=""):
    return SimpleNamespace(role=role, description=description)


def test_profile_includes_role_and_task_description():
    text = AgentNodeExecutor._agent_profile_section(
        _node(role="You are a frontend engineer.", description="Build UIs with Vue 3 and Tailwind; mobile first.")
    )
    assert "You are a frontend engineer." in text
    assert "Build UIs with Vue 3 and Tailwind; mobile first." in text
    assert "task description" in text.lower()


def test_profile_role_only_is_unchanged_and_empty_is_empty():
    assert AgentNodeExecutor._agent_profile_section(_node(role="Only a role")) == "Only a role"
    assert AgentNodeExecutor._agent_profile_section(_node()) == ""
    assert "Just a description" in AgentNodeExecutor._agent_profile_section(_node(description="Just a description"))


def test_skill_rules_make_matching_skills_mandatory():
    for rules in (SKILL_USAGE_RULES, NATIVE_SKILL_USAGE_RULES):
        assert "MUST be loaded first" in rules
        assert "checklist" in rules
    assert "activate_skill" in SKILL_USAGE_RULES
    assert "SKILL.md" in NATIVE_SKILL_USAGE_RULES


def _agent(description="", skills=None):
    config = SimpleNamespace(skills=skills, team=None)
    return SimpleNamespace(
        node_type="agent", description=description, role="", predecessors=[], successors=[], config=config
    )


def test_roster_lists_member_skills_for_routing():
    nodes = {
        "cto": _agent(),
        "fe": _agent("Frontend dev", SimpleNamespace(enabled=True, allow=["frontend-ui-engineering", "impeccable"])),
        "be": _agent("Backend dev", SimpleNamespace(enabled=False, allow=["api-and-interface-design"])),
        "qa": _agent("Tester"),
    }
    members = {m.node_id: m for m in resolve_members("cto", [], nodes)}
    assert members["fe"].skills == ("frontend-ui-engineering", "impeccable")
    assert members["be"].skills == ()
    assert members["qa"].skills == ()


def test_member_protocol_mentions_role_description_and_skills():
    text = MEMBER_PROTOCOL.format(lead="cto", marker="?")
    assert "role" in text and "task description" in text and "skills" in text


# ---------------------------------------------------------------- several active skills

def _write_skill(root, name, allowed=None, extra_files=()):
    d = root / name
    d.mkdir(parents=True)
    front = f"---\nname: {name}\ndescription: {name} skill.\n"
    if allowed:
        front += f"allowed-tools: {allowed}\n"
    (d / "SKILL.md").write_text(front + "---\nBody of " + name, encoding="utf-8")
    for rel in extra_files:
        p = d / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")


def _manager(monkeypatch, tmp_path, tools):
    from agentdev.runtime.node.agent.skills import manager as skills_manager_module

    monkeypatch.setattr(skills_manager_module, "DEFAULT_SKILLS_ROOT", tmp_path)
    return skills_manager_module.AgentSkillManager(available_tool_names=tools)


def test_active_skill_restrictions_combine_instead_of_last_one_winning(monkeypatch, tmp_path):
    _write_skill(tmp_path, "fe", allowed="read_file write_file")
    _write_skill(tmp_path, "qa", allowed="run_tests")
    _write_skill(tmp_path, "free")
    mgr = _manager(monkeypatch, tmp_path, ["read_file", "write_file", "run_tests", "shell"])

    assert mgr.allowed_tools_for_active() == ()
    mgr.activate_skill("fe")
    assert mgr.allowed_tools_for_active() == ("read_file", "write_file")
    mgr.activate_skill("qa")
    assert mgr.allowed_tools_for_active() == ("read_file", "write_file", "run_tests")
    mgr.activate_skill("free")  # a skill without a restriction lifts it
    assert mgr.allowed_tools_for_active() == ()


def test_activation_lists_reference_files(monkeypatch, tmp_path):
    _write_skill(tmp_path, "fe", extra_files=("reference/typography.md", "data/colors.csv", ".git/x.md", "img.png"))
    mgr = _manager(monkeypatch, tmp_path, [])
    result = mgr.activate_skill("fe")
    assert result["files"] == ["data/colors.csv", "reference/typography.md"]

    message = AgentNodeExecutor._build_skill_followup_message(None, "activate_skill", result, "fe-dev")
    assert "reference/typography.md" in message.content and "read_skill_file" in message.content
