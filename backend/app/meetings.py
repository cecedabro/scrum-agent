"""Meeting upload form and job listing (SPEC 7)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[import-not-found,no-redef]

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.auth import require_team
from app.clock import today_local
from app.config import TIMEZONE, get_settings
from app.db import get_db
from app.fmt import datum_kort
from app.models import AppState, Job
from app.transcripts import TranscriptError, as_text, parse_docx, parse_vtt

STATUS_LABELS = {
    "queued": "in de wachtrij",
    "running": "bezig",
    "done": "klaar",
    "failed": "mislukt",
}

router = APIRouter()

_templates_dir = Path(__file__).resolve().parent / "templates"
_meeting_env = Environment(
    loader=FileSystemLoader(str(_templates_dir)),
    autoescape=select_autoescape(),
)
_meeting_env.globals["TIMEZONE"] = TIMEZONE
_meeting_env.filters["datum_kort"] = datum_kort
_meeting_templates = Jinja2Templates(env=_meeting_env)


def _build_context(jobs: list[Job], model_state: str, has_pending: bool) -> dict[str, Any]:
    return {
        "jobs": jobs,
        "STATUS_LABELS": STATUS_LABELS,
        "model_state": model_state,
        "has_pending": has_pending,
    }


def _model_state_string(ms: dict[str, Any] | None) -> str:
    if not ms or not ms.get("up"):
        last_up = ms.get("last_up_at") if ms else None
        if last_up:
            dt = datetime.fromisoformat(last_up)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            local = dt.astimezone(ZoneInfo(TIMEZONE))
            time_str = local.strftime("%H:%M")
            date_str = datum_kort(local.date())
            return (
                f"model offline (pc slaapt of is gepauzeerd), laatst gezien {date_str} {time_str}"
            )
        return "model offline (pc slaapt of is gepauzeerd), nog nooit gezien"
    return "model bereikbaar"


@router.get("/meetings")
async def meetings_page(
    request: Request,
    _auth: None = Depends(require_team),
) -> Response:
    """Show the meetings upload form (SPEC 7.1)."""
    with next(get_db()) as session:
        jobs = session.query(Job).filter(Job.kind == "summary").order_by(Job.id.desc()).all()
        model_status_row = session.query(AppState).filter(AppState.key == "model_status").first()

    has_pending = any(j.status in ("queued", "running") for j in jobs)
    ms = model_status_row.value if model_status_row else None
    model_state = _model_state_string(ms)

    today = today_local()

    return _meeting_templates.TemplateResponse(
        request,
        "meetings.html",
        {
            "page_title": "Vergaderingen",
            **_build_context(jobs, model_state, has_pending),
            "default_date": today.isoformat(),
            "errors": {},
            "title": "",
        },
    )


@router.get("/meetings/partial")
async def meetings_partial(
    request: Request,
    _auth: None = Depends(require_team),
) -> Response:
    """Return the jobs list fragment for HTMX polling (SPEC 7.3)."""
    with next(get_db()) as session:
        jobs = session.query(Job).filter(Job.kind == "summary").order_by(Job.id.desc()).all()
        model_status_row = session.query(AppState).filter(AppState.key == "model_status").first()

    has_pending = any(j.status in ("queued", "running") for j in jobs)
    ms = model_status_row.value if model_status_row else None
    model_state = _model_state_string(ms) if ms else ""

    return _meeting_templates.TemplateResponse(
        request,
        "_jobs.html",
        _build_context(jobs, model_state, has_pending),
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
        with next(get_db()) as session:
            jobs = session.query(Job).filter(Job.kind == "summary").order_by(Job.id.desc()).all()
        today = today_local()
        return _meeting_templates.TemplateResponse(
            request,
            "meetings.html",
            {
                "page_title": "Vergaderingen",
                "default_date": today.isoformat(),
                "errors": {"file": "Alleen .vtt en .docx bestanden worden geaccepteerd"},
                "title": title,
                **_build_context(jobs, "", False),
            },
            status_code=422,
        )

    # --- size guard: read at most MAX_UPLOAD_BYTES + 1 ---
    settings = get_settings()
    max_bytes = settings.MAX_UPLOAD_BYTES + 1
    data = await file.read(max_bytes)
    if len(data) > settings.MAX_UPLOAD_BYTES:
        today = today_local()
        return _meeting_templates.TemplateResponse(
            request,
            "meetings.html",
            {
                "page_title": "Vergaderingen",
                "default_date": today.isoformat(),
                "errors": {"file": "Het bestand is te groot"},
                "title": title,
                **_build_context([], "", False),
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
        today = today_local()
        return _meeting_templates.TemplateResponse(
            request,
            "meetings.html",
            {
                "page_title": "Vergaderingen",
                "default_date": today.isoformat(),
                "errors": {"file": "Het transcriptbestand kan niet worden gelezen"},
                "title": title,
                **_build_context([], "", False),
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
            today = today_local()
            return _meeting_templates.TemplateResponse(
                request,
                "meetings.html",
                {
                    "page_title": "Vergaderingen",
                    "default_date": today.isoformat(),
                    "errors": {"meeting_date": "Ongeldige datum (YYYY-MM-DD)"},
                    "title": title,
                    **_build_context([], "", False),
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
