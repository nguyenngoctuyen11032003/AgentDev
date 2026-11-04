"""Models a connection's account can actually use, for the model pickers in the UI.

Order of truth per connection:
  * CLI account (Claude / Codex): the model catalog the CLI itself cached for that account.
  * Google sign-in: Gemini's live ``models`` listing.
  * Otherwise (offline, listing failed): the static catalog, flagged ``source: "catalog"``.

Only model ids and display names leave this module; credentials are never returned or logged.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List

from agentdev.connections.account_info import account_info
from agentdev.connections.catalog import AUTH_CLI, AUTH_OAUTH, get_vendor, is_retired_model
from agentdev.connections.resolver import ConnectionResolutionError, resolve_connection
from agentdev.connections.store import Connection

_TIMEOUT = 15
_GEMINI_BASE = "https://generativelanguage.googleapis.com"


def _model(model_id: str, name: str | None = None, primary: bool = False) -> Dict[str, Any]:
    return {"id": model_id, "name": name or model_id, "primary": primary}


def _fallback(vendor_id: str) -> List[Dict[str, Any]]:
    vendor = get_vendor(vendor_id)
    return [_model(mid, primary=True) for mid in (vendor.models if vendor else ())]


# Models that answer generateContent but are not usable as an agent's chat/coding model:
# speech, image, transcription, robotics, computer-use and the like.
_NON_CHAT_MARKERS = ("tts", "image", "transcribe", "robotics", "computer-use", "nano-banana", "omni", "live", "audio", "embedding")


def _is_non_chat(model_id: str) -> bool:
    lowered = model_id.lower()
    return any(marker in lowered for marker in _NON_CHAT_MARKERS)


def _gemini(headers: Dict[str, str], base_url: str) -> List[Dict[str, Any]]:
    root = (base_url or _GEMINI_BASE).rstrip("/")
    models: List[Dict[str, Any]] = []
    page = ""
    for _ in range(5):  # a handful of pages is plenty
        url = f"{root}/v1beta/models?pageSize=100" + (f"&pageToken={page}" if page else "")
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:  # noqa: S310 - https vendor URL
            data = json.loads(response.read().decode("utf-8"))
        for item in data.get("models", []):
            name = str(item.get("name", "")).split("/", 1)[-1]
            if (
                name.startswith("gemini")
                and "generateContent" in (item.get("supportedGenerationMethods") or [])
                and not _is_non_chat(name)
                and not is_retired_model("gemini", name)
            ):
                models.append(_model(name, item.get("displayName")))
        page = data.get("nextPageToken") or ""
        if not page:
            break
    return models


def _remote(conn: Connection) -> List[Dict[str, Any]]:
    if conn.vendor != "gemini":
        raise ValueError(f"Unsupported vendor '{conn.vendor}'")
    token = resolve_connection(conn.id).token
    headers = {"Authorization": f"Bearer {token[len('oauth-bearer:'):]}"}
    return _gemini(headers, conn.base_url or "")


def connection_models(conn: Connection) -> Dict[str, Any]:
    """Return ``{ok, source, models, error}``; never raises."""
    if conn.auth_type == AUTH_CLI:
        account = account_info(conn)
        models = account.get("models") or []
        if account.get("loggedIn") is not True:
            return {"ok": False, "source": "catalog", "models": _fallback(conn.vendor), "error": account.get("detail", "")}
        if models:
            return {"ok": True, "source": "account", "models": models, "error": None}
        return {"ok": True, "source": "catalog", "models": _fallback(conn.vendor), "error": None}

    if conn.auth_type != AUTH_OAUTH:
        return {"ok": False, "source": "catalog", "models": _fallback(conn.vendor), "error": "Sign in again with an account"}
    try:
        models = _remote(conn)
    except ConnectionResolutionError as exc:
        return {"ok": False, "source": "catalog", "models": _fallback(conn.vendor), "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - surfaced as a flag; SDK messages can echo secrets
        status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
        detail = type(exc).__name__ + (f" (HTTP {status})" if status else "")
        return {"ok": False, "source": "catalog", "models": _fallback(conn.vendor), "error": detail}
    if not models:
        return {"ok": True, "source": "catalog", "models": _fallback(conn.vendor), "error": None}
    # Put the vendor's headline models first so the picker opens on sensible choices.
    featured = set(get_vendor(conn.vendor).models) if get_vendor(conn.vendor) else set()
    for item in models:
        item["primary"] = item["id"] in featured
    models.sort(key=lambda m: not m["primary"])
    return {"ok": True, "source": "api", "models": models, "error": None}
