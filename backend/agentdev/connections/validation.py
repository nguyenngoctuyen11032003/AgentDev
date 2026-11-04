"""Static pre-flight check of connection references in a workflow document.

Never returns secrets and never touches the network.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Mapping

from agentdev.connections.catalog import is_account_auth
from agentdev.connections import store as _store_module
from agentdev.paths import WORKFLOWS_DIR
from agentdev.utils.exceptions import ValidationError
from agentdev.utils.io_utils import read_yaml
from agentdev.utils.workspace_paths import resolve_workspace_path

_PLACEHOLDER = re.compile(r"\$\{[^}]*\}")
_MAX_DEPTH = 8


def _graph_nodes(doc: Any) -> list:
    if not isinstance(doc, Mapping):
        return []
    graph = doc.get("graph")
    block = graph if isinstance(graph, Mapping) else doc
    nodes = block.get("nodes")
    return nodes if isinstance(nodes, list) else []


def _load_subgraph_file(rel: str) -> Any:
    parts = [p for p in re.split(r"[\/]+", rel.strip()) if p]
    if not parts:
        return None
    try:
        path: Path = resolve_workspace_path(WORKFLOWS_DIR, *parts)
        if not path.is_file():
            return None
        return path, read_yaml(path)
    except (ValidationError, OSError, ValueError, Exception):
        return None


def check_workflow_connections(document: Mapping) -> List[Dict[str, str]]:
    problems: List[Dict[str, str]] = []
    store = _store_module.get_store()

    def check_agent(node_id: str, conn_id: str) -> None:
        if _PLACEHOLDER.search(conn_id):
            return  # resolved at runtime from vars/env; cannot judge statically
        conn = store.get(conn_id)
        if conn is None:
            problem, msg = "missing", f"Connection '{conn_id}' does not exist."
        elif not is_account_auth(conn.auth_type):
            from agentdev.connections.resolver import sign_in_again_message

            problem, msg = "unsupported_auth", sign_in_again_message(conn_id)
        else:
            return
        problems.append({"nodeId": node_id, "connection": conn_id, "problem": problem, "message": msg})

    def walk(doc: Any, prefix: str, seen: frozenset, depth: int) -> None:
        if depth > _MAX_DEPTH:
            return
        for node in _graph_nodes(doc):
            if not isinstance(node, Mapping):
                continue
            nid = f"{prefix}{node.get('id', '')}"
            cfg = node.get("config")
            if not isinstance(cfg, Mapping):
                continue
            ntype = node.get("type")
            if ntype == "agent":
                conn = cfg.get("connection")
                if isinstance(conn, str) and conn.strip():
                    check_agent(nid, conn.strip())
            elif ntype == "subgraph":
                inner = cfg.get("config")
                if not isinstance(inner, Mapping):
                    continue
                if cfg.get("type") == "file":
                    rel = inner.get("path")
                    loaded = _load_subgraph_file(rel) if isinstance(rel, str) else None
                    if not loaded:
                        continue
                    path, sub = loaded
                    if path in seen:
                        continue
                    walk(sub, f"{nid}/", seen | {path}, depth + 1)
                else:
                    walk(inner, f"{nid}/", seen, depth + 1)

    walk(document, "", frozenset(), 0)
    return problems
