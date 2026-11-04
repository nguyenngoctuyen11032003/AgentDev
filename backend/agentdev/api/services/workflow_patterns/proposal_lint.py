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
    for node_id in gates_missing_auto_answer(data):
        notes.append(f"{node_id}: no branch accepts `[Automatic answer`, so the Lab test harness cannot pass this gate.")
    if triage_missing(data):
        notes.append("The first node is not a triage: small asks will run the whole team.")
    return notes, []
