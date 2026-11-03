"""Workflow assistant: YAML reference, system prompt and chat turns."""

import json
import re
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from agentdev.api.services import workflow_assistant as wa
from agentdev.api.services import workflow_assistant_prompt as prompt_mod
from agentdev.api.services.workflow_assistant_prompt import build_system_prompt, load_context
from agentdev.api.services.workflow_lab import static_check_data
from agentdev.connections import autobind
from agentdev.runtime.node.agent import account_fallback
from agentdev.runtime.node.agent.providers.cli_cancel import current_cancel_event

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


# ---------------------------------------------------------------------------- chat turn

VALID_YAML = """\
version: 0.4.0
graph:
  id: tong_dai
  start: [Frontend]
  end: [Bug Fixer]
  nodes:
    - id: Frontend
      type: agent
      config: {provider: anthropic, name: claude-sonnet-5-5, role: Build the UI}
    - id: Bug Fixer
      type: agent
      config: {provider: anthropic, name: claude-sonnet-5-5, role: Fix bugs}
  edges:
    - {from: Frontend, to: Bug Fixer}
"""
# check_config rejects an edge to a node that does not exist.
BROKEN_YAML = VALID_YAML.replace("to: Bug Fixer}", "to: Ghost}")


@pytest.fixture()
def turn_env(tmp_path, monkeypatch):
    """Workflows in ``tmp_path``, light prompt catalogs, and account binding that always succeeds."""
    monkeypatch.setattr(wa, "YAML_DIR", tmp_path)
    monkeypatch.setattr(prompt_mod, "YAML_DIR", tmp_path)
    monkeypatch.setattr(wa, "load_context", lambda: {
        "existing_files": sorted(p.name for p in tmp_path.glob("*.yaml")),
        "skills": [], "tools": [], "models": {"anthropic": ["claude-sonnet-5-5"], "openai": ["gpt-6.1-sol"]},
    })
    monkeypatch.setattr(autobind, "bind_default_connections", lambda data, env: None)
    return tmp_path


def _reply(reply="ok", proposal=None, quick=()):
    return json.dumps({"reply": reply, "quick_replies": list(quick), "proposal": proposal})


def _proposal(yaml_text=VALID_YAML, filename="tong_dai.yaml", kind="create"):
    return {"kind": kind, "filename": filename, "yaml": yaml_text}


class FakeCall:
    """Injected model call returning the scripted texts in order (the last one repeats)."""

    def __init__(self, *texts):
        self.texts = list(texts)
        self.calls = []

    def __call__(self, system, messages):
        self.calls.append((system, [dict(m) for m in messages]))
        return self.texts[min(len(self.calls) - 1, len(self.texts) - 1)]


def _turn(call, text="tạo quy trình tổng đài", workflow=None, messages=None, request_id="r1"):
    return wa.run_turn(vendor="anthropic", workflow=workflow,
                       messages=messages or [{"role": "user", "content": text}],
                       pending_yaml=None, request_id=request_id, call=call)


def test_parse_plain_json():
    out = wa.parse_model_output(_reply("chào", quick=["A", "B"]))
    assert out == {"reply": "chào", "quick_replies": ["A", "B"], "proposal": None}


def test_parse_fenced_json_with_prose():
    text = "Đây là kết quả:\n```json\n" + _reply("xin chào", _proposal()) + "\n```\nHết."
    out = wa.parse_model_output(text)
    assert out["reply"] == "xin chào"
    assert out["proposal"]["filename"] == "tong_dai.yaml"


def test_parse_non_json_becomes_reply():
    text = "  Chỉ là văn bản thường, không có JSON.  \n"
    out = wa.parse_model_output(text)
    assert out["proposal"] is None
    assert out["reply"] == text.strip()


