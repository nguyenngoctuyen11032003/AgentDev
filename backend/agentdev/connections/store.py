"""Persistent store for provider connections (``storage/connections.json``).

Secrets live only in this file (storage/ is gitignored) and are never returned
by the API: callers get a masked hint instead. Workflow YAML references a
connection by id and never contains the secret.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentdev.connections.catalog import AUTH_API_KEY
from agentdev.connections.secret_box import SecretDecryptError, decrypt, encrypt
from agentdev.paths import STORAGE_DIR

CONNECTIONS_FILE = STORAGE_DIR / "connections.json"
_ID_RE = re.compile(r"[^a-z0-9]+")


class ConnectionInputError(ValueError):
    """Raised for invalid connection input."""


@dataclass
class Connection:
    id: str
    vendor: str
    label: str
    auth_type: str = AUTH_API_KEY
    secret: str = ""  # api key, or ${ENV_VAR} reference
    base_url: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    # Stored blob kept only when it could not be decrypted, so later writes never wipe it.
    raw_secret: str = ""

    def to_storage(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "vendor": self.vendor,
            "label": self.label,
            "auth_type": self.auth_type,
            "secret": self.raw_secret if (self.raw_secret and not self.secret) else encrypt(self.secret),
            "base_url": self.base_url,
            "created_at": self.created_at,
        }

    def _public_hint(self) -> str:
        if self.auth_type == "oauth":
            try:
                return json.loads(self.secret).get("email") or "OAuth"
            except (ValueError, AttributeError):
                return "OAuth"
        if self.auth_type == "cli":
            return ""
        return mask_secret(self.secret)

    def to_public(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "vendor": self.vendor,
            "label": self.label,
            "authType": self.auth_type,
            "secretHint": self._public_hint(),
            "baseUrl": self.base_url,
            "createdAt": self.created_at,
        }


def mask_secret(secret: str) -> str:
    secret = (secret or "").strip()
    if not secret:
        return ""
    if secret.startswith("${") and secret.endswith("}"):
        return secret  # env reference, not a secret itself
    if len(secret) < 20:
        return "****"
    return f"{secret[:4]}****{secret[-4:]}"


def _safe_decrypt(stored: str) -> str:
    """Decrypt a stored secret; an undecryptable one (e.g. other OS user) reads as empty."""
    try:
        return decrypt(stored or "")
    except SecretDecryptError:
        return ""


def _is_undecryptable(stored: str) -> bool:
    try:
        decrypt(stored or "")
    except SecretDecryptError:
        return True
    return False


def _slug(text: str) -> str:
    return _ID_RE.sub("-", text.lower()).strip("-") or "connection"


class ConnectionStore:
    def __init__(self, path: Path | None = None):
        self._path = Path(path) if path else CONNECTIONS_FILE
        self._lock = threading.RLock()

    # -- persistence -------------------------------------------------------
    def _load(self, strict: bool = False) -> Dict[str, Connection]:
        """Read the file. ``strict`` (used before writes) refuses to continue on a corrupt file
        so a failed read can never be turned into an overwrite that drops every connection."""
        try:
            text = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError as exc:
            if strict:
                raise ConnectionInputError("Could not read the connections file") from exc
            return {}
        try:
            raw = json.loads(text)
        except ValueError as exc:
            if not strict:
                return {}
            backup = self._path.with_name(self._path.name + ".bak")
            try:
                shutil.copy2(self._path, backup)
            except OSError:
                pass
            raise ConnectionInputError(
                f"connections file is corrupt (copy kept as {backup.name}); fix or delete it"
            ) from exc
        items = raw.get("connections", []) if isinstance(raw, dict) else []
        result: Dict[str, Connection] = {}
        for item in items:
            try:
                conn = Connection(
                    id=item["id"],
                    vendor=item["vendor"],
                    label=item.get("label") or item["id"],
                    auth_type=item.get("auth_type", AUTH_API_KEY),
                    secret=_safe_decrypt(item.get("secret", "")),
                    raw_secret=item.get("secret", "") if _is_undecryptable(item.get("secret", "")) else "",
                    base_url=item.get("base_url", ""),
                    created_at=item.get("created_at") or datetime.now(timezone.utc).isoformat(),
                )
            except (KeyError, TypeError):
                continue
            result[conn.id] = conn
        return result

    def _save(self, connections: Dict[str, Connection]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            {"version": 1, "connections": [c.to_storage() for c in connections.values()]},
            ensure_ascii=False,
            indent=2,
        )
        fd, tmp = tempfile.mkstemp(dir=str(self._path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            os.replace(tmp, self._path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    # -- public API --------------------------------------------------------
    def list(self) -> List[Connection]:
        with self._lock:
            return list(self._load().values())

    def get(self, connection_id: str) -> Optional[Connection]:
        with self._lock:
            return self._load().get(connection_id)

    def create(
        self,
        *,
        vendor: str,
        label: str,
        secret: str,
        base_url: str = "",
        auth_type: str = AUTH_API_KEY,
    ) -> Connection:
        label = (label or "").strip()
        if not label:
            raise ConnectionInputError("label is required")
        if not (secret or "").strip() and auth_type == AUTH_API_KEY:
            raise ConnectionInputError("credential is required")
        with self._lock:
            connections = self._load(strict=True)
            base = _slug(label)
            conn_id = base
            while conn_id in connections:
                conn_id = f"{base}-{uuid.uuid4().hex[:4]}"
            conn = Connection(
                id=conn_id,
                vendor=vendor,
                label=label,
                auth_type=auth_type,
                secret=(secret or "").strip(),
                base_url=(base_url or "").strip(),
            )
            connections[conn.id] = conn
            self._save(connections)
            return conn

    def delete(self, connection_id: str) -> bool:
        with self._lock:
            connections = self._load(strict=True)
            if connection_id not in connections:
                return False
            del connections[connection_id]
            self._save(connections)
            return True


_store: ConnectionStore | None = None


_store_lock = threading.Lock()


def get_store() -> ConnectionStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = ConnectionStore()
    return _store
