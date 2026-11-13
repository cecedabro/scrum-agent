"""Web routes and Jinja2 template setup (SPEC --).

The Jinja environment is configured here with the ``templates/``
directory and the Dutch date filters from ``app.fmt`` registered as
template globals.
"""

from __future__ import annotations

from pathlib import Path as _Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.auth import require_team
from app.config import TIMEZONE
from app.fmt import datum, datum_kort, relatief

# Jinja2 environment
_templates_dir = _Path(__file__).resolve().parent / "templates"
_jinja_env = Environment(
    loader=FileSystemLoader(str(_templates_dir)),
    autoescape=select_autoescape(),
)

# Register Dutch date format filters as globals
_jinja_env.globals["datum"] = datum
_jinja_env.globals["datum_kort"] = datum_kort
_jinja_env.globals["relatief"] = relatief
_jinja_env.globals["TIMEZONE"] = TIMEZONE

# FastAPI-compatible templates helper
templates = Jinja2Templates(env=_jinja_env)

router = APIRouter()


@router.get("/")
async def index(request: Request, _auth: None = Depends(require_team)) -> Response:
    """Overview (Overzicht) page — empty state when no deadlines exist."""
    return templates.TemplateResponse(
        request,
        "base.html",
        {
            "page_title": "Overzicht",
            "deadlines": [],
            "meeting_jobs": [],
            "model_reachable": False,
        },
    )
