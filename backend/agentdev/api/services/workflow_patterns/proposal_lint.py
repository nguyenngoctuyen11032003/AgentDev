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

from agentdev.connections import catalog

SMALL_SECONDS, MID_SECONDS, TOP_SECONDS = 15, 40, 90
LOOP_SECONDS = 30
SLOW_SECONDS = 180
_SMALL_MARKERS = ("haiku", "flash", "luna")
_TOP_MARKERS = ("fable", "opus", "sol", "pro")
_CHEAP_ROLE_RE = re.compile(r"\b(review|reviewer|qa|check|checker|tester|verify|save|saver|archive|archivist)\b",
                            re.IGNORECASE)
_TRIAGE_RE = re.compile(r"triage|intake|router|routing|lead|producer|manager|coordinator|phan loai", re.IGNORECASE)
_AUTO_ANSWER = "[Automatic answer] Approved"


def model_tier(name: Any) -> str:
    """``small`` / ``mid`` / ``top`` from the model name (unknown names count as mid)."""
    text = str(name or "").lower()
    if any(m in text for m in _SMALL_MARKERS):
        return "small"
    if any(re.search(rf"(?<![a-z]){m}(?![a-z])", text) for m in _TOP_MARKERS):
        return "top"
    return "mid"


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


def _graph(data: Any) -> Tuple[Dict[str, dict], List[Tuple[str, str]]]:
    graph = (data or {}).get("graph") if isinstance(data, dict) else None
    graph = graph if isinstance(graph, dict) else {}
    nodes = {n.get("id"): n for n in graph.get("nodes") or [] if isinstance(n, dict) and n.get("id") is not None}
    edges = [(e.get("from"), e.get("to")) for e in graph.get("edges") or []
             if isinstance(e, dict) and e.get("from") in nodes and e.get("to") in nodes]
    return nodes, edges


