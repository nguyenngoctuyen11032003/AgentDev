"""End to end: a member's role, task description and ticked skills reach its prompt (Claude CLI and Codex CLI),
the lead's roster routes on them, and the static part is not re-sent on every step."""

import json
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from agentdev.entity.messages import Message, MessageRole, ToolCallPayload
from agentdev.entity.tool_spec import ToolSpec
from agentdev.runtime.node.agent.providers._cli_common import CliClient, build_tool_preamble, flatten_conversation
from agentdev.runtime.node.agent.providers.claude_cli_provider import ClaudeCliProvider
from agentdev.runtime.node.agent.providers.codex_cli_provider import CodexCliProvider
from agentdev.runtime.node.agent.team import TeamDelegation, TeamState, resolve_members
from agentdev.runtime.node.executor.agent_executor import LOADED_SKILLS_HEADING, AgentNodeExecutor

FE_ROLE = "You are the frontend engineer."
FE_DESC = "Mobile first. Every page meets WCAG AA."
FE_RULE = "FE-RULE: spacing uses the 8px grid; never inline styles."
TASK = "Build the login page"


def _skill(root, name, body):
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {name} skill.\n---\n{body}", encoding="utf-8")


def _skills(monkeypatch, root, allow):
    from agentdev.runtime.node.agent.skills import manager as skills_manager_module

    monkeypatch.setattr(skills_manager_module, "DEFAULT_SKILLS_ROOT", root)
    return skills_manager_module.AgentSkillManager(allow=allow, available_tool_names=[])


def _bare_executor():
    executor = object.__new__(AgentNodeExecutor)
    executor.context = SimpleNamespace(cancel_event=None, global_state={}, log_manager=MagicMock())
    return executor


def _fe_node():
    return SimpleNamespace(id="fe", role=FE_ROLE, description=FE_DESC)


def _cfg():
    return SimpleNamespace(base_url=None, api_key=None, name="m1", provider="x", params={})


# ---------------------------------------------------------------- system prompt


def test_member_system_prompt_has_role_description_and_full_skill_body(monkeypatch, tmp_path):
    _skill(tmp_path, "fe-rules", FE_RULE)
    _skill(tmp_path, "other", "Other body")
    mgr = _skills(monkeypatch, tmp_path, ["fe-rules"])
    prompt = _bare_executor()._build_system_prompt(_fe_node(), mgr)

    assert FE_ROLE in prompt and FE_DESC in prompt
    assert FE_RULE in prompt and LOADED_SKILLS_HEADING in prompt
    assert "before finishing check your output" in prompt
    assert prompt.count(FE_RULE) == 1
    assert "name: fe-rules" not in prompt  # frontmatter stripped
    assert "<name>fe-rules</name>" not in prompt  # not listed again in the on-demand catalog
    assert "Other body" not in prompt  # not ticked


def test_preload_respects_budget_and_tick_order(monkeypatch, tmp_path):
    _skill(tmp_path, "big", "B" * 500)
    _skill(tmp_path, "small", "S" * 100)
    _skill(tmp_path, "tiny", "T" * 50)
    mgr = _skills(monkeypatch, tmp_path, ["small", "big", "tiny"])
    assert [s.name for s in mgr.preload(budget=200)] == ["small", "tiny"]
    catalog = mgr.build_available_skills_xml()
    assert "<name>big</name>" in catalog and "<name>small</name>" not in catalog
    assert "B" * 500 not in mgr.build_preloaded_skills_section()

    # No explicit selection (the whole library is exposed): nothing preloaded, everything on demand.
    everything = _skills(monkeypatch, tmp_path, [])
    assert everything.preload() == [] and "<name>tiny</name>" in everything.build_available_skills_xml()


def test_activating_a_preloaded_skill_does_not_repeat_its_text(monkeypatch, tmp_path):
    _skill(tmp_path, "fe-rules", FE_RULE)
    (tmp_path / "fe-rules" / "ref.md").write_text("ref", encoding="utf-8")
    mgr = _skills(monkeypatch, tmp_path, ["fe-rules"])
    mgr.preload()
    assert mgr.read_skill_file("fe-rules", "ref.md")["content"] == "ref"  # no activation needed
    assert "ref.md" in mgr.build_preloaded_skills_section()

    executor = _bare_executor()
    raw = executor._execute_skill_tool("activate_skill", {"skill_name": "fe-rules"}, mgr)
    ack, followup = executor._skill_tool_result("activate_skill", raw, "fe")
    assert ack["already_active"] is True and followup is None


def test_native_mode_preloads_and_lists_only_the_rest(monkeypatch, tmp_path):
    _skill(tmp_path, "fe-rules", FE_RULE)
    _skill(tmp_path, "huge", "H" * 40_000)
    mgr = _skills(monkeypatch, tmp_path, ["fe-rules", "huge"])
    prompt = _bare_executor()._build_system_prompt(_fe_node(), None, mgr)
    assert FE_RULE in prompt and "H" * 40_000 not in prompt
    assert "huge/SKILL.md" in prompt and "fe-rules/SKILL.md" not in prompt


