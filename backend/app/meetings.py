"""Meeting upload form and job listing (SPEC 7)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.auth import require_team
from app.clock import today_local
from app.db import get_db
from app.models import Job

router = APIRouter()

_templates_dir = Path(__file__).resolve().parent / "templates"
_meeting_env = Environment(
    loader=FileSystemLoader(str(_templates_dir)),
    autoescape=select_autoescape(),
)
_meeting_templates = Jinja2Templates(env=_meeting_env)


@router.get("/meetings")
async def meetings_page(
    request: Request,
    _auth: None = Depends(require_team),
) -> Response:
    """Show the meetings upload form (SPEC 7.1)."""
    with next(get_db()) as session:
        jobs = session.query(Job).order_by(Job.id.desc()).all()

    today = today_local()

    return _meeting_templates.TemplateResponse(
        request,
        "meetings.html",
        {
            "page_title": "Vergaderingen",
            "meeting_jobs": jobs,
            "model_reachable": False,
            "default_date": today.isoformat(),
        },
    )
