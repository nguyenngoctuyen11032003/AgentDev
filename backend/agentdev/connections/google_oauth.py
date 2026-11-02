"""Google OAuth 2.0 authorization-code flow (with PKCE) for Gemini sign-in.

The operator supplies their own OAuth client via ``GOOGLE_OAUTH_CLIENT_ID`` /
``GOOGLE_OAUTH_CLIENT_SECRET``. Redirect URI is
``{PUBLIC_BASE_URL}/api/connections/oauth/google/callback``.
Tokens are never logged.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlencode

import requests

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
# generative-language.retriever is the scope Google documents for OAuth access
# to the Gemini API (generativelanguage.googleapis.com).
SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/generative-language.retriever",
]
PENDING_TTL_SECONDS = 600
REFRESH_SKEW_SECONDS = 60
HTTP_TIMEOUT = 15

# http(method, url, **kwargs) -> requests.Response-like (status_code, json()).
HttpFn = Callable[..., Any]


def _default_http(method: str, url: str, **kwargs: Any) -> Any:
    kwargs.setdefault("timeout", HTTP_TIMEOUT)
    return requests.request(method, url, **kwargs)


_http: HttpFn = _default_http


def set_http(fn: Optional[HttpFn]) -> None:
    """Inject an HTTP function (tests). ``None`` restores the default."""
    global _http
    _http = fn or _default_http


class OAuthError(Exception):
    """OAuth flow failure. Messages never contain tokens."""


@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: str = ""
    expires_at: float = 0.0
    email: Optional[str] = None
    scope: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at,
            "email": self.email,
            "scope": self.scope,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OAuthTokens":
        return cls(
            access_token=str(data.get("access_token") or ""),
            refresh_token=str(data.get("refresh_token") or ""),
            expires_at=float(data.get("expires_at") or 0),
            email=data.get("email"),
            scope=str(data.get("scope") or ""),
        )


def _client_id() -> str:
    return os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()


def _client_secret() -> str:
    return os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()


def is_configured() -> bool:
    return bool(_client_id() and _client_secret())


def redirect_uri() -> str:
    base = os.environ.get("PUBLIC_BASE_URL", "").strip() or "http://localhost:8000"
    return f"{base.rstrip('/')}/api/connections/oauth/google/callback"


# -- pending states --------------------------------------------------------
_pending: Dict[str, Dict[str, Any]] = {}
_results: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def _now() -> float:
    return time.time()


def _purge(now: float) -> None:
    for table in (_pending, _results):
        for key in [k for k, v in table.items() if v["expires"] <= now]:
            del table[key]


def generate_pkce() -> Tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def start_login(label: str) -> Dict[str, str]:
    if not is_configured():
        raise OAuthError("Google OAuth is not configured")
    verifier, challenge = generate_pkce()
    state = secrets.token_urlsafe(32)
    now = _now()
    with _lock:
        _purge(now)
        _pending[state] = {
            "verifier": verifier,
            "label": (label or "").strip(),
            "expires": now + PENDING_TTL_SECONDS,
        }
    params = {
        "client_id": _client_id(),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    return {"auth_url": f"{AUTH_URL}?{urlencode(params)}", "state": state}


def peek_pending_label(state: str) -> Optional[str]:
    """Label stored for a pending state (does not consume it)."""
    with _lock:
        item = _pending.get(state)
        return item["label"] if item else None


def _email_from_id_token(id_token: str) -> Optional[str]:
    # Received directly from Google over TLS; used only for display.
    try:
        part = id_token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(part)).get("email")
    except Exception:
        return None


def _tokens_from_response(payload: Dict[str, Any], fallback_refresh: str = "") -> OAuthTokens:
    access = payload.get("access_token")
    if not access:
        raise OAuthError("token response missing access_token")
    id_token = payload.get("id_token")
    return OAuthTokens(
        access_token=access,
        refresh_token=payload.get("refresh_token") or fallback_refresh,
        expires_at=_now() + float(payload.get("expires_in") or 3600),
        email=_email_from_id_token(id_token) if id_token else None,
        scope=payload.get("scope") or "",
    )


def _post_token(data: Dict[str, str]) -> Dict[str, Any]:
    try:
        resp = _http("POST", TOKEN_URL, data=data, timeout=HTTP_TIMEOUT)
        body = resp.json()
    except Exception as exc:
        raise OAuthError("token endpoint request failed") from None
    if getattr(resp, "status_code", 200) >= 400 or not isinstance(body, dict):
        err = body.get("error") if isinstance(body, dict) else None
        raise OAuthError(f"token endpoint error: {err or 'unknown'}")
    return body


def complete_login(state: str, code: str) -> OAuthTokens:
    now = _now()
    with _lock:
        _purge(now)
        entry = _pending.pop(state, None)  # single use
    if entry is None:
        raise OAuthError("invalid or expired state")
    if not code:
        raise OAuthError("missing code")
    body = _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri(),
            "client_id": _client_id(),
            "client_secret": _client_secret(),
            "code_verifier": entry["verifier"],
        }
    )
    return _tokens_from_response(body)


def refresh(tokens: OAuthTokens) -> OAuthTokens:
    if not tokens.refresh_token:
        raise OAuthError("no refresh token; sign in again")
    body = _post_token(
        {
            "grant_type": "refresh_token",
            "refresh_token": tokens.refresh_token,
            "client_id": _client_id(),
            "client_secret": _client_secret(),
        }
    )
    new = _tokens_from_response(body, fallback_refresh=tokens.refresh_token)
    new.email = new.email or tokens.email
    new.scope = new.scope or tokens.scope
    return new


def get_valid_access_token(tokens_dict: Dict[str, Any]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """Return (access_token, updated_tokens_dict or None if unchanged)."""
    tokens = OAuthTokens.from_dict(tokens_dict)
    if tokens.access_token and tokens.expires_at - _now() > REFRESH_SKEW_SECONDS:
        return tokens.access_token, None
    new = refresh(tokens)
    return new.access_token, new.to_dict()


# -- result tracking for UI polling ---------------------------------------
def record_result(state: str, ok: bool) -> None:
    with _lock:
        _results[state] = {
            "status": "done" if ok else "error",
            "expires": _now() + PENDING_TTL_SECONDS,
        }


def poll(state: str) -> str:
    now = _now()
    with _lock:
        _purge(now)
        if state in _results:
            return _results[state]["status"]
        if state in _pending:
            return "pending"
    return "error"
