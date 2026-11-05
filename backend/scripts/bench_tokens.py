"""Token benchmark: what the REAL engine sends to a model, per node, for a few fixed scenarios.

    cd backend
    uv run python -m scripts.bench_tokens --fake                       # zero cost, prompt structure + chars/4 estimates
    uv run python -m scripts.bench_tokens --fake --json                # JSON on stdout
    uv run python -m scripts.bench_tokens --fake --out docs/audit/     # write bench-tokens-<timestamp>.{json,md}
    uv run python -m scripts.bench_tokens --fake --baseline            # refresh docs/audit/bench-tokens-baseline-fake.md
    uv run python -m scripts.bench_tokens --real --only chat --max-runs 3 --max-usd 0.5   # spends tokens: see below

Relative ``--out`` paths are resolved against the repository root (not the current folder).

Scenarios (each is run through ``run_workflow``, i.e. the real graph executor and agent executor):
  chat      one agent, one chat turn
  followup_long  (opt-in) the same agent, 6 normal requests: shared_prefix_ratio between consecutive turns.
  followup  the same agent, 3 turns with growing history: a normal request, a short "ok", a normal request.
            History is built with the product's own ``make_turn`` / ``compose_follow_up_prompt``.
  team      Plan -> (Worker1, Worker2) -> Merge, every node with two skills ticked (preloaded into the prompt)

Per node it records input/output chars, estimated tokens (chars/4), the engine's real token / cache / cost
numbers when the provider reports them (real mode), model, duration. Per call it records the prompt
structure: system prompt, tool catalog, preloaded skills, history, and whether a volatile part (date, time,
id, temp path) sits in the static (cacheable) head of the prompt.

``--fake``: a fake provider (no model, no network, no cost). The prompt is measured as the Claude CLI
provider would flatten it (``split_conversation``), so the numbers are the size of what would be sent.
``--real``: logged-in CLI accounts only (the Connections page; never API keys), cheapest Claude model.
Hard ceilings: ``--max-runs`` (workflow runs, default 3) and ``--max-usd`` (default 0.5). The plan is refused
before anything runs when it needs more runs than ``--max-runs``; the engine's own ``run_limits.max_cost_usd``
is set on every run and the benchmark stops starting new runs once the spent total reaches ``--max-usd``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "docs" / "audit"
BASELINE_NAME = "bench-tokens-baseline-fake.md"
REAL_MODEL = "claude-haiku-5-5"  # cheapest of the Claude catalog (connections/catalog.py)
FAKE_MODEL = "fake-model"
SKILLS = ["context-efficiency", "writing-for-agents"]  # two small skills from workspace/skills

# Things that change from one request to the next. In the head of a prompt they break prompt-cache prefix reuse.
VOLATILE_PATTERNS = {
    "date_time": re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?\b"),
    "clock": re.compile(r"\b\d{1,2}:\d{2}:\d{2}\b"),
    "uuid": re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
    "long_hex_id": re.compile(r"\b[0-9a-f]{16,}\b", re.I),
    "run_id": re.compile(r"\b(?:sdk|bench|session|run)_[A-Za-z0-9_-]{6,}\b"),
    "temp_path": re.compile(r"(?:[A-Za-z]:\\|/)[^\s\"']*(?:[Tt]emp|tmp)[^\s\"']*"),
}


def est_tokens(chars: int) -> int:
    return (chars + 3) // 4


# --------------------------------------------------------------------------- prompt structure facts


def _system_text(conversation) -> str:
    from agentdev.entity.messages import MessageRole

    return "\n\n".join(m.text_content() for m in conversation if m.role == MessageRole.SYSTEM)


def _volatile_hits(text: str) -> List[Dict[str, Any]]:
    hits = []
    for kind, rx in VOLATILE_PATTERNS.items():
        for m in rx.finditer(text):
            hits.append({"kind": kind, "at": m.start(), "text": m.group(0)[:60]})
    return sorted(hits, key=lambda h: h["at"])


def prompt_facts(conversation, tool_specs) -> Dict[str, Any]:
    """Size and order of the parts of one model call, as the Claude CLI provider renders them."""
    from agentdev.api.services.conversation_turns import NEW_MESSAGE_HEADER
    from agentdev.entity.messages import MessageRole
    from agentdev.runtime.node.agent.providers._cli_common import build_tool_preamble, split_conversation
    from agentdev.runtime.node.agent.team import USER_RESPONSE_RULES
    from agentdev.runtime.node.executor.agent_executor import LOADED_SKILLS_HEADING

    system = _system_text(conversation)
    preamble = build_tool_preamble(list(tool_specs), True) if tool_specs else ""
    static, transcript = split_conversation(conversation, preamble)
    user_text = "\n\n".join(m.text_content() for m in conversation if m.role == MessageRole.USER)

    skills_at = system.find(LOADED_SKILLS_HEADING)
    rules_at = system.find(USER_RESPONSE_RULES[:60])
    skills_chars = 0
    skills_span = (0, 0)
    if skills_at >= 0:
        end = rules_at if rules_at > skills_at else len(system)
        skills_chars = end - skills_at
        skills_span = (skills_at, end)
    # Order of the system prompt's parts (by first position), to read the cache order at a glance.
    markers = {"profile(role/description)": 0, "loaded_skills": skills_at, "user_response_rules": rules_at}
    order = [name for name, pos in sorted(markers.items(), key=lambda kv: kv[1]) if pos >= 0]

    new_at = user_text.find(NEW_MESSAGE_HEADER)
    history_chars = new_at if new_at >= 0 else 0

    # Volatile parts: in the static head (system + tool catalog) they break the cache for everything after them.
    # Preloaded skill text is stable file content, so it is cut out of the scan.
    head_scan = system[: skills_span[0]] + system[skills_span[1]:] if skills_span[1] else system
    head_hits = _volatile_hits(head_scan + "\n" + preamble)
    history_hits = _volatile_hits(user_text[:history_chars]) if history_chars else []
    return {
        "input_chars": len(static) + len(transcript),
        "static_chars": len(static),
        "transcript_chars": len(transcript),
        "system_chars": len(system),
        "tool_catalog_chars": len(preamble),
        "tool_count": len(tool_specs or []),
        "skills_chars": skills_chars,
        "history_chars": history_chars,
        "user_chars": len(user_text),
        "system_order": order,
        "volatile_in_static_head": head_hits,
        "volatile_in_history": history_hits,
        "cache_breaking_order": bool(head_hits),
        "_static": static,
        "_prompt": static + "\n\n" + transcript,
    }


# --------------------------------------------------------------------------- call capture


class Capture:
    """Calls seen by the (fake or wrapped real) provider, in order."""

    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def reset(self) -> None:
        self.calls = []

    def add(self, node_id: str, model: str, facts: Dict[str, Any], out_chars: int, seconds: float) -> None:
        self.calls.append({"node": node_id, "model": model, "facts": facts, "output_chars": out_chars,
                           "duration_s": seconds})


CAPTURE = Capture()
FAKE_ANSWER_CHARS = {"Chat": 900, "Plan": 500, "Worker1": 700, "Worker2": 700, "Merge": 800}


def _filler(node_id: str, chars: int) -> str:
    base = f"[{node_id}] Benchmark answer text with a fixed length so token counts stay comparable between runs. "
    return (base * (chars // len(base) + 1))[:chars]


def make_fake_provider():
    from agentdev.runtime.node.agent import ModelResponse
    from agentdev.entity.messages import Message, MessageRole
    from agentdev.runtime.node.agent.providers._cli_common import record_token_usage
    from agentdev.utils.token_tracker import TokenUsage

    class FakeProvider:
        def __init__(self, config):
            self.config = config
            self.model_name = str(config.name)

        def create_client(self):
            return None

        def call_model(self, client, conversation, timeline, tool_specs=None, **kwargs):
            started = time.perf_counter()
            node_id = self.config.node_id
            facts = prompt_facts(conversation, tool_specs)
            answer = _filler(node_id, FAKE_ANSWER_CHARS.get(node_id, 600))
            CAPTURE.add(node_id, self.model_name, facts, len(answer), time.perf_counter() - started)
            record_token_usage(self, {"usage": {"input_tokens": est_tokens(facts["input_chars"]),
                                                "output_tokens": est_tokens(len(answer))}}, "fake")
            return ModelResponse(message=Message(role=MessageRole.ASSISTANT, content=answer))

        def extract_token_usage(self, response):
            usage = response.get("usage") or {}
            inp, out = int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
            return TokenUsage(input_tokens=inp, output_tokens=out, total_tokens=inp + out,
                              metadata={"estimated": True, "total_cost_usd": None})

    return FakeProvider


def make_capturing(real_cls):
    """The real provider, unchanged, plus a record of what each call sent."""

    class Capturing(real_cls):  # type: ignore[misc, valid-type]
        def call_model(self, client, conversation, timeline, tool_specs=None, **kwargs):
            started = time.perf_counter()
            facts = prompt_facts(conversation, tool_specs)
            response = super().call_model(client, conversation=conversation, timeline=timeline,
                                          tool_specs=tool_specs, **kwargs)
            out = response.message.text_content() if response and response.message else ""
            CAPTURE.add(self.config.node_id, str(self.model_name), facts, len(out), time.perf_counter() - started)
            return response

    return Capturing


def install_fake():
    """Patch the engine for a free fake run and return a callable that undoes every patch."""
    from agentdev.runtime.node.agent import ProviderRegistry
    from agentdev.runtime.node.executor import agent_executor as module
    from agentdev.utils.human_prompt import HumanPromptService, PromptResult

    orig_resolve = module.resolve_connection
    orig_get = ProviderRegistry.__dict__["get_provider"]
    orig_request = HumanPromptService.__dict__["request"]
    provider = make_fake_provider()
    creds = SimpleNamespace(provider="fake", vendor="fake", token="", base_url="")
    module.resolve_connection = lambda _id: creds
    ProviderRegistry.get_provider = staticmethod(lambda _name: provider)
    HumanPromptService.request = lambda *a, **k: PromptResult(text="ok")

    def restore() -> None:
        module.resolve_connection = orig_resolve
        ProviderRegistry.get_provider = orig_get
        HumanPromptService.request = orig_request

    return restore


def install_real_capture():
    """Wrap providers to record prompt facts; returns a callable that undoes the patch."""
    from agentdev.runtime.node.agent import ProviderRegistry

    orig_get = ProviderRegistry.__dict__["get_provider"]
    original = ProviderRegistry.get_provider
    cache: Dict[str, Any] = {}

    def get(name):
        cls = original(name)
        if cls is None:
            return None
        if name not in cache:
            cache[name] = make_capturing(cls)
        return cache[name]

    ProviderRegistry.get_provider = staticmethod(get)

    def restore() -> None:
        ProviderRegistry.get_provider = orig_get

    return restore


# --------------------------------------------------------------------------- scenarios


def _agent(node_id: str, model: str, mode: str, role: str, description: str, skills: bool) -> dict:
    config: Dict[str, Any] = {"name": model, "role": role}
    if mode == "fake":
        config.update({"connection": "fake", "provider": "fake"})
    else:
        config.update({"provider": "anthropic"})  # bound to the signed-in Claude account (connections.autobind)
    if skills:
        config["skills"] = {"enabled": True, "allow": list(SKILLS)}
    return {"id": node_id, "type": "agent", "description": description, "config": config}


def _graph(nodes: List[dict], edges: List[tuple], start: str, end: str, max_usd: Optional[float]) -> dict:
    graph: Dict[str, Any] = {
        "id": "bench_tokens", "start": [start], "end": [end], "log_level": "WARNING",
        "nodes": nodes, "edges": [{"from": a, "to": b} for a, b in edges]}
    if max_usd:
        graph["run_limits"] = {"max_cost_usd": max_usd}
    return {"version": "0.4.0", "graph": graph}


FIRST_REQUEST = ("Write a short plan for a personal budgeting web app: pages, data model and the first three tasks. "
                 "Keep it practical and mention how expenses are categorised.")
SHORT_REQUEST = "ok"
THIRD_REQUEST = ("Now add a monthly report page: which charts it shows, which data each chart needs and how the "
                 "user exports the report as a file. Keep the earlier decisions.")
TEAM_TASK = "Compare two ways of caching API responses and recommend one in a short memo."


def scenario_defs(mode: str, model: str, max_usd: Optional[float]) -> Dict[str, dict]:
    chat_node = _agent("Chat", model, mode, "You are a helpful assistant for small software tasks.",
                       "Answer the user's request directly and briefly.", False)
    chat_graph = _graph([chat_node], [], "Chat", "Chat", max_usd)
    team_nodes = [
        _agent("Plan", model, mode, "Planner", "Split the task into two independent parts for two workers.", True),
        _agent("Worker1", model, mode, "Worker", "Do part one of the plan and report the result.", True),
        _agent("Worker2", model, mode, "Worker", "Do part two of the plan and report the result.", True),
        _agent("Merge", model, mode, "Editor", "Merge both worker reports into one short final answer.", True),
    ]
    team_graph = _graph(team_nodes, [("Plan", "Worker1"), ("Plan", "Worker2"),
                                     ("Worker1", "Merge"), ("Worker2", "Merge")], "Plan", "Merge", max_usd)
    return {
        "chat": {"title": "Simple chat turn (1 agent)", "graph": chat_graph, "turns": [FIRST_REQUEST]},
        "followup": {"title": "3-turn chat: request, 'ok', request (growing history)", "graph": chat_graph,
                     "turns": [FIRST_REQUEST, SHORT_REQUEST, THIRD_REQUEST]},
        # Opt-in (``--only followup_long``): shows how much of the prompt consecutive normal turns share.
        "followup_long": {"title": "6 normal requests in a row (prompt-prefix stability)", "graph": chat_graph,
                          "turns": [f"{FIRST_REQUEST} (step {i})" for i in range(1, 7)]},
        "team": {"title": "Team: Plan -> 2 workers -> Merge, skills preloaded", "graph": team_graph,
                 "turns": [TEAM_TASK]},
    }


def planned_runs(names: List[str], defs: Dict[str, dict]) -> int:
    return sum(len(defs[n]["turns"]) for n in names)


def _node_rows(calls: List[Dict[str, Any]], usage: Dict[str, Any]) -> List[Dict[str, Any]]:
    """One row per node of one run: chars, estimated tokens, and the engine's own numbers when it has them."""
    rollups = (usage or {}).get("node_rollups", {})
    real_usage = (usage or {}).get("node_usages", {})
    history = (usage or {}).get("call_history", [])
    rows = []
    for node_id in dict.fromkeys(c["node"] for c in calls):
        mine = [c for c in calls if c["node"] == node_id]
        in_chars = sum(c["facts"]["input_chars"] for c in mine)
        out_chars = sum(c["output_chars"] for c in mine)
        reported = real_usage.get(node_id, {})
        roll = rollups.get(node_id, {})
        duration = sum(h.get("duration_ms", 0) or 0 for h in history if h.get("node_id") == node_id) / 1000.0
        facts = mine[0]["facts"]
        rows.append({
            "node": node_id,
            "model": mine[0]["model"],
            "calls": len(mine),
            "input_chars": in_chars,
            "output_chars": out_chars,
            "est_input_tokens": est_tokens(in_chars),
            "est_output_tokens": est_tokens(out_chars),
            "engine_input_tokens": reported.get("input_tokens"),
            "engine_output_tokens": reported.get("output_tokens"),
            "cache_read_tokens": roll.get("cache_read_tokens", 0),
            "cache_creation_tokens": roll.get("cache_creation_tokens", 0),
            "cost_usd": roll.get("cost_usd", 0.0),
            "duration_s": round(duration or sum(c["duration_s"] for c in mine), 3),
            "prompt": {k: facts[k] for k in (
                "system_chars", "tool_catalog_chars", "tool_count", "skills_chars", "history_chars",
                "user_chars", "static_chars", "transcript_chars", "system_order")},
            "volatile_in_static_head": facts["volatile_in_static_head"],
            "volatile_in_history": facts["volatile_in_history"],
            "cache_breaking_order": facts["cache_breaking_order"],
        })
    return rows


