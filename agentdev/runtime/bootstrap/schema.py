"""Ensure schema registry is populated with runtime-provided registrations."""

from importlib import import_module
from typing import Iterable

_BOOTSTRAPPED = False


def _modules_to_import() -> Iterable[str]:
    return (
        "agentdev.runtime.node.builtin_nodes",
        "agentdev.runtime.node.agent.memory.builtin_stores",
        "agentdev.runtime.node.agent.thinking.builtin_thinking",
        "agentdev.runtime.edge.conditions.builtin_types",
        "agentdev.runtime.node.agent.providers.builtin_providers",
    )


def ensure_schema_registry_populated() -> None:
    """Import built-in runtime registration modules exactly once."""
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED:
        return

    for module_name in _modules_to_import():
        import_module(module_name)

    _BOOTSTRAPPED = True
