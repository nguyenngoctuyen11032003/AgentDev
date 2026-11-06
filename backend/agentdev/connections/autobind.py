"""Run agent nodes that name no connection on one of the signed-in accounts.

Older workflows describe each agent with ``provider: anthropic`` (plus an ``api_key`` that is
no longer used). At run time every such node is bound to a saved account connection: the same
vendor when one is signed in (anthropic -> Claude, openai -> Codex, gemini -> Google), otherwise
the default connection (or any account that can run the node) with the model switched to that
account's default. A node that names no provider uses the default connection and keeps its model.
Leftover ``api_key`` / ``base_url`` keys are dropped so no credential is ever read from YAML.
"""

from __future__ import annotations

import logging
import re
from typing import Any, List, Mapping, MutableMapping, Optional

from agentdev.connections.catalog import AUTH_CLI, get_vendor, is_account_auth, is_retired_model, replace_retired_model
from agentdev.connections.store import Connection, get_store
from agentdev.entity.configs import ConfigError


class NoSignedInAccountError(ConfigError):
    """No signed-in account can run an agent of the workflow: the machine's accounts, not the workflow."""


logger = logging.getLogger(__name__)

# Provider names found in YAML -> the vendor whose account should run the node
_VENDOR_OF = {
    "anthropic": "anthropic",
    "claude_cli": "anthropic",
    "openai": "openai",
    "codex_cli": "openai",
    "gemini": "gemini",
}
# Model-name prefixes -> vendor, for a node that names a model but no provider
_MODEL_PREFIX_VENDOR = (
    (("claude",), "anthropic"),
    (("gpt", "codex", "o1", "o3", "o4"), "openai"),
    (("gemini",), "gemini"),
)
_LEGACY_KEYS = ("api_key", "base_url")
_PLACEHOLDER = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


def _agent_config(node: Mapping[str, Any]) -> Optional[MutableMapping[str, Any]]:
    """The ``config`` of a graph node of type ``agent`` (nested subgraphs are walked too)."""
    if node.get("type") != "agent":
        return None
    config = node.get("config")
    return config if isinstance(config, MutableMapping) and isinstance(config.get("name"), str) else None


def strip_legacy_keys(value: Any) -> Any:
    """Drop the legacy credential keys (``_LEGACY_KEYS``) from every agent config, nested subgraphs too, in place.

    Old workflows carried them; models now run only on a signed-in account, so they are ignored the same way on
    every load path (run, save, Lab check, file subgraph) instead of loading on one path and failing on another.
    """
    if isinstance(value, MutableMapping):
        config = _agent_config(value)
        if config is not None:
            for key in _LEGACY_KEYS:
                config.pop(key, None)
        for child in value.values():
            strip_legacy_keys(child)
    elif isinstance(value, list):
        for child in value:
            strip_legacy_keys(child)
    return value


def _vendor_of_model(name: Any) -> str:
    """The vendor a literal model name belongs to ("" for a placeholder or an unknown name)."""
    text = str(name or "").strip().lower()
    if not text or text.startswith("$"):
        return ""
    for prefixes, vendor in _MODEL_PREFIX_VENDOR:
        if text.startswith(prefixes):
            return vendor
    return ""


def _serves(conn: Connection, needs_tools: bool) -> bool:
    if not is_account_auth(conn.auth_type):
        return False
    if not needs_tools or conn.auth_type != AUTH_CLI:
        return True
    vendor = get_vendor(conn.vendor)
    return bool(vendor and vendor.cli_tools)


def _pick(connections: List[Connection], vendor_id: str, needs_tools: bool) -> Optional[Connection]:
    usable = [c for c in connections if _serves(c, needs_tools)]
    same = [c for c in usable if c.vendor == vendor_id]
    return (same or usable or [None])[0]


