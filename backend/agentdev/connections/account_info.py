"""Describe the account behind a connection: who is signed in, plan, models and usage limits.

Everything comes from what the vendor CLIs already keep on this machine (their status
command, profile/config files and local caches). Only non-secret fields are read out:
tokens are never returned, logged or stored, and nothing is sent over the network.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentdev.connections.catalog import AUTH_API_KEY, AUTH_CLI, AUTH_OAUTH, get_vendor
from agentdev.connections.cli_auth import detect_cli
from agentdev.connections.store import Connection

MAX_SESSION_FILES = 5  # newest Codex session logs scanned for rate limits
MAX_TAIL_BYTES = 4 * 1024 * 1024

_CLAUDE_AUTH_METHODS = {"claude.ai": "Claude AI", "console": "Anthropic Console"}
# Codex reports limit windows by length; map the common ones to named limits.
_WINDOW_KINDS = {300: "session", 10080: "weekly", 43200: "monthly"}


def _empty(auth_method: str) -> Dict[str, Any]:
    return {
        "loggedIn": None,
        "authMethod": auth_method,
        "displayName": None,
        "email": None,
        "organization": None,
        "plan": None,
        "seat": None,
        "models": None,
        "usage": None,
        "detail": "",
    }


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _str(value: Any, limit: int = 200) -> Optional[str]:
    return value.strip()[:limit] if isinstance(value, str) and value.strip() else None


def _iso_from_epoch(seconds: Any) -> Optional[str]:
    try:
        return datetime.fromtimestamp(float(seconds), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _parse_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _window(kind: str, percent: Any, resets_at: Optional[str], minutes: Optional[int] = None) -> Optional[Dict[str, Any]]:
    try:
        value = max(0.0, min(100.0, float(percent)))
    except (TypeError, ValueError):
        return None
    reset = _parse_time(resets_at)
    if reset is not None and reset <= datetime.now(timezone.utc):
        # The window rolled over since the snapshot was taken, so nothing is used yet.
        value, resets_at = 0.0, None
    return {"kind": kind, "percent": round(value), "resetsAt": resets_at, "windowMinutes": minutes}


def _title(value: Optional[str]) -> Optional[str]:
    return value.replace("_", " ").strip().title() if value else None


# -- Claude ---------------------------------------------------------------------------------
def _claude_dirs() -> tuple[Path, Path]:
    """(config file, data dir) the way Claude Code resolves them."""
    custom = os.environ.get("CLAUDE_CONFIG_DIR")
    if custom:
        base = Path(custom).expanduser()
        return base / ".claude.json", base
    home = Path.home()
    return home / ".claude.json", home / ".claude"


def _claude_models(data_dir: Path, org_id: Optional[str]) -> Optional[List[Dict[str, Any]]]:
    """Models this organization can use, from Claude Code's cached model catalog."""
    if not org_id:
        return None
    best: Optional[Dict[str, Any]] = None
    try:
        files = list((data_dir / "cache" / "model-catalog").glob(f"{org_id}-*-cc.json"))
    except OSError:
        return None
    for path in files:
        data = _read_json(path)
        if not isinstance(data, dict) or not isinstance(data.get("catalog"), dict):
            continue
        if best is None or (data.get("fetchedAt") or 0) > (best.get("fetchedAt") or 0):
            best = data
    if best is None:
        return None
    models = (best["catalog"].get("config") or {}).get("models")
    if not isinstance(models, list):
        return None
    result = []
    for model in models:
        if isinstance(model, dict) and _str(model.get("id")):
            result.append(
                {
                    "id": model["id"],
                    "name": _str(model.get("name")) or model["id"],
                    "primary": model.get("section") == "main",
                }
            )
    result.sort(key=lambda m: not m["primary"])  # stable: keeps the catalog's order
    return result or None


def _claude_usage(config: Dict[str, Any], account_uuid: Optional[str]) -> Optional[Dict[str, Any]]:
    cached = config.get("cachedUsageUtilization")
    if not isinstance(cached, dict) or not isinstance(cached.get("utilization"), dict):
        return None
    if account_uuid and cached.get("accountUuid") not in (None, account_uuid):
        return None  # snapshot belongs to an account that is no longer signed in
    util = cached["utilization"]
    windows: List[Dict[str, Any]] = []
    limits = util.get("limits")
    if isinstance(limits, list) and limits:
        for item in limits:
            if isinstance(item, dict) and _str(item.get("kind")):
                win = _window(item["kind"], item.get("percent"), item.get("resets_at"))
                if win:
                    windows.append(win)
    else:
        for key, kind, minutes in (("five_hour", "session", 300), ("seven_day", "weekly_all", 10080)):
            part = util.get(key)
            if isinstance(part, dict):
                win = _window(kind, part.get("utilization"), part.get("resets_at"), minutes)
                if win:
                    windows.append(win)
    if not windows:
        return None
    return {"windows": windows, "fetchedAt": _iso_from_epoch((cached.get("fetchedAtMs") or 0) / 1000 or None)}


