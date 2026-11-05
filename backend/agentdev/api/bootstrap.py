"""Application bootstrap helpers for the FastAPI server."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from agentdev.api import state
from agentdev.connections.security import host_headers_ok
from agentdev.api.config_schema_router import router as config_schema_router
from agentdev.api.routes import ALL_ROUTERS
from agentdev.utils.error_handler import add_exception_handlers
from agentdev.utils.middleware import add_middleware


class HostGuardMiddleware:
    """Pure ASGI guard (HTTP and WebSocket): only loopback / AGENTDEV_ALLOWED_HOSTS Host values pass."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] in ("http", "websocket"):
            hosts = [v.decode("latin-1") for k, v in scope.get("headers", []) if k == b"host"]
            if not host_headers_ok(hosts):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await JSONResponse({"detail": "Invalid Host header"}, status_code=400)(scope, receive, send)
                return
        await self.app(scope, receive, send)


def init_app(app: FastAPI) -> None:
    """Apply shared middleware, routers, and global state to ``app``."""

    add_exception_handlers(app)
    add_middleware(app)
    # Outermost: reject foreign Host headers (DNS rebinding) before anything else runs.
    app.add_middleware(HostGuardMiddleware)

    state.init_state()

    for router in ALL_ROUTERS:
        app.include_router(router)

    app.include_router(config_schema_router)

    _stop_previews_on_shutdown(app)


def _stop_previews_on_shutdown(app: FastAPI) -> None:
    """Wrap the app lifespan so Lab app previews (whole process trees) die with the server."""
    inner = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(asgi_app):
        try:
            async with inner(asgi_app) as maybe_state:
                yield maybe_state
        finally:
            from agentdev.api.services.app_preview import shutdown_previews

            shutdown_previews()

    app.router.lifespan_context = lifespan
