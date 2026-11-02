"""Persist OAuth-based connections using ConnectionStore internals."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict

from agentdev.connections.catalog import AUTH_OAUTH
from agentdev.connections.store import Connection, ConnectionInputError, _slug, get_store


def save_oauth_connection(label: str, vendor: str, tokens_dict: Dict[str, Any]) -> Connection:
    """Create a connection with auth_type "oauth"; tokens JSON-encoded in ``secret``."""
    label = (label or "").strip()
    if not label:
        raise ConnectionInputError("label is required")
    store = get_store()
    with store._lock:
        connections = store._load(strict=True)
        base = _slug(label)
        conn_id = base
        while conn_id in connections:
            conn_id = f"{base}-{uuid.uuid4().hex[:4]}"
        conn = Connection(
            id=conn_id,
            vendor=vendor,
            label=label,
            auth_type=AUTH_OAUTH,
            secret=json.dumps(tokens_dict, ensure_ascii=False),
        )
        connections[conn.id] = conn
        store._save(connections)
        return conn


def update_oauth_tokens(connection_id: str, tokens_dict: Dict[str, Any]) -> bool:
    """Persist refreshed tokens for an existing oauth connection."""
    store = get_store()
    with store._lock:
        connections = store._load(strict=True)
        conn = connections.get(connection_id)
        if conn is None or conn.auth_type != AUTH_OAUTH:
            return False
        conn.secret = json.dumps(tokens_dict, ensure_ascii=False)
        store._save(connections)
        return True
