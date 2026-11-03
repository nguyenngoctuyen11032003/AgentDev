"""Provider connection management endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from agentdev.connections import ConnectionResolutionError, get_store, resolve_connection
from agentdev.connections.account_info import account_info
from agentdev.connections.catalog import AUTH_CLI, get_vendor, list_vendors
from agentdev.connections.cli_auth import detect_cli, logout_cli
from agentdev.connections.cli_login import CliLoginError, get_login_manager
from agentdev.connections.security import require_local_origin
from agentdev.connections.store import ConnectionInputError

def _block_cross_origin_writes(request: Request) -> None:
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        require_local_origin(request)


router = APIRouter(
    prefix="/api/connections", tags=["connections"], dependencies=[Depends(_block_cross_origin_writes)]
)


class ConnectionCreate(BaseModel):
    vendor: str
    label: str = Field(..., min_length=1, max_length=80)
    auth_type: str = AUTH_CLI  # account sign-in only: "cli" (Claude / Codex); Google uses the OAuth flow


@router.get("/vendors")
def list_vendor_catalog():
    return {"vendors": [vendor.to_json() for vendor in list_vendors()]}


@router.get("/cli-status/{vendor}")
def cli_status(vendor: str):
    """Report whether the vendor's local CLI is installed and signed in."""
    info = get_vendor(vendor)
    if info is None or not info.cli_provider:
        raise HTTPException(status_code=404, detail="CLI sign-in not available for this vendor")
    return detect_cli(vendor)


class CliLoginStart(BaseModel):
    vendor: str
    method: Optional[str] = Field(default=None, max_length=32)


class CliLoginCode(BaseModel):
    code: str = Field(..., min_length=1, max_length=600)


@router.post("/cli-login/start")
def cli_login_start(body: CliLoginStart):
    """Spawn the vendor CLI's sign-in and return the link the user must open."""
    try:
        return get_login_manager().start(body.vendor, body.method)
    except CliLoginError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/cli-login/{session_id}")
def cli_login_status(session_id: str):
    try:
        return get_login_manager().status(session_id)
    except CliLoginError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/cli-login/{session_id}/code")
def cli_login_code(session_id: str, body: CliLoginCode):
    """Paste the code from the browser back, like typing it into `claude auth login`."""
    try:
        return get_login_manager().submit_code(session_id, body.code)
    except CliLoginError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/cli-login/{session_id}")
def cli_login_cancel(session_id: str):
    return {"cancelled": get_login_manager().cancel(session_id)}


@router.get("")
def list_connections():
    store = get_store()
    default = store.default_connection()
    return {
        "connections": [conn.to_public() for conn in store.list()],
        "defaultConnection": default.id if default else None,
    }


class DefaultConnection(BaseModel):
    connection_id: str = Field(..., min_length=1, max_length=120)


@router.put("/default")
def set_default_connection(body: DefaultConnection):
    """Pick the connection every agent node without its own connection runs on."""
    try:
        conn = get_store().set_default(body.connection_id)
    except ConnectionInputError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"defaultConnection": conn.id}


@router.post("", status_code=201)
def create_connection(body: ConnectionCreate):
    vendor = get_vendor(body.vendor)
    if vendor is None:
        raise HTTPException(status_code=422, detail=f"Unknown vendor '{body.vendor}'")
    if body.auth_type not in vendor.auth_methods:
        raise HTTPException(
            status_code=422,
            detail=f"Auth type '{body.auth_type}' is not available for {vendor.label}",
        )
    if body.auth_type == "oauth":
        raise HTTPException(status_code=422, detail="OAuth connections are created via the sign-in flow")
    if body.auth_type == "cli":
        # A CLI connection is only worth creating when the account really is signed in.
        status = detect_cli(vendor.id)
        if not status.get("installed"):
            raise HTTPException(status_code=422, detail="The CLI for this provider is not installed")
        if status.get("logged_in") is not True:
            raise HTTPException(status_code=422, detail="Not signed in: sign in to your account first")
    try:
        conn = get_store().create(vendor=vendor.id, label=body.label, auth_type=body.auth_type)
    except ConnectionInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return conn.to_public()


@router.delete("/{connection_id}")
def delete_connection(connection_id: str):
    store = get_store()
    conn = store.get(connection_id)
    if conn is None or not store.delete(connection_id):
        raise HTTPException(status_code=404, detail="Connection not found")
    cli_logged_out = False
    if conn.auth_type == "cli":
        # Signing out also signs the CLI out, so reconnecting asks for the account again.
        # Other CLI connections of the same vendor share that login, so keep it while any remain.
        still_used = any(c.auth_type == "cli" and c.vendor == conn.vendor for c in store.list())
        if not still_used:
            cli_logged_out = logout_cli(conn.vendor)
    return {"deleted": connection_id, "cliLoggedOut": cli_logged_out}


@router.get("/{connection_id}/account")
def connection_account(connection_id: str):
    """Who is signed in behind this connection: identity, plan, models and usage limits."""
    conn = get_store().get(connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    return account_info(conn)


@router.get("/{connection_id}/models")
def connection_models_route(connection_id: str):
    """Models the account behind this connection can use (for the model pickers)."""
    from agentdev.connections.model_catalog import connection_models

    conn = get_store().get(connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    return connection_models(conn)


@router.post("/{connection_id}/test")
def test_connection(connection_id: str):
    """Verify the credential by listing models; falls back to the catalog list."""
    conn = get_store().get(connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    vendor = get_vendor(conn.vendor)
    fallback: List[str] = list(vendor.models) if vendor else []
    if conn.auth_type == "cli":
        account = account_info(conn)
        ok = account.get("loggedIn") is True
        models = [m["id"] for m in account.get("models") or []] or fallback
        return {"ok": ok, "error": None if ok else account.get("detail", ""), "models": models, "account": account}
    # Google sign-in: resolving refreshes the token, then Gemini lists the account's models.
    try:
        resolve_connection(connection_id)
    except ConnectionResolutionError as exc:
        return {"ok": False, "error": str(exc), "models": fallback}
    from agentdev.connections.model_catalog import connection_models

    result = connection_models(conn)
    return {"ok": result["ok"], "error": result["error"], "models": [m["id"] for m in result["models"]] or fallback}
