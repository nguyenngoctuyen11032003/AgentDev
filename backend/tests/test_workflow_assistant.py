"""Workflow assistant: YAML reference, system prompt and chat turns."""

import re
from pathlib import Path

import pytest
import yaml

from agentdev.api.services import workflow_assistant_prompt as prompt_mod
from agentdev.api.services.workflow_assistant_prompt import build_system_prompt, load_context
from agentdev.api.services.workflow_lab import static_check_data

REPO = Path(__file__).resolve().parents[2]
REFERENCE = REPO / "backend" / "agentdev" / "api" / "services" / "workflow_assistant_reference.md"
BRAINSTORMING = REPO / "workspace" / "skills" / "brainstorming" / "SKILL.md"


def _prompt(**overrides):
    kwargs = dict(
        current_yaml=None,
        current_name=None,
        pending_yaml=None,
        existing_files=["software_company.yaml", "content_studio.yaml"],
        skills=[("spec-driven-development", "Write a spec first"), ("playwright-cli", "Drive a browser")],
        tools=[("save_file", "Persist data to a workspace file"), ("web_search", "Search the web")],
        models={"anthropic": ["claude-opus-5-5", "claude-sonnet-5-5"], "openai": ["gpt-6.1-sol"]},
    )
    kwargs.update(overrides)
    return build_system_prompt(**kwargs)


# ---------------------------------------------------------------------------- reference


def _yaml_blocks(text):
    return re.findall(r"^```yaml\n(.*?)^```", text, flags=re.MULTILINE | re.DOTALL)


def test_reference_examples_pass_static_check():
    blocks = _yaml_blocks(REFERENCE.read_text(encoding="utf-8"))
    assert len(blocks) == 2
    for block in blocks:
        report = static_check_data(yaml.safe_load(block))
        # ``accounts`` depends on the connections signed in on this machine.
        failed = [c for c in report["checks"] if c["status"] == "fail" and c["id"] != "accounts"]
        assert failed == [], failed


def test_reference_is_compact():
    lines = REFERENCE.read_text(encoding="utf-8").splitlines()
    assert 150 <= len(lines) <= 300


# ---------------------------------------------------------------------------- prompt


def test_prompt_includes_context():
    current = "version: 0.4.0\ngraph:\n  id: marker_current_workflow\n"
    prompt = _prompt(current_yaml=current, current_name="software_company.yaml")
    for name in ("spec-driven-development", "playwright-cli", "save_file", "web_search",
                 "software_company.yaml", "content_studio.yaml", "claude-opus-5-5", "gpt-6.1-sol"):
        assert name in prompt
    assert current in prompt
    assert REFERENCE.read_text(encoding="utf-8").strip() in prompt


def test_prompt_without_current_workflow_is_create_mode():
    prompt = _prompt()
    assert "marker_current_workflow" not in prompt
    assert "Bản đề xuất chưa áp dụng" not in prompt


def test_prompt_pending_yaml_section():
    pending = "version: 0.4.0\ngraph:\n  id: marker_pending_proposal\n"
    prompt = _prompt(pending_yaml=pending)
    section = prompt[prompt.index("Bản đề xuất chưa áp dụng"):]
    assert pending in section
    assert "continue from this proposal" in section


def test_prompt_brainstorming_override():
    prompt = _prompt()
    skill = BRAINSTORMING.read_text(encoding="utf-8").strip()
    assert skill in prompt
    after = prompt[prompt.index(skill) + len(skill):]
    for phrase in ("Do not write files, commit, or invoke other skills",
                   "one question per turn",
                   "Reply with a single JSON object"):
        assert phrase in after


def test_prompt_sections_in_order():
    prompt = _prompt(current_yaml="graph: {id: x}\n", current_name="x.yaml")
    markers = [
        "workflow architect",
        BRAINSTORMING.read_text(encoding="utf-8").strip()[:80],
        "Do not write files, commit, or invoke other skills",
        '"quick_replies"',
        "# AgentDev workflow YAML reference",
        "## Catalogs",
        "graph: {id: x}",
    ]
    positions = [prompt.index(m) for m in markers]
    assert positions == sorted(positions)


def test_load_context(tmp_path, monkeypatch):
    (tmp_path / "b_flow.yaml").write_text("graph: {}\n", encoding="utf-8")
    (tmp_path / "a_flow.yaml").write_text("graph: {}\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(prompt_mod, "YAML_DIR", tmp_path)
    monkeypatch.setattr(prompt_mod.skill_library, "list_skills", lambda: [
        {"name": "good", "description": "ok", "valid": True},
        {"name": "broken", "description": "", "valid": False},
    ])
    context = load_context()
    assert context["existing_files"] == ["a_flow.yaml", "b_flow.yaml"]
    assert context["skills"] == [("good", "ok")]
    assert "save_file" in dict(context["tools"])
    assert "claude-opus-5-5" in context["models"]["anthropic"]
    assert set(context["models"]) == {"anthropic", "openai"}
