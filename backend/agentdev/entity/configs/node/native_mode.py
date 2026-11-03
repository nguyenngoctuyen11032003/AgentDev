"""Native agent mode: run an agent node as a full Claude Code / Codex agent in the project workspace."""

from dataclasses import dataclass
from typing import Any, Dict, Mapping

from agentdev.entity.configs.base import (
    BaseConfig,
    ConfigError,
    ConfigFieldSpec,
    extend_path,
    optional_bool,
    require_mapping,
)

DEFAULT_NATIVE_MAX_TURNS = 60
MAX_NATIVE_MAX_TURNS = 500


@dataclass
class AgentNativeModeConfig(BaseConfig):
    """Hands the whole task to the vendor CLI's own agent loop.

    With ``enabled`` the node runs ``claude -p`` / ``codex exec`` with the session's project folder as
    its working directory and the CLI's built-in file tools (read, search, edit). AgentDev tools
    (function tools, skills, team delegation) are not offered in this mode; the agent's final text is
    the node's answer. Team leads always run in normal mode. ``allow_commands`` additionally lets the
    agent run shell commands (tests, builds), and only takes effect when the server sets
    ``MAC_ALLOW_UNSAFE_CODE_EXECUTION=1``.
    """

    enabled: bool = False
    allow_commands: bool = False
    max_turns: int = DEFAULT_NATIVE_MAX_TURNS

    FIELD_SPECS = {
        "enabled": ConfigFieldSpec(
            name="enabled",
            display_name="Native coding agent",
            type_hint="bool",
            required=False,
            default=False,
            description="Run this agent as a full Claude Code / Codex agent inside the project folder: it reads, "
            "searches and edits files itself. AgentDev tools are not used in this mode. Ignored for team leads.",
        ),
        "allow_commands": ConfigFieldSpec(
            name="allow_commands",
            display_name="Allow shell commands",
            type_hint="bool",
            required=False,
            default=False,
            description="Let the agent run shell commands (tests, builds). Only takes effect when the server "
            "opts in with MAC_ALLOW_UNSAFE_CODE_EXECUTION=1; commands are not sandboxed for Claude.",
        ),
        "max_turns": ConfigFieldSpec(
            name="max_turns",
            display_name="Max agent turns",
            type_hint="int",
            required=False,
            default=DEFAULT_NATIVE_MAX_TURNS,
            description="Upper bound on the agent's tool-use turns for one task (Claude CLI), to cap token use.",
            advance=True,
        ),
    }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any], *, path: str) -> "AgentNativeModeConfig":
        if isinstance(data, bool):  # shorthand: ``native_mode: true``
            return cls(enabled=data, path=path)
        mapping = require_mapping(data, path)
        enabled = optional_bool(mapping, "enabled", path, default=False)
        allow_commands = optional_bool(mapping, "allow_commands", path, default=False)
        max_turns = mapping.get("max_turns")
        if max_turns is None:
            max_turns = DEFAULT_NATIVE_MAX_TURNS
        elif isinstance(max_turns, bool) or not isinstance(max_turns, int) or not 1 <= max_turns <= MAX_NATIVE_MAX_TURNS:
            raise ConfigError(
                f"max_turns must be an integer between 1 and {MAX_NATIVE_MAX_TURNS}",
                extend_path(path, "max_turns"),
            )
        return cls(enabled=bool(enabled), allow_commands=bool(allow_commands), max_turns=max_turns, path=path)

    @classmethod
    def field_specs(cls) -> Dict[str, ConfigFieldSpec]:
        return super().field_specs()
