"""Web routes and Jinja2 template setup (SPEC --).

The Jinja environment is configured here with the ``templates/``
directory and the Dutch date filters from ``app.fmt`` registered as
template globals.
"""

from __future__ import annotations

from pathlib import Path as _Path

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.auth import require_team
from app.clock import today_local
from app.config import TIMEZONE, get_settings
from app.db import get_db
from app.deadlines import DeadlineIn, create, past, upcoming, update
from app.deadlines import delete as _delete_deadline
from app.fmt import datum, datum_kort, relatief
from app.models import Deadline
from app.teams import get_teams_client

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


# ---------------------------------------------------------------------------
# Deadlines page routes (SPEC 3.4)
# ---------------------------------------------------------------------------


@router.get("/deadlines")
async def deadlines_page(
    request: Request,
    _auth: None = Depends(require_team),
) -> Response:
    """List all deadlines (upcoming and past) with edit/delete buttons."""

    with next(get_db()) as session:
        today = today_local()
        upcoming_dl = upcoming(session, today=today)
        past_dl = past(session, today=today)
    return templates.TemplateResponse(
        request,
        "deadlines.html",
        {
            "upcoming_deadlines": upcoming_dl,
            "past_deadlines": past_dl,
            "today": today,
            "form_title": "",
            "form_due_date": "",
            "form_due_time": "",
            "form_note": "",
            "errors": {},
        },
    )


@router.post("/deadlines")
async def deadlines_add(
    request: Request,
    title: str = Form(...),
    due_date: str = Form(...),
    due_time: str | None = Form(default=None),
    note: str | None = Form(default=None),
    _auth: None = Depends(require_team),
) -> Response:
    """Add a new deadline from the form."""
    from datetime import date
    from datetime import time as dt_time

    with next(get_db()) as session:
        # Validate
        errors: dict[str, str] = {}
        if not title.strip():
            errors["title"] = "Titel mag niet leeg zijn"
        elif len(title) > 200:
            errors["title"] = "Titel mag maximaal 200 tekens bevatten"

        try:
            parsed_date = date.fromisoformat(due_date) if due_date else None
        except (ValueError, TypeError):
            parsed_date = None
            errors["due_date"] = "Ongeldige datum (YYYY-MM-DD)"

        parsed_time: dt_time | None = None
        if due_time:
            try:
                parsed_time = dt_time.fromisoformat(due_time)
            except ValueError:
                errors["due_time"] = "Ongeldige tijd (HH:MM)"

        if errors:
            with next(get_db()) as session2:
                today = today_local()
                upcoming_dl = upcoming(session2, today=today)
                past_dl = past(session2, today=today)
            return templates.TemplateResponse(
                request,
                "deadlines.html",
                {
                    "upcoming_deadlines": upcoming_dl,
                    "past_deadlines": past_dl,
                    "today": today,
                    "form_title": title,
                    "form_due_date": due_date,
                    "form_due_time": due_time,
                    "form_note": note,
                    "errors": errors,
                },
            )

        data = DeadlineIn(title=title, due_date=parsed_date, due_time=parsed_time, note=note)
        create(session, data)
        session.commit()

    return RedirectResponse(url="/deadlines", status_code=303)


@router.get("/deadlines/{deadline_id}/edit")
async def deadlines_edit_get(
    deadline_id: int,
    request: Request,
    _auth: None = Depends(require_team),
) -> Response:
    """Show edit form for an existing deadline. 404 when not found."""
    with next(get_db()) as session:
        deadline = session.get(Deadline, deadline_id)
        if deadline is None:
            raise HTTPException(status_code=404, detail="Deadline niet gevonden")
    return templates.TemplateResponse(
        request,
        "edit.html",
        {
            "deadline": deadline,
            "form_title": deadline.title,
            "form_due_date": deadline.due_date.isoformat(),
            "form_due_time": deadline.due_time.strftime("%H:%M") if deadline.due_time else "",
            "form_note": deadline.note or "",
            "errors": {},
        },
    )


@router.post("/deadlines/{deadline_id}/edit")
async def deadlines_edit_post(
    deadline_id: int,
    request: Request,
    title: str = Form(...),
    due_date: str = Form(...),
    due_time: str | None = Form(default=None),
    note: str | None = Form(default=None),
    _auth: None = Depends(require_team),
) -> Response:
    """Save edits for an existing deadline. 404 when not found."""
    from datetime import date
    from datetime import time as dt_time

    with next(get_db()) as session:
        deadline = session.get(Deadline, deadline_id)
        if deadline is None:
            raise HTTPException(status_code=404, detail="Deadline niet gevonden")

        errors: dict[str, str] = {}
        if not title.strip():
            errors["title"] = "Titel mag niet leeg zijn"
        elif len(title) > 200:
            errors["title"] = "Titel mag maximaal 200 tekens bevatten"

        try:
            parsed_date = date.fromisoformat(due_date) if due_date else None
        except (ValueError, TypeError):
            parsed_date = None
            errors["due_date"] = "Ongeldige datum (YYYY-MM-DD)"

        parsed_time: dt_time | None = None
        if due_time:
            try:
                parsed_time = dt_time.fromisoformat(due_time)
            except ValueError:
                errors["due_time"] = "Ongeldige tijd (HH:MM)"

        if errors:
            return templates.TemplateResponse(
                request,
                "edit.html",
                {
                    "deadline": deadline,
                    "form_title": title,
                    "form_due_date": due_date,
                    "form_due_time": due_time,
                    "form_note": note,
                    "errors": errors,
                },
            )

        data = DeadlineIn(title=title, due_date=parsed_date, due_time=parsed_time, note=note)
        update(session, deadline_id, data)
        session.commit()

    return RedirectResponse(url="/deadlines", status_code=303)


