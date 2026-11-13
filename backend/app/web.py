"""Web routes and Jinja2 template setup (SPEC --).

The Jinja environment is configured here with the ``templates/``
directory and the Dutch date filters from ``app.fmt`` registered as
template globals.
"""

from __future__ import annotations

from pathlib import Path as _Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.auth import require_team
from app.clock import today_local
from app.config import TIMEZONE
from app.db import get_db
from app.deadlines import DeadlineIn, create, past, upcoming, update
from app.deadlines import delete as _delete_deadline
from app.fmt import datum, datum_kort, relatief
from app.models import Deadline

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
