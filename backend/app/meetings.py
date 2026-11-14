"""Meeting upload form and job listing (SPEC 7)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.auth import require_team
from app.clock import today_local
from app.config import get_settings
from app.db import get_db
from app.fmt import datum_kort
from app.models import Job
from app.transcripts import TranscriptError, as_text, parse_docx, parse_vtt

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
            "errors": {},
            "title": "",
        },
    )


@router.post("/meetings")
async def meetings_upload(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(default=""),
    meeting_date: str = Form(default=""),
    _auth: None = Depends(require_team),
) -> Response:
    """Upload a meeting transcript (SPEC 7.1)."""
    # --- extension check (case-insensitive) ---
    filename = file.filename or ""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ("vtt", "docx"):
        return _meeting_templates.TemplateResponse(
            request,
            "meetings.html",
            {
                "page_title": "Vergaderingen",
                "meeting_jobs": [],
                "model_reachable": False,
                "default_date": today_local().isoformat(),
                "errors": {"file": "Alleen .vtt en .docx bestanden worden geaccepteerd"},
                "title": title,
            },
            status_code=422,
        )

    # --- size guard: read at most MAX_UPLOAD_BYTES + 1 ---
    settings = get_settings()
    max_bytes = settings.MAX_UPLOAD_BYTES + 1
    data = await file.read(max_bytes)
    if len(data) > settings.MAX_UPLOAD_BYTES:
        return _meeting_templates.TemplateResponse(
            request,
            "meetings.html",
            {
                "page_title": "Vergaderingen",
                "meeting_jobs": [],
                "model_reachable": False,
                "default_date": today_local().isoformat(),
                "errors": {"file": "Het bestand is te groot"},
                "title": title,
            },
            status_code=422,
        )

    # --- parse transcript ---
    try:
        if ext == "vtt":
            content = data.decode("utf-8")
            turns = parse_vtt(content)
        else:
            turns = parse_docx(data)
    except (TranscriptError, UnicodeDecodeError):
        return _meeting_templates.TemplateResponse(
            request,
            "meetings.html",
            {
                "page_title": "Vergaderingen",
                "meeting_jobs": [],
                "model_reachable": False,
                "default_date": today_local().isoformat(),
                "errors": {"file": "Het transcriptbestand kan niet worden gelezen"},
                "title": title,
            },
            status_code=422,
        )

    # --- title + date defaults ---
    if not title.strip():
        d = today_local()
        title = "Vergadering " + datum_kort(d)
    else:
        title = title.strip()

    if meeting_date:
        try:
            parsed_date = date.fromisoformat(meeting_date)
        except ValueError:
            return _meeting_templates.TemplateResponse(
                request,
                "meetings.html",
                {
                    "page_title": "Vergaderingen",
                    "meeting_jobs": [],
                    "model_reachable": False,
                    "default_date": today_local().isoformat(),
                    "errors": {"meeting_date": "Ongeldige datum (YYYY-MM-DD)"},
                    "title": title,
                },
                status_code=422,
            )
    else:
        parsed_date = today_local()

    # --- store job ---
    with next(get_db()) as session:
        job = Job(
            kind="summary",
            status="queued",
            title=title,
            meeting_date=parsed_date,
            transcript=as_text(turns),
        )
        session.add(job)
        session.commit()

    return RedirectResponse(url="/meetings", status_code=303)
