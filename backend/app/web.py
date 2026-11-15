"""Web routes and Jinja2 template setup (SPEC --).

The Jinja environment is configured here with the ``templates/``
directory and the Dutch date filters from ``app.fmt`` registered as
template globals.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

from app.auth import require_team
from app.clock import today_local
from app.config import get_settings
from app.db import get_db
from app.deadlines import DeadlineIn, create, past, upcoming, update
from app.deadlines import delete as _delete_deadline
from app.meetings import _model_state_string
from app.models import AppState, Deadline, Job
from app.teams import get_teams_client
from app.templating import STATUS_LABELS, templates

router = APIRouter()


@router.get("/")
async def index(request: Request, _auth: None = Depends(require_team)) -> Response:
    """Overview (Overzicht) page — next 5 deadlines, last 3 jobs, model state."""
    with next(get_db()) as session:
        today = today_local()
        next_deadlines = upcoming(session, today=today)[:5]

        last_jobs = (
            session.query(Job).filter(Job.kind == "summary").order_by(Job.id.desc()).limit(3).all()
        )

        model_status_row = session.query(AppState).filter(AppState.key == "model_status").first()
        ms = model_status_row.value if model_status_row else None
        model_state = _model_state_string(ms)
        model_up = bool(ms and ms.get("up"))

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "next_deadlines": next_deadlines,
            "last_jobs": last_jobs,
            "STATUS_LABELS": STATUS_LABELS,
            "model_state": model_state,
            "model_up": model_up,
            "today": today,
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
            "deadline": {
                "id": None,
                "data": {
                    "title": "",
                    "due_date": "",
                    "due_time": "",
                    "note": "",
                },
                "errors": {},
            },
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

        if not due_date:
            errors["due_date"] = "Vul een datum in (YYYY-MM-DD)"
            parsed_date = None
        else:
            try:
                parsed_date = date.fromisoformat(due_date)
            except ValueError:
                parsed_date = None
                errors["due_date"] = "Ongeldige datum (YYYY-MM-DD)"

        parsed_time: dt_time | None = None
        if due_time:
            try:
                parsed_time = dt_time.fromisoformat(due_time)
            except ValueError:
                errors["due_time"] = "Ongeldige tijd (HH:MM)"

        if note and len(note) > 1000:
            errors["note"] = "Notitie mag maximaal 1000 tekens bevatten"

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
                    "deadline": {
                        "id": None,
                        "data": {
                            "title": title,
                            "due_date": due_date,
                            "due_time": due_time,
                            "note": note,
                        },
                        "errors": errors,
                    },
                },
                status_code=422,
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
            "deadline": {
                "id": deadline.id,
                "data": {
                    "title": deadline.title,
                    "due_date": deadline.due_date.isoformat(),
                    "due_time": deadline.due_time.strftime("%H:%M") if deadline.due_time else "",
                    "note": deadline.note or "",
                },
                "errors": {},
            },
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
                    "deadline": {
                        "id": deadline.id,
                        "data": {
                            "title": title,
                            "due_date": due_date,
                            "due_time": due_time,
                            "note": note,
                        },
                        "errors": errors,
                    },
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


# ---------------------------------------------------------------------------
# Privacy page (SPEC 8.4)
# ---------------------------------------------------------------------------


@router.get("/privacy")
async def privacy_page(
    request: Request,
    _auth: None = Depends(require_team),
) -> Response:
    """Privacy page in Dutch (SPEC 8.4)."""
    return templates.TemplateResponse(
        request,
        "privacy.html",
        {
            "page_title": "Privacy",
        },
    )