def test_question_turn_has_no_proposal(turn_env):
    call = FakeCall(_reply("Quy trình tên gì?", quick=["Tổng đài", "Khác"]))
    out = _turn(call)
    assert out["proposal"] is None
    assert out["reply"] == "Quy trình tên gì?"
    assert out["quick_replies"] == ["Tổng đài", "Khác"]
    assert out["validation_errors"] == []
    assert len(call.calls) == 1


def test_valid_create_proposal(turn_env):
    out = _turn(FakeCall(_reply("Đây là bản đề xuất", _proposal())))
    proposal = out["proposal"]
    assert proposal["kind"] == "create"
    assert proposal["filename"] == "tong_dai.yaml"
    assert proposal["yaml"] == VALID_YAML
    assert proposal["checks"]["status"] != "fail"
    assert proposal["base_hash"] is None
    assert proposal["diff_summary"]["nodes_added"] == ["Frontend", "Bug Fixer"]


def test_accounts_fail_does_not_fail_the_proposal(turn_env, monkeypatch):
    def no_account(data, env):
        raise RuntimeError("No signed-in account can run this agent")

    monkeypatch.setattr(autobind, "bind_default_connections", no_account)
    call = FakeCall(_reply("ok", _proposal()))
    out = _turn(call)
    assert len(call.calls) == 1
    proposal = out["proposal"]
    assert proposal is not None
    assert proposal["warnings"] == []  # check results stay in ``checks``
    accounts = next(c for c in proposal["checks"]["checks"] if c["id"] == "accounts")
    assert accounts["status"] == "fail"
    assert out["validation_errors"] == []


def test_repair_loop_fixes_on_second_try(turn_env):
    call = FakeCall(_reply("v1", _proposal(BROKEN_YAML)), _reply("v2", _proposal()))
    out = _turn(call)
    assert out["proposal"] is not None and out["reply"] == "v2"
    assert len(call.calls) == 2
    repair = call.calls[1][1][-1]
    assert repair["role"] == "user"
    assert repair["content"].startswith("Your proposal failed validation:")
    assert "Ghost" in repair["content"]
    assert repair["content"].endswith("Return the corrected full JSON.")
    assert call.calls[1][1][-2] == {"role": "assistant", "content": call.texts[0]}


def test_repair_loop_gives_up_after_two_repairs(turn_env):
    call = FakeCall(_reply("vẫn sai", _proposal(BROKEN_YAML)))
    out = _turn(call)
    assert len(call.calls) == 3
    assert out["proposal"] is None
    assert out["reply"] == "vẫn sai"
    assert len(out["validation_errors"]) == 1 and "Ghost" in out["validation_errors"][0]


def test_create_name_taken_is_repaired(turn_env):
    (turn_env / "software_company.yaml").write_text(VALID_YAML, encoding="utf-8")
    call = FakeCall(_reply("v1", _proposal(filename="software_company.yaml")), _reply("v2", _proposal()))
    out = _turn(call)
    assert len(call.calls) == 2
    assert "software_company.yaml" in call.calls[1][1][-1]["content"]
    assert out["proposal"]["filename"] == "tong_dai.yaml"


def test_invalid_filename_is_repaired(turn_env):
    call = FakeCall(_reply("v1", _proposal(filename="../x.yaml")), _reply("v2", _proposal()))
    out = _turn(call)
    assert len(call.calls) == 2
    assert "../x.yaml" in call.calls[1][1][-1]["content"]
    assert out["proposal"]["filename"] == "tong_dai.yaml"


def test_yml_extension_is_repaired(turn_env):
    call = FakeCall(_reply("v1", _proposal(filename="tong_dai.yml")), _reply("v2", _proposal()))
    out = _turn(call)
    assert len(call.calls) == 2
    assert out["proposal"]["filename"] == "tong_dai.yaml"


