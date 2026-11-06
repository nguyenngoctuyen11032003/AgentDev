"""Test accounts the user keeps for a product ("Tài khoản dùng thử" in "Sản phẩm").

An app behind a login is only worth trying with an account. The Lab finds the ones the team reported
(``lab_login``); this module keeps the ones the user adds by hand (after creating them in the app, or a known
seed account), so they sit next to the preview every time the product is opened.

Stored outside the product folder (never zipped or shown as a product file):
``storage/product_accounts/<key>.json``, one file per Lab run (``lab_<job>_<run>``) or chat session
(``session_<id>``). Local-only data, like the rest of ``storage/``.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from agentdev import paths

MAX_ACCOUNTS = 20
FIELD_MAX = {"username": 200, "password": 200, "note": 300, "url": 500}
_KEY = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")


class AccountsError(ValueError):
    pass


def _dir() -> Path:
    return Path(paths.WAREHOUSE_DIR).parent / "product_accounts"


def _file(key: str) -> Path:
    if not _KEY.match(key or "") or ".." in key:
        raise AccountsError("Invalid product key")
    return _dir() / f"{key}.json"


def lab_key(job_id: str, run_key: str) -> str:
    return f"lab_{job_id}_{run_key}"


def session_key(session_id: str) -> str:
    return f"session_{session_id}"


def clean(accounts: Any) -> list[dict[str, str]]:
    """Valid accounts only: a list of ``{username, password, note, url}`` strings, at least a username or a
    password each, trimmed and length-capped, at most ``MAX_ACCOUNTS``."""
    if not isinstance(accounts, list):
        raise AccountsError("accounts must be a list")
    if len(accounts) > MAX_ACCOUNTS:
        raise AccountsError(f"At most {MAX_ACCOUNTS} accounts")
    out: list[dict[str, str]] = []
    for item in accounts:
        if not isinstance(item, dict):
            raise AccountsError("Each account must be an object")
        row = {}
        for field, limit in FIELD_MAX.items():
            value = item.get(field, "")
            if value is None:
                value = ""
            if not isinstance(value, str):
                raise AccountsError(f"{field} must be text")
            value = value.strip() if field != "password" else value
            if len(value) > limit:
                raise AccountsError(f"{field} is too long")
            row[field] = value
        if row["url"] and not re.match(r"^https?://", row["url"], re.IGNORECASE):
            raise AccountsError("url must start with http:// or https://")
        if row["username"] or row["password"]:
            out.append(row)
    return out


def load(key: str) -> list[dict[str, str]]:
    path = _file(key)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    try:
        return clean(data.get("accounts", []) if isinstance(data, dict) else [])
    except AccountsError:
        return []


def save(key: str, accounts: Any) -> list[dict[str, str]]:
    """Replace the saved accounts of ``key`` (an empty list deletes the file). Written atomically."""
    rows = clean(accounts)
    path = _file(key)
    if not rows:
        path.unlink(missing_ok=True)
        return []
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"accounts": rows}, handle, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return rows


def delete(key: str) -> None:
    _file(key).unlink(missing_ok=True)
