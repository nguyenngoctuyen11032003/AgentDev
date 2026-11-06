"""Input hardening shared by the connection routes and CLI providers."""

from __future__ import annotations

import os
import re
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from agentdev.utils.reserved_ports import PREVIEW_PORT_RANGE

_LOOPBACK = {"localhost", "127.0.0.1", "::1"}
MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,99}$")


def _host(url: str) -> Optional[str]:
    try:
        return (urlparse(url).hostname or "").lower() or None
    except ValueError:
        return None


def _env_list(name: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, "").split(",") if x.strip()]


def allowed_hosts() -> set[str]:
    """Hostnames the server answers to: loopback, the pytest client, plus AGENTDEV_ALLOWED_HOSTS."""
    return _LOOPBACK | {"testserver"} | {h.lower() for h in _env_list("AGENTDEV_ALLOWED_HOSTS")}


_HOST_RE = re.compile(r"^(\[[0-9a-f:]+\]|[a-z0-9.-]+)(:\d{1,5})?$", re.I)


def host_header_name(host_header: str) -> Optional[str]:
    """Hostname part of a strictly valid Host header (port and IPv6 brackets removed); None if malformed."""
    m = _HOST_RE.match((host_header or "").strip())
    if not m:
        return None
    return m.group(1).strip("[]").lower()


def host_allowed(host_header: str) -> bool:
    """False for foreign or malformed Host values (DNS rebinding). A missing Host is allowed (HTTP/1.0 tools)."""
    if not (host_header or "").strip():
        return True
    return host_header_name(host_header) in allowed_hosts()


def host_headers_ok(raw_values: list[str]) -> bool:
    """Every request carries at most one Host header and it must be allowed."""
    return len(raw_values) <= 1 and host_allowed(raw_values[0] if raw_values else "")


def is_preview_origin(origin: Optional[str]) -> bool:
    """A loopback origin on a Lab/Run preview port: a page an agent built, never trusted to call the API."""
    if not origin:
        return False
    try:
        parsed = urlparse(origin)
        port = parsed.port
    except ValueError:
        return False
    return (parsed.hostname or "").lower() in _LOOPBACK and port in PREVIEW_PORT_RANGE


def origin_allowed(origin: Optional[str]) -> bool:
    """True for no Origin, loopback origins (except preview ports) and origins listed in CORS_ALLOW_ORIGINS."""
    if not origin:
        return True
    if is_preview_origin(origin):
        return False
    if _host(origin) in _LOOPBACK:
        return True
    return origin.rstrip("/") in {o.rstrip("/") for o in _env_list("CORS_ALLOW_ORIGINS")}


def require_local_origin(request: Request) -> None:
    """Reject state-changing browser requests that come from another website (CSRF / DNS rebinding).

    Requests without an Origin header (curl, vite proxy, same-site navigations) pass when the Host is allowed.
    """
    if not host_headers_ok(request.headers.getlist("host")) or not origin_allowed(request.headers.get("origin")):
        raise HTTPException(status_code=403, detail="Cross-origin request blocked")
