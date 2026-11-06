"""Deterministic fixes and lint for a proposed workflow, run before the proposal card is built.

Everything here replaces what would otherwise cost a repair round trip (a whole second model call that
resends the YAML): unknown model names are swapped for the vendor's default, review/QA/save nodes are
moved to a small model, and a speed estimate is computed. ``create`` proposals are re-dumped from the
parsed data (comments and anchors are not worth keeping in a new file); an ``edit`` is copied verbatim,
so only model names are replaced there, by text, and everything else is reported as a warning.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

from agentdev.api.services.workflow_patterns.graph_analysis import (  # noqa: F401 - re-exported
    CRITICAL_PATH_SECONDS as SLOW_SECONDS,
    Graph,
    edge_condition_matches,
    model_tier,
    sccs,
)
from agentdev.connections import catalog
from agentdev.utils.human_prompt import AUTO_ANSWER

_CHEAP_ROLE_RE = re.compile(r"\b(review|reviewer|qa|check|checker|tester|verify|save|saver|archive|archivist)\b",
                            re.IGNORECASE)
_TRIAGE_RE = re.compile(r"triage|intake|router|routing|lead|producer|manager|coordinator|phan loai", re.IGNORECASE)


def _vendor_models(vendor: str) -> Tuple[str, ...]:
    info = catalog.get_vendor(vendor)
    return tuple(info.models) if info else ()


def default_model(vendor: str, tier: str = "mid") -> Optional[str]:
    """The vendor's model for ``tier`` (falls back to its first model)."""
    models = _vendor_models(vendor)
    for name in models:
        if model_tier(name) == tier:
            return name
    return models[0] if models else None


def _agents(data: Any) -> List[dict]:
    graph = (data or {}).get("graph") if isinstance(data, dict) else None
    nodes = (graph or {}).get("nodes") if isinstance(graph, dict) else None
    return [n for n in nodes or [] if isinstance(n, dict) and n.get("type") == "agent"
            and isinstance(n.get("config"), dict)]


def _bad_model(config: dict) -> bool:
    provider, name = config.get("provider"), config.get("name")
    models = _vendor_models(provider) if isinstance(provider, str) else ()
    if not models or not name:
        return False  # an unknown provider or an empty name is the static check's business
    return name not in models or catalog.is_retired_model(provider, name)


def unknown_models(data: Any) -> List[Tuple[str, str, str]]:
    """``(node id, provider, model)`` for agents whose model is not in the catalog."""
    return [(str(n.get("id")), n["config"]["provider"], str(n["config"]["name"]))
            for n in _agents(data) if _bad_model(n["config"])]


def substitute_models_in_text(text: str, data: Any, chat_vendor: Optional[str]) -> Tuple[str, List[str]]:
    """Replace unknown model names in the YAML text itself; (new text, warning notes)."""
    notes: List[str] = []
    for node_id, provider, name in unknown_models(data):
        vendor = provider if _vendor_models(provider) else (chat_vendor or provider)
        new = default_model(vendor)
        if not new:
            continue
        pattern = re.compile(rf"(\bname:\s*)(['\"]?){re.escape(name)}\2(?=\s*(?:#.*)?$)", re.MULTILINE)
        text, count = pattern.subn(lambda m: f"{m.group(1)}{new}", text)
        if count:
            notes.append(f"{node_id}: unknown model `{name}` replaced by `{new}`.")
    return text, notes


class _Dumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:  # noqa: D401 - expand anchors
        return True


def _str_representer(dumper: yaml.SafeDumper, value: str) -> Any:
    if "\n" in value:
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", value)


_Dumper.add_representer(str, _str_representer)


def dump_workflow(data: Any) -> str:
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=110)


def _cheap_node(node: dict) -> bool:
    return bool(_CHEAP_ROLE_RE.search(f"{node.get('id', '')} {node.get('description', '')}"))


def downgrade_cheap_nodes(data: Any) -> List[str]:
    """In place: review/QA/save agents on a top model or high effort move to the vendor's small model with
    effort low. Team leads are never touched. Returns warning notes."""
    notes: List[str] = []
    for node in _agents(data):
        config = node["config"]
        if (config.get("team") or {}).get("enabled") or not _cheap_node(node):
            continue
        params = config.get("params")
        high = isinstance(params, dict) and params.get("effort") == "high"
        top = model_tier(config.get("name")) == "top"
        if not (top or high):
            continue
        if top:
            small = default_model(config.get("provider"), "small")
            if small:
                config["name"] = small
        config["params"] = {**(params if isinstance(params, dict) else {}), "effort": "low"}
        notes.append(f"{node.get('id')}: review/QA/save step moved to `{config.get('name')}` with low effort "
                     "(faster, same result).")
    return notes


