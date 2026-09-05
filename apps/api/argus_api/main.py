"""FastAPI application.

Composition root: settings, middleware, routers and error handling. Nothing
domain-specific lives here.

The security posture is appropriate for a prototype and honest about it. CORS is
restricted by configuration, security headers are set, request bodies are
bounded, and unexpected exceptions return an opaque message while the detail
goes to the log. Authentication is deliberately absent - see
docs/architecture/security.md for exactly what would need to change before this
ran anywhere real.

Rate limiting is applied to the endpoints that trigger inference, because those
cost money and an unbounded caller turns cost into an attack surface. Read
endpoints serve stored rows and are deliberately not throttled.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from argus_api.core.settings import get_settings
from argus_api.db.session import init_db
from argus_api.routers import cases, evaluation, insights, platform, review
from argus_api.services.runtime import runtime_status

logger = logging.getLogger("argus")

# Headers appropriate for a JSON API that serves no HTML of its own.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Create the schema on startup and report the resolved configuration."""
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
    )
    init_db()

    status_info = runtime_status(settings)
    logger.info("ARGUS API starting in %s mode", status_info["mode"])
    logger.info("  %s", status_info["headline"])
    logger.info("  embeddings: %s", status_info["embedding"]["description"])
    logger.info("  database: %s", status_info["database"])
    yield
    logger.info("ARGUS API stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="ARGUS API",
        version="0.1.0",
        summary="Agentic Risk Governance & Understanding System",
        description=(
            "Decision-support API for counterparty risk review. AI investigates "
            "and recommends; a named human decides. All demonstration data is "
            "synthetic."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        max_age=600,
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Any]]
    ) -> Any:
        """Attach a request id, enforce a body cap, and time the request."""
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]

        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > settings.max_upload_bytes:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={
                    "detail": (f"Request body exceeds the {settings.max_upload_bytes} byte limit."),
                    "request_id": request_id,
                },
            )

        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - started) * 1000)

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = str(duration_ms)
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)

        if duration_ms > 5000:
            logger.info(
                "slow request %s %s took %dms",
                request.method,
                request.url.path,
                duration_ms,
            )
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        """Log the detail, return an opaque message.

        Stack traces and internal messages are not returned to clients; the
        request id is, so a report can be traced to a log line.
        """
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        logger.exception("unhandled error [%s] on %s", request_id, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": "An internal error occurred. Please retry.",
                "request_id": request_id,
            },
        )

    app.include_router(cases.router)
    app.include_router(review.router)
    app.include_router(insights.router)
    app.include_router(evaluation.router)
    app.include_router(platform.router)

    @app.get("/health", tags=["platform"])
    def health() -> dict[str, Any]:
        """Liveness plus the resolved runtime, for container health checks."""
        info = runtime_status()
        return {
            "status": "ok",
            "mode": info["mode"],
            "model": info.get("model"),
            "database": info["database"],
        }

    return app


app = create_app()
