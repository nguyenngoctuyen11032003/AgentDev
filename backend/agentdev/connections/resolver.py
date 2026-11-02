"""Turn a connection id into the credentials a provider client needs."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

import json

from agentdev.connections.catalog import AUTH_API_KEY, AUTH_CLI, AUTH_OAUTH, get_vendor
from agentdev.connections.security import UnsafeConnectionInput, check_env_ref_destination, is_allowed_env_name, validate_base_url
from agentdev.connections.store import get_store

_ENV_REF = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")


class ConnectionResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedCredentials:
    vendor: str
    api_key: str
    base_url: str
    provider: str = ""  # registered provider name to run the node with


def expand_secret(secret: str) -> str:
    """Resolve a ``${ENV_VAR}`` reference; plain values pass through."""
    match = _ENV_REF.match((secret or "").strip())
    if not match:
        return (secret or "").strip()
    return os.environ.get(match.group(1), "")


def _resolve_oauth(conn) -> ResolvedCredentials:
    from agentdev.connections import google_oauth
    from agentdev.connections.oauth_store import update_oauth_tokens
    from agentdev.runtime.node.agent.providers.gemini_provider import OAUTH_BEARER_PREFIX

    try:
        tokens = json.loads(conn.secret)
        token, updated = google_oauth.get_valid_access_token(tokens)
    except (ValueError, google_oauth.OAuthError) as exc:
        raise ConnectionResolutionError(
            f"Connection '{conn.id}': sign-in expired or invalid, please sign in again ({type(exc).__name__})."
        ) from exc
    if updated:
        update_oauth_tokens(conn.id, updated)
    return ResolvedCredentials(
        vendor=conn.vendor, api_key=OAUTH_BEARER_PREFIX + token, base_url=conn.base_url, provider=conn.vendor
    )


def resolve_connection(connection_id: str) -> ResolvedCredentials:
    conn = get_store().get(connection_id)
    if conn is None:
        raise ConnectionResolutionError(
            f"Connection '{connection_id}' not found. Create it on the Connections page."
        )
    vendor = get_vendor(conn.vendor)
    if conn.auth_type == AUTH_CLI:
        if vendor is None or not vendor.cli_provider:
            raise ConnectionResolutionError(f"Connection '{connection_id}': CLI sign-in is not available for '{conn.vendor}'.")
        return ResolvedCredentials(vendor=conn.vendor, api_key="", base_url="", provider=vendor.cli_provider)
    if conn.auth_type == AUTH_OAUTH:
        return _resolve_oauth(conn)
    if conn.auth_type != AUTH_API_KEY:
        raise ConnectionResolutionError(
            f"Connection '{connection_id}' uses unsupported auth type '{conn.auth_type}'."
        )
    env_match = _ENV_REF.match((conn.secret or "").strip())
    try:
        base_url = validate_base_url(conn.base_url)
        if env_match:
            if not is_allowed_env_name(env_match.group(1)):
                raise UnsafeConnectionInput(f"Environment variable '{env_match.group(1)}' cannot be used as a credential")
            check_env_ref_destination(base_url, vendor.default_base_url if vendor else "")
    except UnsafeConnectionInput as exc:
        raise ConnectionResolutionError(f"Connection '{connection_id}': {exc}") from exc
    api_key = expand_secret(conn.secret)
    if not api_key:
        raise ConnectionResolutionError(
            f"Connection '{connection_id}' has no usable credential (empty or unset env variable)."
        )
    return ResolvedCredentials(vendor=conn.vendor, api_key=api_key, base_url=conn.base_url, provider=conn.vendor)
