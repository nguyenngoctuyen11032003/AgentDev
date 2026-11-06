"""Vetted workflow patterns, their picker, and the deterministic pre-card fixes and lint."""

import json

import pytest
import yaml

from agentdev.api.services import workflow_assistant as wa
from agentdev.api.services import workflow_assistant_prompt as prompt_mod
from agentdev.api.services.workflow_lab import static_check_data
from agentdev.api.services.workflow_patterns import load_patterns, pattern_fragment, pick_pattern, proposal_lint
from agentdev.connections import autobind, catalog

PATTERNS = load_patterns()
KNOWN_MODELS = {m for v in catalog.VENDORS.values() for m in v.models}


def test_six_patterns_with_headers():
    assert {p.id for p in PATTERNS} == {"generic", "dev_team", "video", "marketing", "data", "support"}
    for p in PATTERNS:
        assert p.keywords and p.when and p.slots, p.id
        assert p.yaml.startswith(f"# id: {p.id}\n")


@pytest.mark.parametrize("pattern", PATTERNS, ids=lambda p: p.id)
def test_pattern_passes_static_check_and_lint(pattern):
    data = yaml.safe_load(pattern.yaml)
    report = static_check_data(data)
    assert [c for c in report["checks"] if c["status"] == "fail" and c["id"] != "accounts"] == []
    for node in data["graph"]["nodes"]:
        if node["type"] == "agent":
            assert node["config"]["name"] in KNOWN_MODELS
    assert proposal_lint.unknown_models(data) == []
    assert proposal_lint.unguarded_cycles(data) == []
    assert proposal_lint.gates_missing_auto_answer(data) == []
    assert not proposal_lint.triage_missing(data)
    assert proposal_lint.estimate_seconds(data) > 0
    assert "regex: [\"" not in pattern.yaml  # regexes are single-quoted


@pytest.mark.parametrize("text, expected", [
    ("làm đội video", "video"),
    ("Tôi muốn làm kịch bản TikTok", "video"),
    ("I want a software team to build a web app", "dev_team"),
    ("đội chăm sóc khách hàng, xử lý hoàn tiền", "support"),
    ("customer support with refund approval", "support"),
    ("phân tích dữ liệu excel và báo cáo", "data"),
    ("chiến dịch marketing cho shop", "marketing"),
    ("xin chào", None),
    ("", None),
])
def test_pick_pattern(text, expected):
    picked = pick_pattern(text)
    assert (picked.id if picked else None) == expected


def test_pattern_goes_to_turn_context_not_the_stable_prefix():
    kwargs = dict(current_yaml=None, current_name=None, pending_yaml=None, existing_files=[])
    video = pick_pattern("làm đội video")
    ctx = prompt_mod.turn_context(user_text="làm đội video", **kwargs)
    assert "## Pattern `video`" in ctx and "Script Approval" in ctx
    assert pattern_fragment(video).strip().splitlines()[1] in ctx
    stable = prompt_mod.stable_prefix(skills=[], tools=[], models={})
    assert "Script Approval" not in stable
    # no match, or an open workflow: nothing injected
    assert "## Pattern" not in prompt_mod.turn_context(user_text="xin chào", **kwargs)
    assert "## Pattern" not in prompt_mod.turn_context(
        user_text="làm đội video", **{**kwargs, "current_yaml": "graph: {}\n"})


# ---------------------------------------------------------------------------- lint helpers


def _wf(nodes, edges, start="A", end="A"):
    return {"version": "0.4.0", "vars": {}, "graph": {"id": "t", "start": [start], "end": [end],
                                                         "nodes": nodes, "edges": edges}}


def _agent(id, model, **config):
    return {"id": id, "type": "agent", "description": id,
            "config": {"provider": "anthropic", "name": model, "role": "r", **config}}


def test_model_tiers():
    assert proposal_lint.model_tier("claude-haiku-5-5") == "small"
    assert proposal_lint.model_tier("claude-sonnet-5-5") == "mid"
    assert proposal_lint.model_tier("claude-opus-5-5") == "top"
    assert proposal_lint.model_tier("gpt-6.1-sol") == "top"
    assert proposal_lint.model_tier("gemini-3-flash-preview") == "small"