# ---------------------------------------------------------------- lead roster


def test_lead_roster_shows_role_description_and_skills():
    def agent(role="", description="", skills=None):
        return SimpleNamespace(node_type="agent", role=role, description=description, predecessors=[], successors=[],
                               config=SimpleNamespace(skills=skills, team=None))

    nodes = {
        "cto": agent(),
        "fe": agent(FE_ROLE, FE_DESC, SimpleNamespace(enabled=True, allow=["frontend-ui-engineering"])),
        "qa": agent(description="Tester"),
    }
    team = TeamDelegation(lead_id="cto", members=resolve_members("cto", [], nodes), runner=lambda *a: [],
                          prompt_service=None, state=TeamState(), max_delegations=3, max_review_rounds=2,
                          plan_approval=False)
    lines = team.system_prompt_section().splitlines()
    fe_line = next(line for line in lines if line.startswith("- `fe`"))
    assert FE_ROLE in fe_line and FE_DESC in fe_line and "frontend-ui-engineering" in fe_line
    assert next(line for line in lines if line.startswith("- `qa`")) == "- `qa`: Tester"


# ---------------------------------------------------------------- providers

TOOL = ToolSpec(name="write_file", description="Write a file",
                parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]})


def _member_conversation(monkeypatch, root):
    _skill(root, "fe-rules", FE_RULE)
    mgr = _skills(monkeypatch, root, ["fe-rules"])
    system = _bare_executor()._build_system_prompt(_fe_node(), mgr)
    return [Message(role=MessageRole.SYSTEM, content=system), Message(role=MessageRole.USER, content=TASK)]


def _tool_step(conv, call_id):
    conv.append(Message(role=MessageRole.ASSISTANT, content="",
                        tool_calls=[ToolCallPayload(id=call_id, function_name="write_file", arguments='{"path": "a"}')]))
    conv.append(Message(role=MessageRole.TOOL, content="ok", tool_call_id=call_id, metadata={"tool_name": "write_file"}))


def test_claude_cli_skill_body_is_in_system_prompt_and_not_resent_on_resume(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude_home"))
    monkeypatch.delenv("AGENTDEV_CLI_SESSION_REUSE", raising=False)
    conv = _member_conversation(monkeypatch, tmp_path / "skills")
    calls = []
    replies = [{"text": "", "tool_calls": [{"name": "write_file", "arguments": {"path": "a"}}]},
               {"text": "done", "tool_calls": []}]

    def fake(cmd, **kw):
        with open(cmd[cmd.index("--system-prompt-file") + 1], encoding="utf-8") as fh:
            calls.append({"cmd": cmd, "system": fh.read(), "input": kw["input"]})
        out = {"is_error": False, "structured_output": replies[len(calls) - 1], "result": "{}",
               "usage": {"input_tokens": 1, "output_tokens": 1}}
        return subprocess.CompletedProcess([], 0, json.dumps(out), "")

    p = ClaudeCliProvider(_cfg())
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        first = p.call_model(CliClient("claude"), conv, [], tool_specs=[TOOL])
        conv.append(first.message.clone())
        conv.append(Message(role=MessageRole.TOOL, content="ok", tool_call_id=first.message.tool_calls[0].id,
                            metadata={"tool_name": "write_file"}))
        p.call_model(CliClient("claude"), conv, [], tool_specs=[TOOL])
    p.close()
    one, two = calls
    for text in (FE_ROLE, FE_DESC, FE_RULE):
        assert text in one["system"]  # static part: the (prompt-cached) system prompt
        assert text not in one["input"] and text not in two["input"]
    assert one["system"] == two["system"]
    assert "--resume" in two["cmd"] and TASK not in two["input"]  # resumed step sends only the new messages


def test_codex_prompt_carries_skill_body_once_in_the_stable_prefix(monkeypatch, tmp_path):
    conv = _member_conversation(monkeypatch, tmp_path)
    _tool_step(conv, "c1")
    _tool_step(conv, "c2")
    seen = {}

    def fake(cmd, **kw):
        seen["prompt"] = kw["input"]
        with open(cmd[cmd.index("-o") + 1], "w", encoding="utf-8") as fh:
            json.dump({"text": "done", "tool_calls": []}, fh)
        return subprocess.CompletedProcess([], 0, "", "")

    p = CodexCliProvider(_cfg())
    with patch("agentdev.connections.cli_auth.run_capture", side_effect=fake):
        p.call_model(CliClient("codex"), conv, [], tool_specs=[TOOL])
    prompt = seen["prompt"]
    assert prompt.count(FE_RULE) == 1 and FE_ROLE in prompt and FE_DESC in prompt
    assert prompt.index(FE_RULE) < prompt.index(TASK)  # before the conversation: a cacheable prefix
    assert flatten_conversation(conv, build_tool_preamble([TOOL], True)).count(FE_RULE) == 1