def _claude_cli_account(info: Dict[str, Any]) -> None:
    status = detect_cli("anthropic")
    info["loggedIn"] = status.get("logged_in")
    info["detail"] = status.get("detail", "")
    if status.get("logged_in") is not True:
        return
    profile = status.get("profile") or {}
    config_file, data_dir = _claude_dirs()
    config = _read_json(config_file)
    config = config if isinstance(config, dict) else {}
    account = config.get("oauthAccount") if isinstance(config.get("oauthAccount"), dict) else {}
    email = profile.get("email") or _str(account.get("emailAddress"))
    if account and email and _str(account.get("emailAddress")) not in (None, email):
        account = {}  # stale profile cache from another account

    method = profile.get("authMethod")
    info["authMethod"] = _CLAUDE_AUTH_METHODS.get(method or "", method or info["authMethod"])
    info["email"] = email
    info["displayName"] = _str(account.get("displayName")) or _str(account.get("fullName"))
    info["organization"] = profile.get("orgName") or _str(account.get("organizationName"))
    if info["organization"]:
        info["organization"] = " ".join(info["organization"].split())
    plan = profile.get("subscriptionType")
    info["plan"] = f"Claude {_title(plan)}" if plan else None
    seat = _str(account.get("seatTier"))
    if seat and "_" in seat:
        seat = seat.split("_", 1)[1]  # "team_standard" -> "standard"
    info["seat"] = _title(seat)
    info["models"] = _claude_models(data_dir, profile.get("orgId") or _str(account.get("organizationUuid")))
    info["usage"] = _claude_usage(config, _str(account.get("accountUuid")))


# -- Codex ----------------------------------------------------------------------------------
def _codex_home() -> Path:
    custom = os.environ.get("CODEX_HOME")
    return Path(custom).expanduser() if custom else Path.home() / ".codex"


def _jwt_claims(token: Any) -> Dict[str, Any]:
    """Decode a JWT payload without verifying it; only identity claims are read from it."""
    if not isinstance(token, str) or token.count(".") != 2:
        return {}
    part = token.split(".")[1]
    try:
        data = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _codex_identity(home: Path) -> Dict[str, Optional[str]]:
    auth = _read_json(home / "auth.json")
    if not isinstance(auth, dict):
        return {}
    tokens = auth.get("tokens") if isinstance(auth.get("tokens"), dict) else {}
    id_token = tokens.get("id_token")
    if isinstance(id_token, dict):  # some versions store the parsed token
        id_token = id_token.get("raw_jwt")
    claims = _jwt_claims(id_token)
    openai_auth = claims.get("https://api.openai.com/auth")
    openai_auth = openai_auth if isinstance(openai_auth, dict) else {}
    profile = claims.get("https://api.openai.com/profile")
    profile = profile if isinstance(profile, dict) else {}
    org = None
    orgs = openai_auth.get("organizations")
    if isinstance(orgs, list):
        default = next((o for o in orgs if isinstance(o, dict) and o.get("is_default")), None)
        default = default or next((o for o in orgs if isinstance(o, dict)), None)
        org = _str((default or {}).get("title"))
    return {
        "mode": "chatgpt" if tokens else ("api_key" if auth.get("OPENAI_API_KEY") else None),
        "email": _str(claims.get("email")) or _str(profile.get("email")),
        "name": _str(claims.get("name")),
        "plan": _str(openai_auth.get("chatgpt_plan_type")),
        "organization": org,
    }


def _tail_lines(path: Path) -> List[str]:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > MAX_TAIL_BYTES:
                handle.seek(size - MAX_TAIL_BYTES)
            data = handle.read()
    except OSError:
        return []
    return data.decode("utf-8", errors="replace").splitlines()