def test_speed_estimate_math():
    chain = _wf([_agent("A", "claude-haiku-5-5"), _agent("B", "claude-sonnet-5-5"), _agent("C", "claude-opus-5-5")],
                [{"from": "A", "to": "B"}, {"from": "B", "to": "C"}], end="C")
    assert proposal_lint.estimate_seconds(chain) == 15 + 40 + 90
    # parallel branches count once: longest branch wins
    fan = _wf([_agent("A", "claude-haiku-5-5"), _agent("B", "claude-sonnet-5-5"), _agent("C", "claude-haiku-5-5")],
              [{"from": "A", "to": "B"}, {"from": "A", "to": "C"}])
    assert proposal_lint.estimate_seconds(fan) == 15 + 40
    # a loop adds 30 s once: the cycle's agents plus the loop surcharge
    loop = _wf([_agent("A", "claude-sonnet-5-5"), _agent("R", "claude-haiku-5-5")],
               [{"from": "A", "to": "R"}, {"from": "R", "to": "A"}])
    assert proposal_lint.estimate_seconds(loop) == 40 + 15 + 30
    check = proposal_lint.speed_check(chain)
    assert check["id"] == "speed" and check["estimated_seconds"] == 145 and check["status"] == "pass"
    slow = _wf([_agent(n, "claude-opus-5-5") for n in "ABC"], [{"from": "A", "to": "B"}, {"from": "B", "to": "C"}])
    assert proposal_lint.speed_check(slow)["status"] == "warn"


def test_unguarded_cycle_and_gate_lint():
    cyc = _wf([_agent("A", "claude-sonnet-5-5"), _agent("R", "claude-haiku-5-5")],
              [{"from": "A", "to": "R"}, {"from": "R", "to": "A"}])
    assert proposal_lint.unguarded_cycles(cyc) == [["R", "A"]] or proposal_lint.unguarded_cycles(cyc) == [["A", "R"]]
    cyc["graph"]["nodes"].append({"id": "G", "type": "loop_counter", "config": {"max_iterations": 2}})
    cyc["graph"]["edges"] += [{"from": "R", "to": "G"}, {"from": "G", "to": "A"}]
    assert proposal_lint.unguarded_cycles(cyc) == []
    gate = _wf([{"id": "H", "type": "human", "config": {"description": "x"}}, _agent("A", "claude-haiku-5-5")],
               [{"from": "H", "to": "A", "condition": {"type": "keyword", "config": {
                   "regex": ['^\\s*OK\\s*$'], "case_sensitive": False}}}], start="H")
    assert proposal_lint.gates_missing_auto_answer(gate) == ["H"]


def test_downgrade_and_case_sensitive():
    data = _wf([_agent("Lead", "claude-opus-5-5", team={"enabled": True, "members": ["QA Tester"]}),
                _agent("QA Tester", "claude-opus-5-5", params={"effort": "high"}),
                _agent("Writer", "claude-opus-5-5")],
               [{"from": "Writer", "to": "QA Tester", "condition": {"type": "keyword", "config": {"any": ["x"]}}}])
    notes = proposal_lint.downgrade_cheap_nodes(data)
    nodes = {n["id"]: n["config"] for n in data["graph"]["nodes"]}
    assert nodes["QA Tester"]["name"] == "claude-haiku-5-5" and nodes["QA Tester"]["params"]["effort"] == "low"
    assert nodes["Lead"]["name"] == "claude-opus-5-5" and nodes["Writer"]["name"] == "claude-opus-5-5"
    assert len(notes) == 1
    assert proposal_lint.add_case_sensitive(data) == 1
    assert data["graph"]["edges"][0]["condition"]["config"]["case_sensitive"] is True


# ---------------------------------------------------------------------------- through run_turn


@pytest.fixture
def turn_env(tmp_path, monkeypatch):
    monkeypatch.setattr(wa, "YAML_DIR", tmp_path)
    monkeypatch.setattr(prompt_mod, "YAML_DIR", tmp_path)
    monkeypatch.setattr(wa, "load_context", lambda: {"existing_files": [], "skills": [], "tools": [],
                                                    "models": {"anthropic": ["claude-sonnet-5-5"]}})
    monkeypatch.setattr(autobind, "bind_default_connections", lambda data, env: None)
    return tmp_path


class Fake:
    def __init__(self, *texts):
        self.texts, self.calls = list(texts), []

    def __call__(self, system, messages):
        self.calls.append((system, messages))
        return self.texts[min(len(self.calls) - 1, len(self.texts) - 1)]


def _run(call, text, vendor="anthropic"):
    return wa.run_turn(vendor=vendor, workflow=None, messages=[{"role": "user", "content": text}],
                       pending_yaml=None, request_id="p1", call=call)


def _reply(yaml_text, filename="doi_video.yaml"):
    return json.dumps({"intent": "propose", "reply": "Bản nháp", "quick_replies": [],
                       "proposal": {"kind": "create", "filename": filename, "yaml": yaml_text}})