def add_case_sensitive(data: Any) -> int:
    """In place: keyword conditions without ``case_sensitive`` get ``true`` (the runtime default)."""
    count = 0
    graph = (data or {}).get("graph") if isinstance(data, dict) else None
    for edge in (graph or {}).get("edges") or []:
        cond = edge.get("condition") if isinstance(edge, dict) else None
        if isinstance(cond, dict) and cond.get("type") == "keyword" and isinstance(cond.get("config"), dict):
            if "case_sensitive" not in cond["config"]:
                cond["config"]["case_sensitive"] = True
                count += 1
    return count


# ---------------------------------------------------------------------------- graph


def unguarded_cycles(data: Any) -> List[List[str]]:
    return Graph.from_workflow(data).unguarded_cycles()


def counters_in_inner_loop(data: Any) -> List[str]:
    return Graph.from_workflow(data).counters_in_inner_loop()


def gates_missing_auto_answer(data: Any) -> List[str]:
    """Human nodes the Lab's automatic answer cannot get past (same rule as the ``human_auto`` check)."""
    return Graph.from_workflow(data).humans_blocking_auto_answer(AUTO_ANSWER)


def _conditional(edge: dict) -> bool:
    cond = edge.get("condition")
    if not cond or cond is True:
        return False
    if isinstance(cond, dict) and cond.get("type") == "function":
        return str((cond.get("config") or {}).get("name") or "") not in ("true", "")
    return True


def end_nodes_running_together(data: Any) -> List[Tuple[Any, Any]]:
    """Pairs of end nodes that one run can both reach: no node splits them with conditional edges."""
    g = Graph.from_workflow(data)
    graph = (data or {}).get("graph") if isinstance(data, dict) else None
    graph = graph if isinstance(graph, dict) else {}
    ends = [e for e in graph.get("end") or [] if e in g.nodes]
    starts = [s for s in graph.get("start") or [] if s in g.nodes]
    if len(ends) < 2:
        return []

    def reach(seeds: List[Any], skip: Any = None) -> set:
        seen, todo = set(), [s for s in seeds if s != skip]
        while todo:
            n = todo.pop()
            if n in seen:
                continue
            seen.add(n)
            todo.extend(t for t in g.adj.get(n, []) if t != skip)
        return seen

    out: List[Tuple[Any, Any]] = []
    for i, x in enumerate(ends):
        for y in ends[i + 1:]:
            exclusive = False
            for n in g.nodes:
                cond_edges = [e for e in g.edges if e.get("from") == n and e.get("to") in g.nodes and _conditional(e)]
                if len(cond_edges) < 2:
                    continue
                if x in reach(starts, skip=n) or y in reach(starts, skip=n):
                    continue  # one of them is also reachable around this node
                for a in cond_edges:
                    for b in cond_edges:
                        ra, rb = reach([a["to"]]), reach([b["to"]])
                        if x in ra and x not in rb and y in rb and y not in ra:
                            exclusive = True
            if not exclusive:
                out.append((x, y))
    return out


def triage_missing(data: Any) -> bool:
    """True when the graph has >= 4 agents but its first node is not a triage/lead-like agent."""
    agents = _agents(data)
    if len(agents) < 4:
        return False
    graph = data.get("graph") or {}
    nodes = Graph(graph).nodes
    start = (graph.get("start") or [None])[0]
    node = nodes.get(start)
    if not node:
        return False
    if node.get("type") == "agent" and (node["config"].get("team") or {}).get("enabled"):
        return False
    return not (node.get("type") == "agent" and _TRIAGE_RE.search(f"{node.get('id', '')} {node.get('description', '')}"))


def estimate_seconds(data: Any) -> int:
    """The static check's ``critical_path`` estimate (one implementation, one number per graph)."""
    return Graph.from_workflow(data).critical_path()["estimated_seconds"]


def speed_check(data: Any) -> dict:
    path = Graph.from_workflow(data).critical_path()
    seconds = path["estimated_seconds"]
    status = "warn" if path["slow"] else "pass"
    detail = f"~{seconds}s" if status == "pass" else f"~{seconds}s for the longest path; consider smaller models or fewer steps"
    return {"id": "speed", "status": status, "detail": detail, "estimated_seconds": seconds}