def _edited_yaml():
    data = yaml.safe_load(VALID_YAML)
    nodes = data["graph"]["nodes"]
    nodes[1]["config"]["role"] = "Fix every bug, then write tests"
    nodes.append({"id": "QA", "type": "agent",
                  "config": {"provider": "anthropic", "name": "claude-sonnet-5-5", "role": "Test the UI"}})
    data["graph"]["edges"] = [{"from": "Frontend", "to": "QA"}, {"from": "QA", "to": "Bug Fixer"}]
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def test_edit_proposal_diff_and_warnings(turn_env):
    file_text = VALID_YAML.replace("\n", "\r\n")
    (turn_env / "tong_dai.yaml").write_bytes(file_text.encode("utf-8"))
    call = FakeCall(_reply("Đã thêm QA", _proposal(_edited_yaml(), kind="edit")))
    out = _turn(call, workflow="tong_dai.yaml", messages=[
        {"role": "user", "content": "giải thích quy trình"},
        {"role": "assistant", "content": "..."},
        {"role": "user", "content": "thêm QA sau Frontend"},
    ])
    proposal = out["proposal"]
    assert proposal["kind"] == "edit"
    assert "Bug Fixer" in proposal["warnings"]
    assert "Frontend" not in proposal["warnings"]
    assert proposal["base_hash"] == wa.content_hash(file_text)
    assert proposal["diff_summary"]["nodes_added"] == ["QA"]
    assert {"id": "Bug Fixer", "fields": ["config.role"]} in proposal["diff_summary"]["nodes_changed"]
    assert "id: tong_dai" in call.calls[0][0]  # the saved workflow is in the system prompt


def test_edit_kind_forced_for_workflow_context(turn_env):
    (turn_env / "tong_dai.yaml").write_text(VALID_YAML, encoding="utf-8")
    same = _turn(FakeCall(_reply("ok", _proposal(_edited_yaml()))), workflow="tong_dai.yaml")
    assert same["proposal"]["kind"] == "edit"
    assert same["proposal"]["base_hash"] == wa.content_hash(VALID_YAML)

    other = _turn(FakeCall(_reply("ok", _proposal(_edited_yaml(), filename="tong_dai_v2.yaml"))),
                  workflow="tong_dai.yaml")
    assert other["proposal"]["kind"] == "create"
    assert other["proposal"]["base_hash"] is None


def test_edit_of_another_file_is_repaired(turn_env):
    (turn_env / "tong_dai.yaml").write_text(VALID_YAML, encoding="utf-8")
    call = FakeCall(_reply("v1", _proposal(filename="other.yaml", kind="edit")),
                    _reply("v2", _proposal(kind="edit")))
    out = _turn(call, workflow="tong_dai.yaml")
    assert len(call.calls) == 2
    assert out["proposal"]["kind"] == "edit"


def test_quota_error_maps_to_code(turn_env):
    calls = []

    def call(system, messages):
        calls.append(1)
        raise account_fallback.QuotaExceededError("You've hit your usage limit")

    with pytest.raises(wa.AssistantError) as info:
        _turn(call)
    assert info.value.code == "quota_exhausted"
    assert len(calls) == 1


def test_timeout_and_provider_errors_map_to_codes(turn_env):
    from agentdev.runtime.node.agent.providers._cli_common import CliTimeoutError

    def raiser(exc):
        def call(system, messages):
            raise exc
        return call

    for exc, code in ((CliTimeoutError("timed out"), "timeout"), (RuntimeError("boom"), "provider_error")):
        with pytest.raises(wa.AssistantError) as info:
            _turn(raiser(exc))
        assert info.value.code == code


def _history(count, first_role="user"):
    roles = ("user", "assistant") if first_role == "user" else ("assistant", "user")
    messages = [{"role": roles[i % 2], "content": f"m{i}"} for i in range(count)]
    messages[-1]["role"] = "user"
    return messages


def test_history_trimmed(turn_env):
    messages = _history(50)
    call = FakeCall(_reply())
    _turn(call, messages=messages)
    assert call.calls[0][1] == [messages[0]] + messages[-24:]


