"""Input hardening shared by the connection routes, resolver and providers."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException, Request

_LOOPBACK = {"localhost", "127.0.0.1", "::1"}
_ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")
# Only credential-looking variables may be referenced as ${NAME}; this stops a connection
# from being used to read arbitrary server environment variables (e.g. OAuth client secrets).
_ENV_SUFFIXES = ("_API_KEY", "_AUTH_TOKEN", "_ACCESS_TOKEN")
MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,99}$")


class UnsafeConnectionInput(ValueError):
    pass


def is_allowed_env_name(name: str) -> bool:
    return bool(_ENV_NAME.match(name)) and (name == "API_KEY" or name.endswith(_ENV_SUFFIXES))


def _host(url: str) -> Optional[str]:
    try:
        return (urlparse(url).hostname or "").lower() or None
    except ValueError:
        return None


def validate_base_url(url: str) -> str:
    """https only (plain http just for loopback); no embedded credentials."""
    url = (url or "").strip()
    if not url:
        return ""
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise UnsafeConnectionInput("Base URL is not a valid URL") from exc
    host = (parsed.hostname or "").lower()
    if not host or parsed.username or parsed.password:
        raise UnsafeConnectionInput("Base URL is not valid")
    if parsed.scheme == "https" or (parsed.scheme == "http" and host in _LOOPBACK):
        return url
    raise UnsafeConnectionInput("Base URL must use https (http is only allowed for localhost)")


def check_env_ref_destination(base_url: str, default_base_url: str) -> None:
    """A key read from the environment may only be sent to the vendor's own host or localhost."""
    host = _host(base_url) if base_url else None
    if host is None or host in _LOOPBACK or host == _host(default_base_url):
        return
    raise UnsafeConnectionInput(
        "A key taken from an environment variable can only be used with the provider's default URL or localhost"
    )


def require_local_origin(request: Request) -> None:
    """Reject state-changing browser requests that come from another website (CSRF).

    Requests without an Origin header (curl, scripts, same-site navigations) pass.
    """
    origin = request.headers.get("origin")
    if not origin:
        return
    origin_host = _host(origin)
    request_host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
    if origin_host in _LOOPBACK or (origin_host and origin_host == request_host):
        return
    raise HTTPException(status_code=403, detail="Cross-origin request blocked")