def lint(data: Any) -> Tuple[List[str], List[dict]]:
    """Read-only lint: (warning notes, extra checks). No extra speed check: the static check's
    ``critical_path`` already carries the estimate, and a second one could only disagree."""
    notes: List[str] = []
    graph = Graph.from_workflow(data)
    for i in sorted(graph.cyclic):
        if not graph.guarded(i) and not graph.has_counter(i):  # a misplaced counter gets its own note below
            notes.append("Loop without a loop_counter: " + " → ".join(map(str, graph.comps[i]))
                         + ". Add a counter so it cannot run forever.")
    for node_id in counters_in_inner_loop(data):
        notes.append(f"{node_id}: this loop_counter sits on an inner loop that is left before it runs, so it never "
                     "counts. Point its in-loop edge at the step that starts the loop (the one the outside feeds).")
    from agentdev.api.services.session_execution import NO_REPLY_TEXT
    for node_id in Graph.from_workflow(data).humans_approving_silence(NO_REPLY_TEXT):
        notes.append(f"{node_id}: a timeout (no reply) takes the approve branch, so silence approves. Anchor the "
                     "approve regex on the answer itself (e.g. ^\s*OK\W*$ or [Automatic answer), never on '['.")
    for node_id in gates_missing_auto_answer(data):
        notes.append(f"{node_id}: no branch accepts `[Automatic answer`, so the Lab test harness cannot pass this gate.")
    for x, y in end_nodes_running_together(data):
        notes.append(f"MULTIPLE_END_NODES: end steps '{x}' and '{y}' can both run in one turn; the one that finishes "
                     "last gives the answer. Make them exclusive with edge conditions, or keep a single end step.")
    if triage_missing(data):
        notes.append("The first node is not a triage: small asks will run the whole team.")
    return notes, []


PAID_GATE_REMOVED = "PAID_GATE_REMOVED"


def _paid_gate_ids(graph: Graph) -> List[Any]:
    """Paid gates: only a ``type: human`` node with ``config.paid: true`` makes a person approve the spend."""
    return [nid for nid, node in graph.nodes.items()
            if node.get("type") == "human" and isinstance(node.get("config"), dict)
            and node["config"].get("paid") is True]


def _ungated_reach(graph: Graph) -> set:
    """Nodes a run can start from a start node without passing a paid human gate (``trigger: false`` edges only
    carry data and never start a step, so they are skipped)."""
    gates = set(_paid_gate_ids(graph))
    start = graph.raw.get("start")
    start = [start] if isinstance(start, str) else list(start or [])
    triggering = [e for e in graph.edges if e.get("trigger") is not False
                  and e.get("from") in graph.nodes and e.get("to") in graph.nodes]
    if not start:  # no declared start: every node nothing triggers
        targets = {e.get("to") for e in triggering}
        start = [nid for nid in graph.nodes if nid not in targets]
    adj: Dict[Any, List[Any]] = {}
    for e in triggering:
        adj.setdefault(e.get("from"), []).append(e.get("to"))
    seen = {s for s in start if s in graph.nodes}
    stack = [s for s in seen if s not in gates]
    while stack:
        for nxt in adj.get(stack.pop(), []):
            if nxt not in seen:
                seen.add(nxt)
                if nxt not in gates:
                    stack.append(nxt)
    return seen


def _reached_without_person(graph: Graph, gate: Any) -> set:
    """Steps a paid gate's edges lead to when no person answers (timeout text, Lab auto-answers)."""
    from agentdev.api.services.session_execution import NO_REPLY_TEXT
    from agentdev.utils.human_prompt import AUTO_SKIP_PAID

    return {e.get("to") for e in graph.edges if e.get("from") == gate
            for text in (NO_REPLY_TEXT, AUTO_ANSWER, AUTO_SKIP_PAID) if edge_condition_matches(e.get("condition"), text)}


def paid_gate_changes(old: Any, new: Any) -> List[Dict[str, Any]]:
    """How an edit weakens the saved file's ``paid: true`` steps (top-level graph): ``removed`` (node gone),
    ``type_changed`` (no longer a human step), ``unmarked`` (flag dropped), ``silence_reaches`` (a timeout /
    automatic answer now leads to steps it did not reach before) or ``bypassed`` (a step the gate guarded can now
    start from a start node without passing any paid human gate). Reported as a warning: the user may really want
    it, but must see it before Apply."""
    if not isinstance(old, dict):
        return []
    before, after = Graph.from_workflow(old), Graph.from_workflow(new)
    still_paid = set(_paid_gate_ids(after))
    reach_before, reach_after = _ungated_reach(before), _ungated_reach(after)
    items: List[Dict[str, Any]] = []
    for gate in _paid_gate_ids(before):
        if gate not in after.nodes:
            items.append({"node": gate, "kind": "removed"})
            continue
        if after.nodes[gate].get("type") != "human":
            items.append({"node": gate, "kind": "type_changed"})
        elif gate not in still_paid:
            items.append({"node": gate, "kind": "unmarked"})
        else:
            added = _reached_without_person(after, gate) - _reached_without_person(before, gate)
            if added:
                items.append({"node": gate, "kind": "silence_reaches", "to": sorted(map(str, added))})
            # Only while the gate still stands: a removed/retyped/unmarked gate is already reported above.
            guarded = {e.get("to") for e in before.edges if e.get("from") == gate and e.get("to") != gate}
            bypassed = (guarded & reach_after) - reach_before
            if bypassed:
                items.append({"node": gate, "kind": "bypassed", "to": sorted(map(str, bypassed))})
    return items
