"""Google OAuth routes for connections (sign in with Google for Gemini)."""

from __future__ import annotations

import html
import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from agentdev.connections.security import require_local_origin

from agentdev.connections import google_oauth
from agentdev.connections.oauth_store import save_oauth_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/connections/oauth/google", tags=["connections-oauth"])

VENDOR = "gemini"


class StartBody(BaseModel):
    label: str = Field(..., min_length=1, max_length=80)


def _page(ok: bool) -> HTMLResponse:
    message = "Signed in. You can close this window." if ok else "Sign-in failed. Please try again."
    payload = json.dumps({"type": "agentdev-oauth", "ok": ok}).replace("<", "\\u003c")
    body = (
        '<!doctype html><html><head><meta charset="utf-8"><title>Google sign-in</title></head><body>'
        f"<p>{html.escape(message)}</p>"
        f"<script>try{{if(window.opener)window.opener.postMessage({payload},'*');}}"
        "catch(e){}window.close();</script></body></html>"
    )
    return HTMLResponse(body, headers={"Cache-Control": "no-store"})


@router.get("/status")
def status():
    return {"configured": google_oauth.is_configured()}


@router.post("/start", dependencies=[Depends(require_local_origin)])
def start(body: StartBody):
    if not body.label.strip():
        raise HTTPException(status_code=400, detail="label is required")
    try:
        result = google_oauth.start_login(body.label)
    except google_oauth.OAuthError:
        raise HTTPException(status_code=400, detail="Google OAuth is not configured")
    return {"authUrl": result["auth_url"], "state": result["state"]}


@router.get("/callback")
def callback(code: str = "", state: str = "", error: str = ""):
    if error or not code or not state:
        if state:
            google_oauth.record_result(state, False)
        return _page(False)
    label = google_oauth.peek_pending_label(state)
    try:
        tokens = google_oauth.complete_login(state, code)
        save_oauth_connection(label or tokens.email or "Google", google_oauth_vendor(), tokens.to_dict())
    except Exception:
        logger.warning("Google OAuth callback failed")
        google_oauth.record_result(state, False)
        return _page(False)
    google_oauth.record_result(state, True)
    return _page(True)


def google_oauth_vendor() -> str:
    return VENDOR


@router.get("/poll")
def poll(state: str = ""):
    return {"status": google_oauth.poll(state)}