def bind_default_connections(
    data: MutableMapping[str, Any],
    env_lookup: Mapping[str, Any],
    *,
    require_accounts: bool = True,
) -> None:
    """Fill in ``connection`` for agent configs that have none, and a model name when the
    YAML's ``${MODEL_NAME}``-style placeholder is set nowhere (env or workflow vars)."""
    vars_ = data.get("vars") if isinstance(data.get("vars"), Mapping) else {}
    store = get_store()
    connections = store.list()
    # The default connection (Claude unless changed on the Connections page) runs every node.
    default = store.default_connection()

    def fill_unset_model(node: MutableMapping[str, Any], path: str) -> None:
        match = _PLACEHOLDER.match(str(node.get("name") or "").strip())
        if not match or match.group(1) in env_lookup or match.group(1) in vars_:
            return
        conn = next((c for c in connections if c.id == node.get("connection")), None)
        vendor = get_vendor(conn.vendor) if conn else None
        model = (_default_model(conn) if conn else None) or (vendor.models[0] if vendor and vendor.models else None)
        if model:
            logger.info("%s: %s is not set; using the account's default model %s", path, match.group(0), model)
            node["name"] = model

    def swap_retired_model(node: MutableMapping[str, Any], path: str) -> None:
        conn = next((c for c in connections if c.id == node.get("connection")), None)
        name = node.get("name")
        if conn is not None and isinstance(name, str) and is_retired_model(conn.vendor, name):
            replacement = replace_retired_model(conn.vendor, name)
            logger.warning("%s: model %s is retired; using %s", path, name, replacement)
            node["name"] = replacement

    def handle(node: MutableMapping[str, Any], path: str) -> None:
        for key in _LEGACY_KEYS:
            node.pop(key, None)
        if node.get("connection"):
            fill_unset_model(node, path)
            swap_retired_model(node, path)
            return
        provider = node.get("provider") or ""
        vendor_id = _VENDOR_OF.get(provider, provider) or _vendor_of_model(node.get("name"))
        needs_tools = bool(node.get("tooling"))
        same_vendor = [c for c in connections if c.vendor == vendor_id and _serves(c, needs_tools)] if vendor_id else []
        if same_vendor:
            # The named vendor wins over the default; the default connection is preferred among its accounts.
            chosen = default if default in same_vendor else same_vendor[0]
        elif default is not None and _serves(default, needs_tools):
            chosen = default
        else:
            chosen = _pick(connections, vendor_id, needs_tools)
        if chosen is None:
            if not require_accounts:
                # Validation only (e.g. CI): accounts are per machine, so leave the node unbound.
                return
            vendor = get_vendor(vendor_id)
            label = vendor.label if vendor else (provider or "a model provider")
            raise NoSignedInAccountError(
                f"No signed-in account can run this agent: sign in to {label} on the Connections page "
                "and pick the connection on the node.",
                path,
            )
        node["connection"] = chosen.id
        if vendor_id and chosen.vendor != vendor_id:
            # The model name belongs to another vendor: use this account's default model instead.
            vendor = get_vendor(chosen.vendor)
            if vendor and vendor.models:
                logger.warning(
                    "%s: no %s account signed in; running on %s (%s) with model %s",
                    path, vendor_id, chosen.id, chosen.vendor, _default_model(chosen) or vendor.models[0],
                )
                node["name"] = _default_model(chosen) or vendor.models[0]
        fill_unset_model(node, path)
        swap_retired_model(node, path)

    def walk(value: Any, path: str) -> None:
        if isinstance(value, MutableMapping):
            config = _agent_config(value)
            if config is not None:
                handle(config, f"{path}.config")
            for key, child in list(value.items()):
                walk(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(data.get("graph"), "root.graph")


def _default_model(conn: Connection) -> Optional[str]:
    """First model the account itself lists (falls back to the static catalog upstream)."""
    try:
        from agentdev.connections.account_info import account_info

        models = account_info(conn).get("models") or []
    except Exception:  # noqa: BLE001 - best effort; the catalog default is fine
        return None
    primary = [m for m in models if m.get("primary")] or models
    return primary[0]["id"] if primary else None