def test_vague_video_request_gets_a_pattern_and_a_first_turn_proposal(turn_env):
    video = next(p for p in PATTERNS if p.id == "video")
    call = Fake(_reply(video.yaml))
    out = _run(call, "làm đội video")
    assert len(call.calls) == 1  # no repair, no extra question round trip
    assert "## Pattern `video`" in call.calls[0][1][-1]["content"]
    proposal = out["proposal"]
    assert proposal is not None and out["validation_errors"] == []
    # one speed estimate per proposal: the static check's critical_path (no second, disagreeing "speed")
    ids = [c["id"] for c in proposal["checks"]["checks"]]
    assert "speed" not in ids and ids.count("critical_path") == 1
    speed = next(c for c in proposal["checks"]["checks"] if c["id"] == "critical_path")
    assert speed["estimated_seconds"] == proposal_lint.estimate_seconds(yaml.safe_load(proposal["yaml"])) > 0


def test_unknown_model_is_substituted_without_a_repair_call(turn_env):
    data = yaml.safe_load(next(p for p in PATTERNS if p.id == "generic").yaml)
    data["graph"]["nodes"][1]["config"]["name"] = "claude-sonnet-9-9"
    call = Fake(_reply(yaml.safe_dump(data), "gen.yaml"))
    out = _run(call, "tạo quy trình")
    assert len(call.calls) == 1
    proposal = out["proposal"]
    assert "claude-sonnet-9-9" not in proposal["yaml"]
    assert any("claude-sonnet-9-9" in w and "claude-sonnet-5-5" in w for w in proposal["warnings"])


def test_create_downgrades_top_model_reviewer(turn_env):
    data = yaml.safe_load(next(p for p in PATTERNS if p.id == "generic").yaml)
    reviewer = next(n for n in data["graph"]["nodes"] if n["id"] == "Reviewer")
    reviewer["config"]["name"] = "claude-opus-5-5"
    reviewer["config"]["params"] = {"effort": "high"}
    out = _run(Fake(_reply(yaml.safe_dump(data), "gen.yaml")), "tạo quy trình")
    saved = yaml.safe_load(out["proposal"]["yaml"])
    reviewer = next(n for n in saved["graph"]["nodes"] if n["id"] == "Reviewer")
    assert reviewer["config"]["name"] == "claude-haiku-5-5" and reviewer["config"]["params"]["effort"] == "low"
    assert any("Reviewer" in w for w in out["proposal"]["warnings"])


# ---------------------------------------------------------------------------- shared graph logic


def test_lint_and_lab_share_one_graph_implementation():
    from agentdev.api.services import workflow_lab
    from agentdev.api.services.workflow_patterns import graph_analysis

    assert proposal_lint.model_tier is workflow_lab.model_tier is graph_analysis.model_tier
    assert proposal_lint.edge_condition_matches is workflow_lab.edge_condition_matches
    # "gemini" is not "mini"; "pro" is a top model; "mini" alone is small
    assert graph_analysis.model_tier("gemini-3.1-pro-preview") == "top"
    assert graph_analysis.model_tier("gpt-5-mini") == "small"
    assert graph_analysis.model_tier("gpt-6.1-terra") == "mid"


def test_none_only_keyword_condition_matches_like_the_runtime():
    from agentdev.entity.configs.edge.edge_condition import KeywordEdgeConditionConfig
    from agentdev.runtime.edge.conditions.keyword_manager import KeywordEdgeConditionManager

    cond = {"type": "keyword", "config": {"none": ["Rejected"], "case_sensitive": True}}
    manager = KeywordEdgeConditionManager.__new__(KeywordEdgeConditionManager)
    cfg = KeywordEdgeConditionConfig.from_dict(cond["config"], path="c")
    manager.any_keywords, manager.regex_patterns = cfg.any_keywords, cfg.regex_patterns
    manager.processed_none, manager.processed_any = cfg.none_keywords, cfg.any_keywords
    manager.compiled_regex, manager.case_sensitive = [], True
    for text in ("[Automatic answer] Approved", "Rejected"):
        assert proposal_lint.edge_condition_matches(cond, text) == manager._evaluate(text)
    gate = _wf([{"id": "H", "type": "human", "config": {"description": "x"}}, _agent("A", "claude-haiku-5-5")],
               [{"from": "H", "to": "A", "condition": cond}], start="H", end="A")
    assert proposal_lint.gates_missing_auto_answer(gate) == []


def test_lint_speed_matches_lab_critical_path():
    lead = _agent("Lead", "claude-sonnet-5-5", team={"enabled": True, "members": ["W"]})
    data = _wf([lead, _agent("W", "claude-haiku-5-5"), _agent("Self", "claude-haiku-5-5")],
               [{"from": "Lead", "to": "Self"}, {"from": "Self", "to": "Self"}], start="Lead", end="Self")
    lab = next(c for c in static_check_data(data)["checks"] if c["id"] == "critical_path")
    assert lab["estimated_seconds"] == proposal_lint.estimate_seconds(data) == 40 + 15 + 15 + 30
    assert proposal_lint.lint(data)[1] == []