def _common_prefix(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def run_scenario(name: str, spec: dict, mode: str, folder: Path, cost_so_far: float, max_usd: float) -> Dict[str, Any]:
    from agentdev.api.services.conversation_turns import compose_follow_up_prompt, make_turn
    from agentdev.runtime.sdk import run_workflow

    path = folder / f"{name}.yaml"
    path.write_text(yaml.safe_dump(spec["graph"]), encoding="utf-8")
    runs: List[Dict[str, Any]] = []
    turns: List[Dict[str, Any]] = []
    prev_prompt = prev_static = None
    prev_had_history = False
    spent = cost_so_far
    stopped = None
    for index, request in enumerate(spec["turns"], start=1):
        if mode == "real" and spent >= max_usd:
            stopped = f"stopped before turn {index}: spent ${spent:.4f} reached --max-usd {max_usd}"
            break
        composed = compose_follow_up_prompt(turns, request) if turns else request
        history_chars = len(composed) - len(request) if turns else 0
        CAPTURE.reset()
        error = None
        answer = ""
        usage: Dict[str, Any] = {}
        try:
            result = run_workflow(path, task_prompt=composed, session_name=f"bench_{name}_{index}")
            usage = result.meta_info.token_usage or {}
            answer = result.final_message.text_content() if result.final_message else ""
        except Exception as exc:  # noqa: BLE001 - reported, not hidden
            error = f"{type(exc).__name__}: {str(exc)[:160]}"
        calls = list(CAPTURE.calls)
        rows = _node_rows(calls, usage)
        order = [n["id"] for n in spec["graph"]["graph"]["nodes"]]  # graph order: parallel nodes finish in any order
        rows.sort(key=lambda r: order.index(r["node"]) if r["node"] in order else len(order))
        run_cost = float((usage.get("summary") or {}).get("cost_usd") or 0.0)
        spent += run_cost
        first = calls[0]["facts"] if calls else None
        run = {
            "label": f"turn {index}" if len(spec["turns"]) > 1 else "run",
            "request_chars": len(request),
            "composed_prompt_chars": len(composed),
            "history_chars_added": history_chars,
            "nodes": rows,
            "totals": {
                "calls": len(calls),
                "input_chars": sum(r["input_chars"] for r in rows),
                "output_chars": sum(r["output_chars"] for r in rows),
                "est_input_tokens": sum(r["est_input_tokens"] for r in rows),
                "est_output_tokens": sum(r["est_output_tokens"] for r in rows),
                "engine_input_tokens": (usage.get("total_usage") or {}).get("input_tokens"),
                "engine_output_tokens": (usage.get("total_usage") or {}).get("output_tokens"),
                "cache_read_tokens": sum(r["cache_read_tokens"] for r in rows),
                "cache_creation_tokens": sum(r["cache_creation_tokens"] for r in rows),
                "cost_usd": round(run_cost, 4),
            },
            "error": error,
        }
        if first is not None:
            # Prefix shared with the previous turn's first call: what a prompt cache could reuse.
            if prev_prompt is not None:
                shared = _common_prefix(prev_prompt, first["_prompt"])
                run["prefix_shared_with_previous_chars"] = shared
                run["prefix_shared_with_previous_pct"] = round(100.0 * shared / max(len(first["_prompt"]), 1), 1)
                run["shared_prefix_ratio"] = round(shared / max(len(first["_prompt"]), 1), 3)
                run["static_head_identical_to_previous"] = prev_static == first["_static"]
                # Turn 1 has no history, so little shared prefix with turn 2 is expected: only judge later turns.
                run["prefix_judged"] = prev_had_history
            prev_prompt, prev_static = first["_prompt"], first["_static"]
        prev_had_history = history_chars > 0
        runs.append(run)
        turns.append(make_turn(request, answer))
    return {"name": name, "title": spec["title"], "runs": runs, "stopped": stopped, "cost_usd": round(spent - cost_so_far, 4)}


def structure_issues(scenarios: List[Dict[str, Any]]) -> List[str]:
    issues = []
    for sc in scenarios:
        for run in sc["runs"]:
            for row in run["nodes"]:
                if row["cache_breaking_order"]:
                    kinds = sorted({h["kind"] for h in row["volatile_in_static_head"]})
                    issues.append(f"{sc['name']}/{run['label']}/{row['node']}: volatile part ({', '.join(kinds)}) "
                                  "in the static head of the prompt: breaks prompt-cache prefix reuse")
            if run.get("static_head_identical_to_previous") is False:
                issues.append(f"{sc['name']}/{run['label']}: static head (system + tools) differs from the previous turn")
            pct = run.get("prefix_shared_with_previous_pct")
            if pct is not None and run.get("prefix_judged") and pct < 50:
                issues.append(f"{sc['name']}/{run['label']}: only {pct}% of the prompt is a prefix of the previous "
                              "turn's prompt (history is re-rendered/clipped, little cache reuse)")
    return issues


def run_all(mode: str, names: List[str], max_usd: float, max_runs: int) -> Dict[str, Any]:
    model = REAL_MODEL if mode == "real" else FAKE_MODEL
    defs = scenario_defs(mode, model, max_usd if mode == "real" else None)
    unknown = [n for n in names if n not in defs]
    if unknown:
        raise SystemExit(f"unknown scenario(s): {', '.join(unknown)}; choose from {', '.join(defs)}")
    planned = planned_runs(names, defs)
    if mode == "real" and planned > max_runs:
        raise SystemExit(
            f"refused: the plan needs {planned} workflow runs but --max-runs is {max_runs}. "
            "Pick fewer scenarios with --only, or raise --max-runs on purpose.")
    scenarios: List[Dict[str, Any]] = []
    spent = 0.0
    with tempfile.TemporaryDirectory(prefix="agentdev-bench-tokens-") as tmp:
        import agentdev.runtime.sdk as sdk

        orig_output_root = sdk.OUTPUT_ROOT
        sdk.OUTPUT_ROOT = Path(tmp) / "out"  # keep benchmark output out of the real warehouse
        restore = install_fake() if mode == "fake" else install_real_capture()
        try:
            for name in names:
                sc = run_scenario(name, defs[name], mode, Path(tmp), spent, max_usd)
                spent += sc["cost_usd"]
                scenarios.append(sc)
        finally:
            restore()
            sdk.OUTPUT_ROOT = orig_output_root
    return {
        "mode": mode,
        "model": model,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "token_estimate": "chars/4 (engine-reported tokens are shown separately when the provider reports them)",
        "limits": {"max_runs": max_runs, "max_usd": max_usd, "planned_runs": planned},
        "scenarios": scenarios,
        "total_cost_usd": round(spent, 4),
        "structure_issues": structure_issues(scenarios),
    }


# --------------------------------------------------------------------------- output


def render_markdown(report: Dict[str, Any], stable: bool = False) -> str:
    """Markdown tables. ``stable`` leaves out the timestamp and durations so a fake baseline diffs cleanly."""
    lines = [f"# Token benchmark ({report['mode']})", ""]
    lines.append(f"- model: `{report['model']}`; estimate: {report['token_estimate']}")
    if not stable:
        lines.append(f"- generated: {report['generated_at']}")
    lines.append(f"- total engine cost: ${report['total_cost_usd']}")
    lines.append("")
    for sc in report["scenarios"]:
        lines += [f"## {sc['name']}: {sc['title']}", ""]
        if sc["stopped"]:
            lines += [f"> {sc['stopped']}", ""]
        head = ["run", "node", "model", "calls", "in chars", "out chars", "est in tok", "est out tok",
                "engine in/out tok", "cache read/create", "cost $"]
        if not stable:
            head.append("sec")
        lines += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        for run in sc["runs"]:
            for r in run["nodes"]:
                eng = (f"{r['engine_input_tokens']}/{r['engine_output_tokens']}"
                       if r["engine_input_tokens"] is not None and report["mode"] == "real" else "-")
                cells = [run["label"], r["node"], r["model"], r["calls"], r["input_chars"], r["output_chars"],
                         r["est_input_tokens"], r["est_output_tokens"], eng,
                         f"{r['cache_read_tokens']}/{r['cache_creation_tokens']}", r["cost_usd"]]
                if not stable:
                    cells.append(r["duration_s"])
                lines.append("| " + " | ".join(str(c) for c in cells) + " |")
            if run["error"]:
                lines.append(f"| {run['label']} | ERROR | {run['error']} |")
        lines.append("")
        lines += ["Prompt structure (first call of each node, chars):", "",
                  "| run | node | system | tool catalog | skills | history | user msg | static head | order | volatile in head |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for run in sc["runs"]:
            for r in run["nodes"]:
                p = r["prompt"]
                vol = ", ".join(sorted({h["kind"] for h in r["volatile_in_static_head"]})) or "none"
                lines.append(f"| {run['label']} | {r['node']} | {p['system_chars']} | {p['tool_catalog_chars']} "
                             f"({p['tool_count']} tools) | {p['skills_chars']} | {p['history_chars']} | "
                             f"{p['user_chars']} | {p['static_chars']} | {' > '.join(p['system_order'])} | {vol} |")
        lines.append("")
        cache_rows = [run for run in sc["runs"] if "prefix_shared_with_previous_pct" in run]
        if cache_rows:
            lines += ["Prefix shared with the previous turn (cache potential):", "",
                      "| run | history added | prompt prefix shared (chars) | % of prompt | static head identical |",
                      "|---|---|---|---|---|"]
            for run in cache_rows:
                lines.append(f"| {run['label']} | {run['history_chars_added']} | {run['prefix_shared_with_previous_chars']} "
                             f"| {run['prefix_shared_with_previous_pct']} | {run['static_head_identical_to_previous']} |")
            lines.append("")
    lines += ["## Prompt-structure findings", ""]
    lines += [f"- {i}" for i in report["structure_issues"]] or ["- none"]
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: Dict[str, Any], out_dir: Path, baseline: bool) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    written = []
    json_path = out_dir / f"bench-tokens-{stamp}.json"
    md_path = out_dir / f"bench-tokens-{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    written += [json_path, md_path]
    if baseline:
        if report["mode"] != "fake":
            raise SystemExit("--baseline only writes from a --fake run")
        base = out_dir / BASELINE_NAME
        base.write_text(render_markdown(report, stable=True), encoding="utf-8")
        written.append(base)
    return written


def resolve_out(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else REPO_ROOT / path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--fake", action="store_true", help="fake provider, zero cost (default)")
    mode.add_argument("--real", action="store_true", help="logged-in Claude CLI account, cheapest model, spends tokens")
    parser.add_argument("--only", nargs="*", help="scenario names: chat followup team (default: all)")
    parser.add_argument("--json", action="store_true", help="print JSON instead of the markdown table")
    parser.add_argument("--out", help="folder for bench-tokens-<timestamp>.{json,md} (relative: from the repo root)")
    parser.add_argument("--baseline", action="store_true", help="also write the stable baseline md (fake only)")
    parser.add_argument("--max-runs", type=int, default=3, help="real mode: most workflow runs allowed (default 3)")
    parser.add_argument("--max-usd", type=float, default=0.5, help="real mode: most spend allowed (default 0.5)")
    args = parser.parse_args(argv)

    chosen = "real" if args.real else "fake"
    names = args.only or ["chat", "followup", "team"]
    report = run_all(chosen, names, args.max_usd, args.max_runs)
    if args.out or args.baseline:
        for path in write_outputs(report, resolve_out(args.out) if args.out else DEFAULT_OUT, args.baseline):
            print(f"wrote {path}", file=sys.stderr)
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
