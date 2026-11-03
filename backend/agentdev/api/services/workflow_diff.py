"""Diff two workflow documents down to the field level, and list the risky tools a document adds."""

import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union


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


def _graph(doc: Any) -> dict:
    """``doc.graph`` when it is a mapping, else ``{}`` (a broken saved file must not crash the diff)."""
    graph = doc.get("graph") if isinstance(doc, dict) else None
    return graph if isinstance(graph, dict) else {}


def _dicts(value: Any) -> List[dict]:
    """The mapping entries of a list (anything else, or a non-list, yields nothing)."""
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _edge_map(graph: dict) -> Dict[Tuple[Any, Any, int], dict]:
    """Key edges by (from, to, occurrence index among the same pair) so parallel edges stay distinct."""
    seen: Dict[Tuple[Any, Any], int] = {}
    result: Dict[Tuple[Any, Any, int], dict] = {}
    for e in _dicts(graph.get("edges")):
        pair = (e.get("from"), e.get("to"))
        result[pair + (seen.get(pair, 0),)] = e
        seen[pair] = seen.get(pair, 0) + 1
    return result


def diff_workflows(old: Optional[dict], new: dict) -> dict:
    og, ng = _graph(old), _graph(new)
    old_nodes = {n.get("id"): n for n in _dicts(og.get("nodes"))}
    new_nodes = {n.get("id"): n for n in _dicts(ng.get("nodes"))}

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


def unrequested_changes(diff: dict, user_text: Union[str, Iterable[str]]) -> List[str]:
    """Ids of removed/changed nodes, or endpoints of removed edges, the user never named.

    ``user_text`` is one message or every user message of the conversation: the diff is against the
    saved file, so a change asked for in an earlier turn (still pending) is a requested change too."""
    texts = [user_text] if isinstance(user_text, str) or user_text is None else list(user_text)
    haystacks = [form for text in texts for form in _forms(text or "")]
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


# ---------------------------------------------------------------------------- dangerous tools


def _code_execution_tools() -> set:
    from agentdev.api.services.workflow_lab import UNSAFE_TOOLS

    return UNSAFE_TOOLS


def _tooling_items(node_id: Any, tooling: Any, unsafe: set) -> List[dict]:
    items: List[dict] = []
    for entry in _dicts(tooling):
        kind, config = entry.get("type"), entry.get("config")
        if not isinstance(config, dict):
            continue
        if kind == "mcp_local" and config.get("command"):
            args = config.get("args") if isinstance(config.get("args"), list) else []
            detail = " ".join(str(part) for part in [config["command"], *args])
            items.append({"node": node_id, "kind": "mcp_local", "detail": detail})
        elif kind == "mcp_remote" and config.get("server"):
            items.append({"node": node_id, "kind": "mcp_remote", "detail": str(config["server"])})
        elif kind == "function":
            for tool in config.get("tools") if isinstance(config.get("tools"), list) else []:
                name = tool.get("name") if isinstance(tool, dict) else tool
                if not isinstance(name, str):
                    continue
                base = name.split(":")[0]
                if name in unsafe or base in unsafe or base == "uv_related":
                    items.append({"node": node_id, "kind": "code_execution", "detail": name})
    return items


def dangerous_tool_items(data: Any) -> List[dict]:
    """``{node, kind, detail}`` for every capability that lets the workflow run commands or reach the
    network when it runs: local MCP servers (``mcp_local``, detail = the command line), remote MCP servers
    (``mcp_remote``, detail = the URL) and code execution (``code_execution``, detail = the tool name, or
    the node type of a Python node). Independent of the unsafe-code-execution switch on this machine."""
    unsafe = _code_execution_tools()
    items: List[dict] = []
    for node in _dicts(_graph(data).get("nodes")):
        node_id, node_type = node.get("id"), node.get("type")
        if node_type in ("python", "python_runner"):
            items.append({"node": node_id, "kind": "code_execution", "detail": str(node_type)})
        elif node_type == "agent" and isinstance(node.get("config"), dict):
            items.extend(_tooling_items(node_id, node["config"].get("tooling"), unsafe))
    return items


def new_dangerous_tool_items(old: Any, new: Any) -> List[dict]:
    """``dangerous_tool_items(new)`` minus the ones ``old`` already had (unchanged, so not worth a warning).
    With no ``old`` (a new workflow) every item is new."""
    before = {(i["node"], i["kind"], i["detail"]) for i in dangerous_tool_items(old)} if old is not None else set()
    return [i for i in dangerous_tool_items(new) if (i["node"], i["kind"], i["detail"]) not in before]