def test_history_under_limit_untouched(turn_env):
    messages = _history(30)
    call = FakeCall(_reply())
    _turn(call, messages=messages)
    assert call.calls[0][1] == messages


def test_history_trim_keeps_first_user_message_after_greeting(turn_env):
    messages = _history(50, first_role="assistant")
    call = FakeCall(_reply())
    _turn(call, messages=messages)
    assert call.calls[0][1] == [messages[1]] + messages[-24:]


def test_parse_json_after_prose_with_braces():
    text = 'Tip: use {name} as a placeholder. ' + _reply("đây", quick=["A"]) + " Done."
    out = wa.parse_model_output(text)
    assert out["reply"] == "đây"
    assert out["quick_replies"] == ["A"]


def test_duplicate_request_id_in_flight_is_bad_request(turn_env):
    started, release = threading.Event(), threading.Event()

    def slow(system, messages):
        started.set()
        release.wait(5)
        return _reply()

    thread = threading.Thread(target=lambda: _turn(slow, request_id="dup"))
    thread.start()
    try:
        assert started.wait(5)
        with pytest.raises(wa.AssistantError) as info:
            _turn(FakeCall(_reply()), request_id="dup")
        assert info.value.code == "bad_request"
    finally:
        release.set()
        thread.join(5)
    assert _turn(FakeCall(_reply()), request_id="dup")["reply"] == "ok"  # free again once it ended


def test_unknown_vendor_bad_request(turn_env):
    with pytest.raises(wa.AssistantError) as info:
        wa.run_turn(vendor="gemini", workflow=None, messages=[{"role": "user", "content": "x"}],
                    pending_yaml=None, request_id="r", call=FakeCall(_reply()))
    assert info.value.code == "bad_request"


def test_cancel_sets_event(turn_env):
    started = threading.Event()

    def call(system, messages):
        event = current_cancel_event()
        started.set()
        assert event is not None and event.wait(5)
        return _reply()

    result = {}

    def worker():
        try:
            _turn(call, request_id="cancel-me")
        except wa.AssistantError as exc:
            result["code"] = exc.code

    thread = threading.Thread(target=worker)
    thread.start()
    assert started.wait(5)
    assert wa.cancel("cancel-me") is True
    thread.join(5)
    assert result == {"code": "cancelled"}
    assert wa.cancel("cancel-me") is False  # unregistered once the turn ended


def test_content_hash_ignores_crlf():
    assert wa.content_hash("a\r\nb\n") == wa.content_hash("a\nb\n")
    assert len(wa.content_hash("x")) == 64


def test_list_providers(monkeypatch):
    from agentdev.connections import store as store_module

    def conn(cid, vendor, auth="cli"):
        return SimpleNamespace(id=cid, vendor=vendor, auth_type=auth, label=cid)

    conns = [conn("key", "openai", "api_key"), conn("claude-1", "anthropic"), conn("claude-2", "anthropic")]
    fake = SimpleNamespace(list=lambda: list(conns), default_connection=lambda: conns[2])
    monkeypatch.setattr(store_module, "get_store", lambda: fake)
    monkeypatch.setattr(account_fallback, "default_model_for", lambda c: f"{c.id}-model")
    assert wa.list_providers() == [
        {"vendor": "anthropic", "label": "Claude", "connection_id": "claude-2", "model": "claude-2-model",
         "available": True},
        {"vendor": "openai", "label": "Codex", "connection_id": None, "model": None, "available": False},
    ]


def test_not_signed_in(turn_env, monkeypatch):
    monkeypatch.setattr(wa, "list_providers", lambda: [
        {"vendor": "anthropic", "label": "Claude", "connection_id": None, "model": None, "available": False}])
    with pytest.raises(wa.AssistantError) as info:
        wa.run_turn(vendor="anthropic", workflow=None, messages=[{"role": "user", "content": "x"}],
                    pending_yaml=None, request_id="r")
    assert info.value.code == "not_signed_in"