def test_full_system_prompt_includes_the_matched_pattern():
    prompt = prompt_mod.build_system_prompt(current_yaml=None, current_name=None, pending_yaml=None,
                                            existing_files=[], skills=[], tools=[], models={},
                                            user_text="làm đội video")
    assert "## Pattern `video`" in prompt


def test_team_estimate_spreads_members_over_parallel_lanes():
    from agentdev.api.services.workflow_patterns.graph_analysis import Graph, TIER_SECONDS

    def agent(nid, model, team=None):
        cfg = {"name": model}
        if team:
            cfg["team"] = team
        return {"id": nid, "type": "agent", "config": cfg}

    members = [f"m{i}" for i in range(4)]
    nodes = [agent(m, "claude-sonnet-5-5") for m in members]

    def lead_seconds(max_parallel):
        lead = agent("lead", "claude-sonnet-5-5", {"enabled": True, "members": members, "max_parallel": max_parallel})
        g = Graph.from_workflow({"graph": {"nodes": [lead, *nodes], "edges": [], "start": ["lead"]}})
        return g._agent_cost(g.nodes["lead"])[0]

    mid = TIER_SECONDS["mid"]
    assert lead_seconds(1) == mid + 4 * mid  # one member at a time
    assert lead_seconds(4) == mid + mid  # all four at once: the slowest member
    assert lead_seconds(3) == mid + -(-4 * mid // 3)


# --- paid gates an edit weakens (warning, never an error) ------------------------------------------------------

def _paid_flow(paid=True, approve_any=("tạo video",), with_gate=True):
    agent = {"provider": "anthropic", "name": "claude-haiku-5-5", "role": "r"}
    nodes = [{"id": "Writer", "type": "agent", "description": "d", "config": dict(agent)},
             {"id": "Video Renderer", "type": "agent", "description": "d", "config": dict(agent)},
             {"id": "Render Skipped", "type": "agent", "description": "d", "config": dict(agent)}]
    edges = [{"from": "Writer", "to": "Render Skipped"}]
    if with_gate:
        gate = {"description": "Render costs money: type 'tạo video' to render"}
        if paid:
            gate["paid"] = True
        nodes.insert(1, {"id": "Render Approval", "type": "human", "description": "d", "config": gate})
        cond = lambda kind, words: {"type": "keyword", "config": {kind: list(words), "case_sensitive": False}}
        edges = [{"from": "Writer", "to": "Render Approval"},
                 {"from": "Render Approval", "to": "Video Renderer", "condition": cond("any", approve_any)},
                 {"from": "Render Approval", "to": "Render Skipped", "condition": cond("none", ("tạo video",))}]
    return {"graph": {"id": "v", "description": "d", "start": ["Writer"], "end": ["Video Renderer", "Render Skipped"],
                      "nodes": nodes, "edges": edges}}


def test_paid_gate_changes_flag_unmarked_removed_and_silence_reaching_paid_step():
    old = _paid_flow()
    assert proposal_lint.paid_gate_changes(old, _paid_flow()) == []
    assert proposal_lint.paid_gate_changes(old, _paid_flow(paid=False)) == [
        {"node": "Render Approval", "kind": "unmarked"}]
    assert proposal_lint.paid_gate_changes(old, _paid_flow(with_gate=False)) == [
        {"node": "Render Approval", "kind": "removed"}]
    # "Approved" (the automatic answer) / the no-reply text now take the paid branch.
    weakened = proposal_lint.paid_gate_changes(old, _paid_flow(approve_any=("tạo video", "proceed")))
    assert weakened == [{"node": "Render Approval", "kind": "silence_reaches", "to": ["Video Renderer"]}]
    assert proposal_lint.paid_gate_changes(None, _paid_flow(paid=False)) == []  # a new file has nothing to weaken


def test_edit_removing_paid_flag_is_a_warning_with_a_code(tmp_path, monkeypatch):
    monkeypatch.setattr(wa, "YAML_DIR", str(tmp_path))
    old = _paid_flow()
    saved = yaml.safe_dump(old, allow_unicode=True, sort_keys=False)
    new = yaml.safe_dump(_paid_flow(paid=False), allow_unicode=True, sort_keys=False)
    proposal, errors = wa._check_proposal({"kind": "edit", "filename": "v.yaml", "yaml": new}, "v.yaml", saved, old,
                                          ["bỏ cờ paid"])
    assert errors == [] and proposal is not None
    check = next(c for c in proposal["checks"]["checks"] if c["id"] == "paid_gate_removed")
    assert check["status"] == "warn" and check["code"] == "PAID_GATE_REMOVED"
    assert check["items"] == [{"node": "Render Approval", "kind": "unmarked"}]
    assert proposal["checks"]["status"] in ("warn", "fail")
