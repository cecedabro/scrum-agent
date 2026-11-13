"""App factory. Routers live in their own modules; this file only wires them."""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.config import check_production, get_settings
from app.db import get_engine
from app.paths import STATIC_DIR
from app.web import router as web_router

# Security headers (SPEC 2.4)
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'",
}

# Unsafe HTTP methods guarded by CSRF check (SPEC 2.3)
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def create_app() -> FastAPI:
    settings = get_settings()
    check_production(settings)
    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = FastAPI(title="Scrum agent", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def csrf_guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """SPEC 2.3: reject cross-site unsafe requests with 403."""
        if request.method in _UNSAFE_METHODS:
            sec_fetch = request.headers.get("sec-fetch-site", "")
            if sec_fetch == "cross-site":
                resp = JSONResponse(
                    status_code=403,
                    content={"detail": "Cross-site requests not allowed"},
                )
                for header, value in _SECURITY_HEADERS.items():
                    resp.headers[header] = value
                return resp
            origin = request.headers.get("origin")
            host = request.headers.get("host", "")
            if origin and _origin_host(origin) != _host_name(host):
                resp = JSONResponse(
                    status_code=403,
                    content={"detail": "Cross-site requests not allowed"},
                )
                for header, value in _SECURITY_HEADERS.items():
                    resp.headers[header] = value
                return resp
        response = await call_next(request)
        return response

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """SPEC 2.4: security headers on every response."""
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers[header] = value
        return response

    app.include_router(web_router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", response_model=None)
    def readyz() -> dict[str, str] | JSONResponse:
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            return JSONResponse(status_code=503, content={"status": "unavailable"})
        return {"status": "ready"}

    return app


def _origin_host(origin: str) -> str:
    """Extract the authority (host[:port]) from an Origin URL."""
    # Origin is always a full URL like https://example.com
    match = re.match(r"[^:]+://([^/:]+)", origin)
    if match:
        return match.group(1)
    return origin


def _host_name(host: str) -> str:
    """Strip the port from a Host header value."""
    return re.sub(r":\d+$", "", host)


app = create_app()
