"""Diff two workflow documents down to the field level."""

import unicodedata
from typing import Any, Dict, List, Optional, Tuple


def _leaf_paths(old: Any, new: Any, prefix: str = "") -> List[str]:
    """Dotted paths of leaves that differ; lists and scalars are leaves."""
    if isinstance(old, dict) and isinstance(new, dict):
        paths: List[str] = []
        for key in list(new) + [k for k in old if k not in new]:
            sub = f"{prefix}.{key}" if prefix else str(key)
            if key not in old or key not in new:
                paths.append(sub)
            else:
                paths.extend(_leaf_paths(old[key], new[key], sub))
        return paths
    return [prefix] if old != new else []


def _graph(doc: Optional[dict]) -> dict:
    return (doc or {}).get("graph") or {}


def _edge_map(graph: dict) -> Dict[Tuple[Any, Any, int], dict]:
    """Key edges by (from, to, occurrence index among the same pair) so parallel edges stay distinct."""
    seen: Dict[Tuple[Any, Any], int] = {}
    result: Dict[Tuple[Any, Any, int], dict] = {}
    for e in graph.get("edges") or []:
        pair = (e.get("from"), e.get("to"))
        result[pair + (seen.get(pair, 0),)] = e
        seen[pair] = seen.get(pair, 0) + 1
    return result


def diff_workflows(old: Optional[dict], new: dict) -> dict:
    og, ng = _graph(old), _graph(new)
    old_nodes = {n.get("id"): n for n in og.get("nodes") or []}
    new_nodes = {n.get("id"): n for n in ng.get("nodes") or []}

    nodes_changed = []
    for nid, node in new_nodes.items():
        if nid in old_nodes:
            fields = _leaf_paths(old_nodes[nid], node)
            if fields:
                nodes_changed.append({"id": nid, "fields": fields})

    old_edges, new_edges = _edge_map(og), _edge_map(ng)
    edges_changed = []
    for key, edge in new_edges.items():
        if key in old_edges:
            fields = [f for f in _leaf_paths(old_edges[key], edge) if f not in ("from", "to")]
            if fields:
                edges_changed.append({"from": key[0], "to": key[1], "fields": fields})

    old_rest = {k: v for k, v in og.items() if k not in ("nodes", "edges")}
    new_rest = {k: v for k, v in ng.items() if k not in ("nodes", "edges")}

    return {
        "nodes_added": [i for i in new_nodes if i not in old_nodes],
        "nodes_removed": [i for i in old_nodes if i not in new_nodes],
        "nodes_changed": nodes_changed,
        "edges_added": [{"from": k[0], "to": k[1]} for k in new_edges if k not in old_edges],
        "edges_removed": [{"from": k[0], "to": k[1]} for k in old_edges if k not in new_edges],
        "edges_changed": edges_changed,
        "graph_fields_changed": _leaf_paths(old_rest, new_rest),
    }


def _forms(text: str) -> List[str]:
    low = unicodedata.normalize("NFC", text).lower()
    return [low, low.replace("_", " ").replace("-", " ")]


def _mentioned(node_id: Any, haystacks: List[str]) -> bool:
    for form in _forms(str(node_id)):
        if form and any(form in h for h in haystacks):
            return True
    return False


def unrequested_changes(diff: dict, user_text: str) -> List[str]:
    """Ids of removed/changed nodes, or endpoints of removed edges, the user never named."""
    haystacks = _forms(user_text or "")
    flagged: List[str] = []

    def flag(node_id: Any) -> None:
        if node_id not in flagged:
            flagged.append(node_id)

    for nid in diff.get("nodes_removed", []):
        if not _mentioned(nid, haystacks):
            flag(nid)
    for item in diff.get("nodes_changed", []):
        if not _mentioned(item["id"], haystacks):
            flag(item["id"])
    for edge in diff.get("edges_removed", []):
        ends = [edge["from"], edge["to"]]
        if not any(_mentioned(e, haystacks) for e in ends):
            for e in ends:
                flag(e)
    return flagged