@router.post("/deadlines/{deadline_id}/delete")
async def deadlines_delete(
    deadline_id: int,
    _auth: None = Depends(require_team),
) -> Response:
    """Delete a deadline. 404 when not found."""
    with next(get_db()) as session:
        found = _delete_deadline(session, deadline_id)
        if not found:
            raise HTTPException(status_code=404, detail="Deadline niet gevonden")
        session.commit()
    return RedirectResponse(url="/deadlines", status_code=303)


# ---------------------------------------------------------------------------
# Settings page routes (SPEC 4.1-4.2)
# ---------------------------------------------------------------------------


@router.get("/settings")
async def settings_page(
    request: Request,
    _auth: None = Depends(require_team),
) -> Response:
    """Display the settings form with webhook status."""
    from app.settings import load

    with next(get_db()) as session:
        settings = load(session)

    webhook_url = get_settings().TEAMS_WEBHOOK_URL
    webhook_set = bool(webhook_url and webhook_url.strip())

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "page_title": "Instellingen",
            "settings": settings,
            "webhook_set": webhook_set,
            "errors": {},
            "test_result": None,
        },
    )


@router.post("/settings")
async def settings_save(
    request: Request,
    weekly_enabled: str = Form(default="off"),
    weekly_weekday: str = Form(default="maandag"),
    weekly_time: str = Form(default="08:30"),
    deadline_reminder_enabled: str = Form(default="on"),
    deadline_reminder_time: str = Form(default="09:00"),
    deadline_reminder_days_before: str = Form(default="2,1"),
    sprint_enabled: str = Form(default="off"),
    sprint_end_date: str = Form(default=""),
    sprint_length: str = Form(default="2"),
    sprint_days_before: str = Form(default="1"),
    sprint_time: str = Form(default="09:00"),
    summary_auto_post: str = Form(default="on"),
    _auth: None = Depends(require_team),
) -> Response:
    """Save settings after validation."""
    from app.settings import ReminderSettings, save, validate_settings

    weekly_on = weekly_enabled.lower() in ("on", "true", "1", "yes")
    deadline_on = deadline_reminder_enabled.lower() in ("on", "true", "1", "yes")
    sprint_on = sprint_enabled.lower() in ("on", "true", "1", "yes")
    summary_on = summary_auto_post.lower() in ("on", "true", "1", "yes")

    s = ReminderSettings(
        weekly_enabled=weekly_on,
        weekly_weekday=weekly_weekday,
        weekly_time=weekly_time,
        deadline_reminder_enabled=deadline_on,
        deadline_reminder_time=deadline_reminder_time,
        weekdays_before=[],
        sprint_enabled=sprint_on,
        sprint_end_date=sprint_end_date,
        sprint_length=int(sprint_length) if sprint_length.strip() else 2,
        sprint_days_before=int(sprint_days_before) if sprint_days_before.strip() else 1,
        sprint_time=sprint_time,
        summary_auto_post=summary_on,
    )

    # Parse weekdays_before
    days_str = deadline_reminder_days_before.strip()
    if days_str:
        try:
            s.weekdays_before = [int(d.strip()) for d in days_str.split(",") if d.strip()]
        except ValueError:
            s.weekdays_before = []

    with next(get_db()) as session:
        errors = validate_settings(s)

        if errors:
            webhook_url = get_settings().TEAMS_WEBHOOK_URL
            webhook_set = bool(webhook_url and webhook_url.strip())
            return templates.TemplateResponse(
                request,
                "settings.html",
                {
                    "page_title": "Instellingen",
                    "settings": s,
                    "webhook_set": webhook_set,
                    "errors": errors,
                    "test_result": None,
                },
            )

        save(session, s)
        session.commit()

    return RedirectResponse(url="/settings", status_code=303)


@router.post("/settings/test")
async def settings_test(
    request: Request,
    _auth: None = Depends(require_team),
    client: httpx.Client | None = Depends(get_teams_client),
) -> Response:
    """Send a test card via Teams and show result status."""
    import uuid

    from app.cards import test_card
    from app.settings import load
    from app.teams import send_once

    ref_key = f"test-{uuid.uuid4().hex[:12]}"

    with next(get_db()) as session:
        card = test_card()
        status = send_once(session, "test", ref_key, card, client=client)

        settings = load(session)

    webhook_url = get_settings().TEAMS_WEBHOOK_URL
    webhook_set = bool(webhook_url and webhook_url.strip())

    status_labels = {
        "sent": "Verzonden",
        "dry_run": "Gedrydrun (geen webhook ingesteld)",
        "skipped": "Overslagen",
        "ok": "Ok",
        "retryable": "Herhaalbaar (probeer opnieuw)",
        "permanent": "Permanente fout",
        "failed": "Mislukt",
    }

    return templates.TemplateResponse(
        request,
        "settings.html",
        {
            "page_title": "Instellingen",
            "settings": settings,
            "webhook_set": webhook_set,
            "errors": {},
            "test_result": status_labels.get(status, status),
        },
    )
