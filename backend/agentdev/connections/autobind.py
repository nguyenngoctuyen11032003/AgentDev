"""Let legacy agent nodes use saved connections without editing their YAML.

Older workflows hard-code ``api_key: ${ANTHROPIC_API_KEY}`` in every node. When that
variable is not set anywhere (environment or workflow ``vars``), the node is bound to a
saved connection for the same provider instead of failing with "Unresolved placeholder".
Nodes that already work (variable present) or that name a ``connection`` are untouched.
"""

from __future__ import annotations

import re
from typing import Any, List, Mapping, MutableMapping, Optional

from agentdev.connections.catalog import AUTH_CLI, VENDORS, get_vendor
from agentdev.connections.store import Connection, get_store
from agentdev.entity.configs import ConfigError

_PLACEHOLDER = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def _unresolved_name(value: Any, env: Mapping[str, Any], vars_: Mapping[str, Any]) -> Optional[str]:
    if not isinstance(value, str):
        return None
    match = _PLACEHOLDER.match(value.strip())
    if not match:
        return None
    name = match.group(1)
    return None if (name in env or name in vars_) else name


def _is_agent_config(node: Mapping[str, Any]) -> bool:
    return (
        isinstance(node.get("provider"), str)
        and node["provider"] in VENDORS
        and isinstance(node.get("name"), str)
        and "api_key" in node
        and not node.get("connection")
    )


def _pick(candidates: List[Connection], needs_tools: bool) -> Optional[Connection]:
    # Not every CLI can drive tools (Claude can, Codex cannot): such nodes need an API key / OAuth connection.
    def serves(conn: Connection) -> bool:
        if not needs_tools or conn.auth_type != AUTH_CLI:
            return True
        vendor = get_vendor(conn.vendor)
        return bool(vendor and vendor.cli_tools)

    usable = [c for c in candidates if serves(c)]
    return usable[0] if usable else None


def bind_default_connections(data: MutableMapping[str, Any], env_lookup: Mapping[str, Any]) -> None:
    vars_ = data.get("vars") or {}
    connections = get_store().list()

    def handle(node: MutableMapping[str, Any], path: str) -> None:
        missing = _unresolved_name(node.get("api_key"), env_lookup, vars_)
        if missing is None:
            return
        provider = node["provider"]
        vendor = get_vendor(provider)
        label = vendor.label if vendor else provider
        candidates = [c for c in connections if c.vendor == provider]
        needs_tools = bool(node.get("tooling"))
        chosen = _pick(candidates, needs_tools)
        if chosen is not None:
            node["connection"] = chosen.id
            node.pop("api_key", None)
            node.pop("base_url", None)
            return
        if candidates and needs_tools:
            raise ConfigError(
                f"This agent uses tools, which are not available with account (CLI) sign-in. "
                f"Connect {label} with an API key on the Connections page, or set {missing}.",
                path,
            )
        raise ConfigError(
            f"No credential for {label}: add a connection on the Connections page, or set {missing}.",
            path,
        )

    def walk(value: Any, path: str) -> None:
        if isinstance(value, MutableMapping):
            if _is_agent_config(value):
                handle(value, path)
            for key, child in list(value.items()):
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(data.get("graph"), "root.graph")
