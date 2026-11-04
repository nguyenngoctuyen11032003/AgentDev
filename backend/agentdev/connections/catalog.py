"""Static catalog of the vendors a Connection can point at."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

# Connections always sign in with an account: the vendor's own CLI (Claude Code / Codex)
# or Google OAuth. Any other auth type found in storage was saved by an older version
# (API keys) and only loads so the user can be told to sign in again.
AUTH_OAUTH = "oauth"
AUTH_CLI = "cli"
ACCOUNT_AUTH_TYPES = frozenset({AUTH_CLI, AUTH_OAUTH})


def is_account_auth(auth_type: str) -> bool:
    """True when ``auth_type`` is an account sign-in this version can run."""
    return auth_type in ACCOUNT_AUTH_TYPES


@dataclass(frozen=True)
class VendorInfo:
    id: str  # equals the registered provider name (openai / anthropic / gemini)
    label: str
    models: Tuple[str, ...]  # fallback list when the account's own model catalog is unavailable
    auth_methods: Tuple[str, ...] = (AUTH_CLI,)
    cli_tools: bool = False  # whether the CLI provider can run agents that use tools
    cli_provider: str | None = None  # registered provider that drives the vendor's local CLI

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "models": list(self.models),
            "authMethods": list(self.auth_methods),
            "cliProvider": self.cli_provider,
            "cliTools": self.cli_tools,
        }


VENDORS: Dict[str, VendorInfo] = {
    "anthropic": VendorInfo(
        id="anthropic",
        label="Anthropic Claude",
        models=("claude-fable-5-1", "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"),
        auth_methods=(AUTH_CLI,),
        cli_provider="claude_cli",
        cli_tools=True,
    ),
    "openai": VendorInfo(
        id="openai",
        label="OpenAI",
        models=("gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-luna", "gpt-5.6-sol"),
        auth_methods=(AUTH_CLI,),
        cli_provider="codex_cli",
        cli_tools=True,
    ),
    "gemini": VendorInfo(
        id="gemini",
        label="Google Gemini",
        # The 2.5 models now answer 404 "no longer available to new users". The first entry is the
        # default; the Pro preview exists but may hit the account's quota (429).
        models=("gemini-3-flash-preview", "gemini-3.1-pro-preview"),
        auth_methods=(AUTH_OAUTH,),
    ),
}


def get_vendor(vendor_id: str) -> VendorInfo | None:
    return VENDORS.get(vendor_id)


def list_vendors() -> List[VendorInfo]:
    return list(VENDORS.values())


# Model ids a vendor has switched off (the API answers 404 "no longer available"). Saved workflows may
# still name them; ``replace_retired_model`` swaps them for the vendor's default at bind time.
_RETIRED_EXACT = {
    "gemini": frozenset({"gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"}),
}
_RETIRED_PREFIXES = {"gemini": ("gemini-1.5-", "gemini-2.0-")}


def is_retired_model(vendor_id: str, model: str) -> bool:
    name = (model or "").strip().lower()
    return name in _RETIRED_EXACT.get(vendor_id, ()) or name.startswith(_RETIRED_PREFIXES.get(vendor_id, ()))


def replace_retired_model(vendor_id: str, model: str) -> str:
    """``model`` unchanged, or the vendor's catalog default when ``model`` is retired."""
    vendor = get_vendor(vendor_id)
    if vendor and vendor.models and is_retired_model(vendor_id, model):
        return vendor.models[0]
    return model
