"""Turn a connection id into what a provider needs to run a node with that account."""

from __future__ import annotations

import json
from dataclasses import dataclass

from agentdev.connections.catalog import AUTH_API_KEY, AUTH_CLI, AUTH_OAUTH, get_vendor
from agentdev.connections.store import get_store


class ConnectionResolutionError(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedCredentials:
    vendor: str
    provider: str  # registered provider name to run the node with
    # Google sign-in only: the OAuth access token, passed to the Gemini provider as
    # "oauth-bearer:<token>". CLI accounts keep their own login, so this stays empty.
    token: str = ""
    base_url: str = ""


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
        vendor=conn.vendor, provider=conn.vendor, token=OAUTH_BEARER_PREFIX + token, base_url=conn.base_url
    )


def resolve_connection(connection_id: str) -> ResolvedCredentials:
    conn = get_store().get(connection_id)
    if conn is None:
        raise ConnectionResolutionError(
            f"Connection '{connection_id}' not found. Sign in to an account on the Connections page."
        )
    vendor = get_vendor(conn.vendor)
    if conn.auth_type == AUTH_CLI:
        if vendor is None or not vendor.cli_provider:
            raise ConnectionResolutionError(f"Connection '{connection_id}': account sign-in is not available for '{conn.vendor}'.")
        return ResolvedCredentials(vendor=conn.vendor, provider=vendor.cli_provider)
    if conn.auth_type == AUTH_OAUTH:
        return _resolve_oauth(conn)
    if conn.auth_type == AUTH_API_KEY:
        raise ConnectionResolutionError(
            f"Connection '{connection_id}' uses an API key, which is no longer supported. "
            "Sign out of it and sign in with an account on the Connections page."
        )
    raise ConnectionResolutionError(f"Connection '{connection_id}' uses unsupported auth type '{conn.auth_type}'.")
