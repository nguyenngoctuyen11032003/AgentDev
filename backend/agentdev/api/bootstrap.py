"""Application bootstrap helpers for the FastAPI server."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentdev.api import state
from agentdev.api.config_schema_router import router as config_schema_router
from agentdev.api.routes import ALL_ROUTERS
from agentdev.utils.error_handler import add_exception_handlers
from agentdev.utils.middleware import add_middleware


def init_app(app: FastAPI) -> None:
    """Apply shared middleware, routers, and global state to ``app``."""

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    add_exception_handlers(app)
    add_middleware(app)

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
