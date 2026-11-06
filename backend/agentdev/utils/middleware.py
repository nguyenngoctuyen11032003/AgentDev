"""Custom middleware for the AgentDev workflow system."""

import uuid
from typing import Callable
from fastapi import Request, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import re
import os
import logging
from urllib.parse import unquote_plus

from agentdev.connections.security import is_preview_origin
from agentdev.utils.structured_logger import get_server_logger


_SENSITIVE_QUERY = re.compile(r"code|state|token|secret|key|password|authorization", re.I)


def _is_sensitive(name: str) -> bool:
    return bool(_SENSITIVE_QUERY.search(unquote_plus(name)))


def redact_query(params: dict) -> dict:
    """Mask OAuth codes, tokens and secrets before a query is logged."""
    return {k: ("***" if _is_sensitive(k) else v) for k, v in params.items()}


def redact_query_string(query: str) -> str:
    """Mask every value (repeated params too) of sensitive parameters in a raw query string."""
    parts = []
    for piece in query.split("&"):
        name, sep, _ = piece.partition("=")
        parts.append(f"{name}=***" if sep and _is_sensitive(name) else piece)
    return "&".join(parts)


def redact_url(request: Request) -> str:
    url = request.url
    if not url.query:
        return str(url)
    return str(url.replace(query=redact_query_string(url.query)))


class AccessLogRedactFilter(logging.Filter):
    """Mask sensitive query values in uvicorn access log lines."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple):
            record.args = tuple(
                redact_target(a) if isinstance(a, str) and "?" in a and a.startswith("/") else a for a in args
            )
        return True


def redact_target(target: str) -> str:
    path, _, query = target.partition("?")
    return f"{path}?{redact_query_string(query)}"


def install_access_log_filter() -> None:
    lg = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, AccessLogRedactFilter) for f in lg.filters):
        lg.addFilter(AccessLogRedactFilter())


install_access_log_filter()


async def correlation_id_middleware(request: Request, call_next: Callable):
    """Add correlation ID to requests for tracing."""
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    
    start_time = time.time()
    response = await call_next(request)
    duration = time.time() - start_time
    
    # Log the request and response
    logger = get_server_logger()
    logger.log_request(
        request.method,
        redact_url(request),
        correlation_id=correlation_id,
        path=request.url.path,
        query_params=redact_query(dict(request.query_params)),
        client_host=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent")
    )
    
    logger.log_response(
        response.status_code,
        duration,
        correlation_id=correlation_id,
        content_length=response.headers.get("content-length")
    )
    
    # Add correlation ID to response headers
    response.headers["X-Correlation-ID"] = correlation_id
    
    return response


async def security_middleware(request: Request, call_next: Callable):
    """Security middleware to validate requests.

    Rejections are *returned* as responses: an ``HTTPException`` raised inside
    an HTTP middleware bypasses FastAPI's exception handlers and surfaces as 500.
    """
    # Lab/Run previews (model-written pages on loopback preview ports) never reach the API, whatever the method:
    # this runs before CORS, so even a preflight gets no CORS headers.
    if is_preview_origin(request.headers.get("origin")):
        return JSONResponse(status_code=403, content={"detail": "Requests from a preview page are not allowed"})
    # Validate content type for JSON endpoints
    if request.url.path.startswith("/api/") and request.method in ["POST", "PUT", "PATCH"]:
        content_type = request.headers.get("content-type", "").lower()
        if not content_type.startswith("application/json") and request.method != "GET":
            # Skip validation for file uploads
            if not content_type.startswith("multipart/form-data"):
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Content-Type must be application/json for API endpoints"},
                )
    
    # Validate file paths to prevent path traversal
    # Check URL path for suspicious patterns
    path = request.url.path
    if ".." in path or "./" in path:
        # Use a more thorough check
        if re.search(r"(\.{2}[/\\])|([/\\]\.{2})", path):
            logger = get_server_logger()
            logger.log_security_event(
                "PATH_TRAVERSAL_ATTEMPT",
                f"Suspicious path detected: {path}",
                correlation_id=getattr(request.state, 'correlation_id', str(uuid.uuid4()))
            )
            return JSONResponse(status_code=400, content={"detail": "Invalid path"})
    
    response = await call_next(request)
    return response


async def rate_limit_middleware(request: Request, call_next: Callable):
    """Rate limiting middleware (basic implementation)."""
    # This is a simple rate limiting implementation
    # In production, you would use Redis or other storage for tracking
    # This is just a placeholder for now
    response = await call_next(request)
    return response


class _NoPreviewCORSMiddleware(CORSMiddleware):
    """CORS that never allows a Lab/Run preview origin, even though it matches the loopback regex."""

    def is_allowed_origin(self, origin: str) -> bool:
        return not is_preview_origin(origin) and super().is_allowed_origin(origin)


def add_cors_middleware(app: FastAPI) -> None:
    """Configure and attach CORS middleware."""
    # Dev defaults; override via CORS_ALLOW_ORIGINS (comma-separated)
    default_origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    env_origins = os.getenv("CORS_ALLOW_ORIGINS")
    if env_origins:
        origins = [o.strip() for o in env_origins.split(",") if o.strip()]
        origin_regex = None
    else:
        origins = default_origins
        # Helpful in dev: allow localhost/127.0.0.1 on any port (except preview ports, see _NoPreviewCORSMiddleware)
        origin_regex = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    app.add_middleware(
        _NoPreviewCORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID"],
        max_age=600,
    )


def add_middleware(app: FastAPI):
    """Add all middleware to the FastAPI application."""
    install_access_log_filter()
    # Attach CORS first to handle preflight requests and allow origins.
    add_cors_middleware(app)

    # Add other middleware
    app.middleware("http")(correlation_id_middleware)
    app.middleware("http")(security_middleware)
    # app.middleware("http")(rate_limit_middleware)  # Enable if needed
    
    return app