def _codex_usage(home: Path) -> Optional[Dict[str, Any]]:
    """Latest rate-limit snapshot Codex wrote into its session logs."""
    try:
        files = sorted((home / "sessions").glob("*/*/*/*.jsonl"), reverse=True)[:MAX_SESSION_FILES]
    except OSError:
        return None
    for path in files:
        for line in reversed(_tail_lines(path)):
            if '"rate_limits"' not in line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            payload = event.get("payload") if isinstance(event, dict) else None
            limits = payload.get("rate_limits") if isinstance(payload, dict) else None
            if not isinstance(limits, dict):
                continue
            taken = _parse_time(event.get("timestamp"))
            windows = []
            for key in ("primary", "secondary"):
                part = limits.get(key)
                if not isinstance(part, dict):
                    continue
                minutes = part.get("window_minutes")
                minutes = int(minutes) if isinstance(minutes, (int, float)) else None
                resets = _iso_from_epoch(part.get("resets_at")) if part.get("resets_at") else None
                if resets is None and taken and isinstance(part.get("resets_in_seconds"), (int, float)):
                    resets = _iso_from_epoch(taken.timestamp() + part["resets_in_seconds"])
                win = _window(_WINDOW_KINDS.get(minutes or 0, "window"), part.get("used_percent"), resets, minutes)
                if win:
                    windows.append(win)
            if windows:
                return {
                    "windows": windows,
                    "fetchedAt": taken.isoformat() if taken else None,
                    "plan": _str(limits.get("plan_type")),
                }
    return None


def _codex_models(home: Path) -> Optional[List[Dict[str, Any]]]:
    """Models Codex lists for this account, from its cached model catalog."""
    try:
        data = json.loads((home / "models_cache.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        return None
    visible = [m for m in models if isinstance(m, dict) and _str(m.get("slug")) and m.get("visibility") == "list"]
    visible.sort(key=lambda m: m.get("priority") if isinstance(m.get("priority"), (int, float)) else 1e9)
    result = [
        {"id": m["slug"], "name": _str(m.get("display_name")) or m["slug"], "primary": True} for m in visible
    ]
    return result or None


def _codex_cli_account(info: Dict[str, Any]) -> None:
    status = detect_cli("openai")
    info["loggedIn"] = status.get("logged_in")
    info["detail"] = status.get("detail", "")
    if status.get("logged_in") is not True:
        return
    home = _codex_home()
    identity = _codex_identity(home)
    text = (status.get("status_text") or "").lower()
    mode = identity.get("mode") or ("api_key" if "api key" in text else "chatgpt" if "chatgpt" in text else None)
    if mode == "api_key":
        # Only account sign-in is supported: a Codex logged in with an API key does not count.
        info["loggedIn"] = False
        info["detail"] = "Codex is signed in with an API key; sign in with ChatGPT instead (`codex login`)."
        return
    info["authMethod"] = "ChatGPT"
    info["email"] = identity.get("email")
    info["displayName"] = identity.get("name")
    info["organization"] = identity.get("organization")
    usage = _codex_usage(home)
    plan = identity.get("plan") or (usage or {}).pop("plan", None)
    if usage:
        usage.pop("plan", None)
    info["plan"] = f"ChatGPT {_title(plan)}" if plan else None
    info["usage"] = usage
    info["models"] = _codex_models(home)


# -- entry point ----------------------------------------------------------------------------
def account_info(conn: Connection) -> Dict[str, Any]:
    """Return what is known about the account behind ``conn``. Never raises."""
    vendor = get_vendor(conn.vendor)
    if conn.auth_type == AUTH_API_KEY:
        info = _empty("API key")
        info["loggedIn"] = False
        info["detail"] = "API-key connections are no longer supported: sign out and sign in with an account."
        return info
    if conn.auth_type == AUTH_OAUTH:
        info = _empty("Google OAuth" if conn.vendor == "gemini" else "OAuth")
        try:
            info["email"] = _str(json.loads(conn.secret).get("email"))
        except (ValueError, AttributeError):
            pass
        info["loggedIn"] = bool(conn.secret)
        return info
    info = _empty("CLI")
    if conn.auth_type != AUTH_CLI or vendor is None:
        return info
    try:
        if conn.vendor == "anthropic":
            _claude_cli_account(info)
        elif conn.vendor == "openai":
            _codex_cli_account(info)
    except Exception as exc:  # noqa: BLE001 - account details are best effort
        info["detail"] = f"Could not read account details ({type(exc).__name__})"
    return info
