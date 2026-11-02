"""Static catalog of the vendors a Connection can point at."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Auth methods a vendor can (eventually) support. Only ``api_key`` is implemented;
# the others are advertised so the UI can show them as "coming soon".
AUTH_API_KEY = "api_key"
AUTH_OAUTH = "oauth"
AUTH_CLI = "cli"


@dataclass(frozen=True)
class VendorInfo:
    id: str  # equals the registered provider name (openai / anthropic / gemini)
    label: str
    default_base_url: str
    env_key_hint: str
    models: Tuple[str, ...]
    auth_methods: Tuple[str, ...] = (AUTH_API_KEY,)
    cli_tools: bool = False  # whether the CLI provider can run agents that use tools
    cli_provider: str | None = None  # registered provider that drives the vendor's local CLI
    planned_auth_methods: Tuple[str, ...] = field(default_factory=tuple)

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "defaultBaseUrl": self.default_base_url,
            "envKeyHint": self.env_key_hint,
            "models": list(self.models),
            "authMethods": list(self.auth_methods),
            "plannedAuthMethods": list(self.planned_auth_methods),
            "cliProvider": self.cli_provider,
            "cliTools": self.cli_tools,
        }


VENDORS: Dict[str, VendorInfo] = {
    "anthropic": VendorInfo(
        id="anthropic",
        label="Anthropic Claude",
        default_base_url="https://api.anthropic.com",
        env_key_hint="ANTHROPIC_API_KEY",
        models=("claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"),
        auth_methods=(AUTH_API_KEY, AUTH_CLI),
        cli_provider="claude_cli",
        cli_tools=True,
    ),
    "openai": VendorInfo(
        id="openai",
        label="OpenAI",
        default_base_url="https://api.openai.com/v1",
        env_key_hint="API_KEY",
        models=("gpt-4o", "gpt-4o-mini", "gpt-4.1", "o4-mini"),
        auth_methods=(AUTH_API_KEY, AUTH_CLI),
        cli_provider="codex_cli",
    ),
    "gemini": VendorInfo(
        id="gemini",
        label="Google Gemini",
        default_base_url="https://generativelanguage.googleapis.com",
        env_key_hint="GEMINI_API_KEY",
        models=("gemini-2.5-pro", "gemini-2.5-flash"),
        auth_methods=(AUTH_API_KEY, AUTH_OAUTH),
    ),
}


def get_vendor(vendor_id: str) -> VendorInfo | None:
    return VENDORS.get(vendor_id)


def list_vendors() -> List[VendorInfo]:
    return list(VENDORS.values())
