"""Switch an agent to another signed-in account when its account runs out of quota.

Claude and Codex subscriptions have usage windows. When one account answers with a usage /
rate limit error, the run continues on another signed-in account (Claude -> Codex, Codex ->
Claude, then Gemini), and the user is told which account took over. The switch is remembered
for the rest of the run, so later agents go straight to the working account.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Set

from agentdev.connections.catalog import AUTH_CLI, AUTH_OAUTH, get_vendor
from agentdev.connections.store import Connection, get_store

# Phrases vendors use when an account's usage window / credits are used up. Deliberately tight:
# transient 429 / "rate limit" errors are retried normally instead, and generic words such as
# "quota" or "limit reached" also occur in stack traces and in the model's own output.
QUOTA_PATTERN = re.compile(
    r"usage limit reached|hit your usage limit|reached your (?:usage|weekly|daily|monthly|5-hour) limit|"
    r"usage_limit_reached|(?:5-hour|weekly|session) limit reached|credit balance is too low|out of credits|"
    r"insufficient_quota|exceeded your current quota|quota exceeded for quota metric|resource_exhausted.*quota",
    re.IGNORECASE,
)

# Preferred replacement vendor for each vendor.
_PREFERRED = {"anthropic": ["openai", "gemini"], "openai": ["anthropic", "gemini"], "gemini": ["anthropic", "openai"]}


class QuotaExceededError(RuntimeError):
    """The account behind this agent has no quota left right now."""


def is_quota_error(exc: BaseException) -> bool:
    """True only for a provider-raised QuotaExceededError (anywhere in the cause chain)."""
    seen = 0
    current: Optional[BaseException] = exc
    while current is not None and seen < 6:
        if isinstance(current, QuotaExceededError):
            return True
        current = current.__cause__ or current.__context__
        seen += 1
    return False


def is_exhaustion_error(exc: BaseException) -> bool:
    """After normal retries failed: a QuotaExceededError, or an error whose own message (not its
    causes) uses one of the tight usage-exhausted phrases (e.g. Gemini RESOURCE_EXHAUSTED quota)."""
    return is_quota_error(exc) or bool(QUOTA_PATTERN.search(str(exc) or ""))


def looks_like_quota(text: str) -> bool:
    return bool(text and QUOTA_PATTERN.search(text))


@dataclass
class FallbackState:
    """Per-run memory: exhausted connections and what replaced them."""

    exhausted: Set[str] = field(default_factory=set)
    replacement: Dict[str, str] = field(default_factory=dict)


def get_fallback_state(global_state: Dict) -> FallbackState:
    state = global_state.get("_account_fallback")
    if not isinstance(state, FallbackState):
        state = FallbackState()
        global_state["_account_fallback"] = state
    return state


def _usable(conn: Connection, needs_tools: bool) -> bool:
    if conn.auth_type not in (AUTH_CLI, AUTH_OAUTH):
        return False
    if not needs_tools or conn.auth_type != AUTH_CLI:
        return True
    vendor = get_vendor(conn.vendor)
    return bool(vendor and vendor.cli_tools)


def pick_fallback(
    current_id: str,
    *,
    needs_tools: bool,
    exhausted: Iterable[str],
    connections: Optional[list] = None,
) -> Optional[Connection]:
    """Another signed-in account to continue on, other vendors first."""
    pool = connections if connections is not None else get_store().list()
    skip = set(exhausted) | {current_id}
    current = next((c for c in pool if c.id == current_id), None)
    candidates = [c for c in pool if c.id not in skip and _usable(c, needs_tools)]
    if current is not None and current.auth_type == AUTH_CLI:
        # CLI connections of one vendor share the machine's single CLI login: same exhausted account.
        candidates = [c for c in candidates if not (c.vendor == current.vendor and c.auth_type == AUTH_CLI)]
    if not candidates:
        return None
    order = _PREFERRED.get(current.vendor if current else "", [])

    def rank(conn: Connection) -> int:
        if current is not None and conn.vendor == current.vendor:
            return len(order) + 1  # same vendor (another account) after other vendors
        return order.index(conn.vendor) if conn.vendor in order else len(order)

    return sorted(candidates, key=rank)[0]


def default_model_for(conn: Connection) -> Optional[str]:
    try:
        from agentdev.connections.autobind import _default_model

        model = _default_model(conn)
    except Exception:  # noqa: BLE001 - best effort
        model = None
    if model:
        return model
    vendor = get_vendor(conn.vendor)
    return vendor.models[0] if vendor and vendor.models else None


def account_label(conn_id: str) -> str:
    try:
        conn = get_store().get(conn_id)
    except Exception:  # noqa: BLE001
        conn = None
    if conn is None:
        return conn_id
    return conn.label or conn.id
