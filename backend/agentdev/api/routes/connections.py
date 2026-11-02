"""Provider connection management endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from agentdev.connections import ConnectionResolutionError, get_store, resolve_connection
from agentdev.connections.catalog import AUTH_API_KEY, get_vendor, list_vendors
from agentdev.connections.cli_auth import detect_cli
from agentdev.connections.cli_login import CliLoginError, get_login_manager
from agentdev.connections.resolver import _ENV_REF
from agentdev.connections.security import (
    UnsafeConnectionInput,
    check_env_ref_destination,
    is_allowed_env_name,
    require_local_origin,
    validate_base_url,
)
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
    auth_type: str = AUTH_API_KEY
    api_key: str = Field("", description="API key or a ${ENV_VAR} reference (not used for CLI sign-in)")
    base_url: str = ""


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


class CliLoginCode(BaseModel):
    code: str = Field(..., min_length=1, max_length=600)


@router.post("/cli-login/start")
def cli_login_start(body: CliLoginStart):
    """Spawn the vendor CLI's sign-in and return the link the user must open."""
    try:
        return get_login_manager().start(body.vendor)
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
    return {"connections": [conn.to_public() for conn in get_store().list()]}


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
        base_url = validate_base_url(body.base_url)
        env_match = _ENV_REF.match(body.api_key.strip())
        if env_match:
            if not is_allowed_env_name(env_match.group(1)):
                raise UnsafeConnectionInput(
                    f"Environment variable '{env_match.group(1)}' cannot be used as a credential "
                    "(allowed: names ending in _API_KEY, _AUTH_TOKEN or _ACCESS_TOKEN)"
                )
            check_env_ref_destination(base_url, vendor.default_base_url)
    except UnsafeConnectionInput as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        conn = get_store().create(
            vendor=vendor.id,
            label=body.label,
            secret=body.api_key,
            base_url=base_url,
            auth_type=body.auth_type,
        )
    except ConnectionInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return conn.to_public()


@router.delete("/{connection_id}")
def delete_connection(connection_id: str):
    if not get_store().delete(connection_id):
        raise HTTPException(status_code=404, detail="Connection not found")
    return {"deleted": connection_id}


@router.post("/{connection_id}/test")
def test_connection(connection_id: str):
    """Verify the credential by listing models; falls back to the catalog list."""
    conn = get_store().get(connection_id)
    if conn is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    vendor = get_vendor(conn.vendor)
    fallback: List[str] = list(vendor.models) if vendor else []
    if conn.auth_type == "cli":
        status = detect_cli(conn.vendor)
        ok = bool(status.get("installed")) and status.get("logged_in") is not False
        return {"ok": ok, "error": None if ok else status.get("detail", ""), "models": fallback, "cli": status}
    try:
        creds = resolve_connection(connection_id)
    except ConnectionResolutionError as exc:
        return {"ok": False, "error": str(exc), "models": fallback}
    if conn.auth_type == "oauth":
        # Token was just validated/refreshed by the resolver; model listing needs an API key.
        return {"ok": True, "models": fallback}

    base_url = creds.base_url or (vendor.default_base_url if vendor else "")
    try:
        models = _list_remote_models(conn.vendor, creds.api_key, base_url)
    except Exception as exc:  # noqa: BLE001 - surfaced to the user as a test failure
        # Never echo the SDK message: it can contain response bodies or parts of the key.
        status = getattr(exc, "status_code", None)
        detail = f"{type(exc).__name__}" + (f" (HTTP {status})" if status else "")
        return {"ok": False, "error": detail, "models": fallback}
    return {"ok": True, "models": models or fallback}


def _list_remote_models(vendor: str, api_key: str, base_url: str) -> List[str]:
    if vendor == "anthropic":
        import anthropic

        client = anthropic.Anthropic(api_key=api_key, base_url=base_url or None, timeout=15)
        return [m.id for m in client.models.list(limit=100)]
    if vendor == "openai":
        from openai import OpenAI

        client = OpenAI(api_key=api_key, base_url=base_url or None, timeout=15)
        return sorted(m.id for m in client.models.list())
    if vendor == "gemini":
        from google import genai

        client = genai.Client(api_key=api_key)
        names = []
        for model in client.models.list():
            name = getattr(model, "name", "") or ""
            names.append(name.split("/", 1)[-1])
        return names
    raise ValueError(f"Unsupported vendor '{vendor}'")