def sccs(nodes: Any, edges: List[Tuple[str, str]]) -> List[List[str]]:
    """Strongly connected components (Tarjan, iterative)."""
    adj: Dict[str, List[str]] = {n: [] for n in nodes}
    for src, dst in edges:
        adj[src].append(dst)
    index: Dict[str, int] = {}
    low: Dict[str, int] = {}
    stack: List[str] = []
    on: set = set()
    out: List[List[str]] = []
    counter = 0
    for root in adj:
        if root in index:
            continue
        work = [(root, iter(adj[root]))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on.add(root)
        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on.add(nxt)
                    work.append((nxt, iter(adj[nxt])))
                    advanced = True
                    break
                if nxt in on:
                    low[node] = min(low[node], index[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    top = stack.pop()
                    on.discard(top)
                    comp.append(top)
                    if top == node:
                        break
                out.append(comp)
    return out


def _cycles(nodes: Dict[str, dict], edges: List[Tuple[str, str]]) -> List[List[str]]:
    selfloops = {s for s, d in edges if s == d}
    return [c for c in sccs(nodes, edges) if len(c) > 1 or c[0] in selfloops]


def unguarded_cycles(data: Any) -> List[List[str]]:
    nodes, edges = _graph(data)
    return [c for c in _cycles(nodes, edges) if not any(nodes[n].get("type") == "loop_counter" for n in c)]


def _matches(condition: Any, text: str) -> bool:
    """Same semantics as the keyword edge condition (``none`` / ``any`` / ``regex``)."""
    if not isinstance(condition, dict):
        return True
    if condition.get("type") != "keyword":
        return True  # function conditions cannot be judged here
    config = condition.get("config") or {}
    sensitive = config.get("case_sensitive", True)
    hay = text if sensitive else text.lower()
    norm = (lambda w: str(w)) if sensitive else (lambda w: str(w).lower())
    if any(norm(w) in hay for w in config.get("none") or []):
        return False
    if any(norm(w) in hay for w in config.get("any") or []):
        return True
    flags = 0 if sensitive else re.IGNORECASE
    for pattern in config.get("regex") or []:
        try:
            if re.search(str(pattern), text, flags):
                return True
        except re.error:
            continue
    return False


def gates_missing_auto_answer(data: Any) -> List[str]:
    """Human nodes with conditional outgoing edges where none accepts ``[Automatic answer ...]``."""
    graph = (data or {}).get("graph") if isinstance(data, dict) else None
    nodes, _ = _graph(data)
    bad = []
    for node_id, node in nodes.items():
        if node.get("type") != "human":
            continue
        conds = [e.get("condition") for e in (graph or {}).get("edges") or []
                 if isinstance(e, dict) and e.get("from") == node_id and isinstance(e.get("condition"), dict)]
        if conds and not any(_matches(c, _AUTO_ANSWER) for c in conds):
            bad.append(node_id)
    return bad


def triage_missing(data: Any) -> bool:
    """True when the graph has >= 4 agents but its first node is not a triage/lead-like agent."""
    agents = _agents(data)
    if len(agents) < 4:
        return False
    graph = data.get("graph") or {}
    nodes, _ = _graph(data)
    start = (graph.get("start") or [None])[0]
    node = nodes.get(start)
    if not node:
        return False
    if node.get("type") == "agent" and (node["config"].get("team") or {}).get("enabled"):
        return False
    return not (node.get("type") == "agent" and _TRIAGE_RE.search(f"{node.get('id', '')} {node.get('description', '')}"))


def _weight(node: dict, nodes: Dict[str, dict]) -> int:
    if node.get("type") != "agent" or not isinstance(node.get("config"), dict):
        return 0
    seconds = {"small": SMALL_SECONDS, "mid": MID_SECONDS, "top": TOP_SECONDS}
    own = seconds[model_tier(node["config"].get("name"))]
    team = node["config"].get("team") or {}
    if team.get("enabled"):  # worst case: the members run one after the other
        for member in team.get("members") or []:
            if isinstance(nodes.get(member), dict):
                own += _weight(nodes[member], nodes)
    return own


def estimate_seconds(data: Any) -> int:
    """Longest chain of agent nodes (small 15 s, mid 40 s, top 90 s), +30 s per loop; team members add up."""
    nodes, edges = _graph(data)
    if not nodes:
        return 0
    comps = sccs(nodes, edges)
    selfloops = {s for s, d in edges if s == d}
    cyclic = {i for i, c in enumerate(comps) if len(c) > 1 or c[0] in selfloops}
    comp_of = {n: i for i, c in enumerate(comps) for n in c}
    weight = [sum(_weight(nodes[n], nodes) for n in c) + (LOOP_SECONDS if i in cyclic else 0) for i, c in enumerate(comps)]
    succ: Dict[int, set] = {i: set() for i in range(len(comps))}
    for src, dst in edges:
        if comp_of[src] != comp_of[dst]:
            succ[comp_of[src]].add(comp_of[dst])
    memo: Dict[int, int] = {}

    def longest(i: int) -> int:
        if i not in memo:
            memo[i] = weight[i] + max((longest(j) for j in succ[i]), default=0)
        return memo[i]

    return max(longest(i) for i in range(len(comps)))


def speed_check(data: Any) -> dict:
    seconds = estimate_seconds(data)
    status = "warn" if seconds > SLOW_SECONDS else "pass"
    detail = f"~{seconds}s" if status == "pass" else f"~{seconds}s for the longest path; consider smaller models or fewer steps"
    return {"id": "speed", "status": status, "detail": detail, "estimated_seconds": seconds}


def lint(data: Any) -> Tuple[List[str], List[dict]]:
    """Read-only lint: (warning notes, extra checks)."""
    notes: List[str] = []
    for comp in unguarded_cycles(data):
        notes.append("Loop without a loop_counter: " + " → ".join(comp) + ". Add a counter so it cannot run forever.")
    for node_id in gates_missing_auto_answer(data):
        notes.append(f"{node_id}: no branch accepts `[Automatic answer`, so the Lab test harness cannot pass this gate.")
    if triage_missing(data):
        notes.append("The first node is not a triage: small asks will run the whole team.")
    return notes, [speed_check(data)]
