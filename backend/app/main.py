"""App factory. Routers live in their own modules; this file only wires them."""

import logging

from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.auth import require_team
from app.config import check_production, get_settings
from app.db import get_engine
from app.paths import STATIC_DIR


def create_app() -> FastAPI:
    settings = get_settings()
    check_production(settings)
    logging.basicConfig(
        level=settings.LOG_LEVEL.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = FastAPI(title="Scrum agent", docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

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

    @app.get("/")
    def index(_dep: None = Depends(require_team)) -> str:
        return "Scrum agent"

    return app


app = create_app()
