"""Input hardening shared by the connection routes and CLI providers."""

from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException, Request

_LOOPBACK = {"localhost", "127.0.0.1", "::1"}
MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,99}$")


def _host(url: str) -> Optional[str]:
    try:
        return (urlparse(url).hostname or "").lower() or None
    except ValueError:
        return None


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
