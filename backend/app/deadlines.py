"""Service functions for deadline CRUD operations.

All public functions take a SQLAlchemy ``Session`` and optionally ``now``
(a UTC-aware ``datetime``) so tests can pass a fixed moment.

SPEC 3.1 validation lives in the ``DeadlineIn`` pydantic model.

API routes live in ``api_router`` (SPEC 3.5).
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, field_validator, model_validator

from app.auth import require_team
from app.clock import now_utc as _now_utc
from app.models import Deadline

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ---------------------------------------------------------------------------
# Pydantic input model (SPEC 3.1)
# ---------------------------------------------------------------------------


class DeadlineIn(BaseModel):
    """Validated input for creating / updating a deadline.

    All user-facing validation error messages are in Dutch.
    """

    title: str
    due_date: date
    due_time: time | None = None
    note: str | None = None
    source: str = "manual"
    external_ref: str | None = None

    @field_validator("title")
    @classmethod
    def title_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Titel mag niet leeg zijn")
        return v

    @field_validator("title")
    @classmethod
    def title_max_length(cls, v: str) -> str:
        if len(v) > 200:
            raise ValueError("Titel mag maximaal 200 tekens bevatten")
        return v

    @field_validator("note")
    @classmethod
    def note_max_length(cls, v: str | None) -> str | None:
        if v is not None and len(v) > 1000:
            raise ValueError("Notitie mag maximaal 1000 tekens bevatten")
        return v

    @field_validator("due_time")
    @classmethod
    def due_time_must_be_valid(cls, v: time | None) -> time | None:
        # Pydantic's type coercion already rejects bad values, but we
        # provide a Dutch message for completeness.
        if v is not None and not (0 <= v.hour <= 23 and 0 <= v.minute <= 59):
            raise ValueError("Tijd is niet geldig (HH:MM)")
        return v

    @model_validator(mode="after")
    def source_must_be_valid(self) -> DeadlineIn:
        if self.source not in ("manual", "github"):
            raise ValueError("Bron moet 'manual' of 'github' zijn")
        return self


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------


def create(
    session: Session,
    data: DeadlineIn,
    now: datetime | None = None,
) -> Deadline:
    """Persist a new deadline and return it.

    ``now`` defaults to the real clock; tests may pass a fixed moment.
    """
    utc = now or _now_utc()
    deadline = Deadline(
        title=data.title,
        due_date=data.due_date,
        due_time=data.due_time,
        note=data.note,
        source=data.source,
        external_ref=data.external_ref,
        created_at=utc,
        updated_at=utc,
    )
    session.add(deadline)
    session.flush()
    return deadline


def update(
    session: Session,
    deadline_id: int,
    data: DeadlineIn,
    now: datetime | None = None,
) -> Deadline | None:
    """Update an existing deadline by id. Returns ``None`` if not found."""
    utc = now or _now_utc()
    deadline = session.get(Deadline, deadline_id)
    if deadline is None:
        return None
    deadline.title = data.title
    deadline.due_date = data.due_date
    deadline.due_time = data.due_time
    deadline.note = data.note
    deadline.source = data.source
    deadline.external_ref = data.external_ref
    deadline.updated_at = utc
    session.flush()
    return deadline


def delete(
    session: Session,
    deadline_id: int,
) -> bool:
    """Delete a deadline by id. Returns ``True`` when a row was removed."""
    deadline = session.get(Deadline, deadline_id)
    if deadline is None:
        return False
    session.delete(deadline)
    session.flush()
    return True


# ---------------------------------------------------------------------------
# Query helpers (sorted)
# ---------------------------------------------------------------------------


def _sort_key(dl: Deadline) -> tuple[date, time]:
    """Sort key: date ascending, then time ascending (None → end of day)."""
    time_val = dl.due_time if dl.due_time is not None else time(23, 59)
    return (dl.due_date, time_val)


def upcoming(
    session: Session,
    today: date | None = None,
    now: datetime | None = None,
) -> list[Deadline]:
    """Upcoming deadlines (today and later), sorted by date then time."""
    if today is None:
        from app.clock import today_local

        today = today_local(now)
    from sqlalchemy import select

    stmt = (
        select(Deadline)
        .where(Deadline.due_date >= today)
        .order_by(Deadline.due_date, Deadline.due_time)
    )
    return list(session.scalars(stmt).all())


def between(
    session: Session,
    start: date,
    end: date,
    now: datetime | None = None,
) -> list[Deadline]:
    """Deadlines between *start* and *end* inclusive on both ends, sorted."""
    from sqlalchemy import select

    stmt = (
        select(Deadline)
        .where(Deadline.due_date >= start)
        .where(Deadline.due_date <= end)
        .order_by(Deadline.due_date, Deadline.due_time)
    )
    return list(session.scalars(stmt).all())


def past(
    session: Session,
    today: date | None = None,
    now: datetime | None = None,
) -> list[Deadline]:
    """Past deadlines (before today), sorted by date then time."""
    if today is None:
        from app.clock import today_local

        today = today_local(now)
    from sqlalchemy import select

    stmt = (
        select(Deadline)
        .where(Deadline.due_date < today)
        .order_by(Deadline.due_date, Deadline.due_time)
    )
    return list(session.scalars(stmt).all())


# ---------------------------------------------------------------------------
# API response model (SPEC 3.5)
# ---------------------------------------------------------------------------


class DeadlineOut(BaseModel):
    """Deadline output for the JSON API (SPEC 3.5)."""

    id: int
    title: str
    due_date: date
    due_time: time | None = None
    note: str | None = None
    source: str


def _deadline_to_out(dl: Deadline) -> dict[str, Any]:
    """Convert a Deadline ORM object to a JSON-serialisable dict."""
    return {
        "id": dl.id,
        "title": dl.title,
        "due_date": dl.due_date.isoformat(),
        "due_time": dl.due_time.isoformat() if dl.due_time else None,
        "note": dl.note,
        "source": dl.source,
    }


# ---------------------------------------------------------------------------
# API router (SPEC 3.5)
# ---------------------------------------------------------------------------

api_router = APIRouter(prefix="/api/v1/deadlines", tags=["deadlines"])


@api_router.get("")
def list_deadlines(
    include_past: bool = Query(default=False),
    _auth: None = Depends(require_team),
) -> list[dict[str, Any]]:
    """Upcoming deadlines, or all when include_past=true (SPEC 3.5)."""
    from app.db import get_db

    with next(get_db()) as session:
        deadlines = past(session) + upcoming(session) if include_past else upcoming(session)
        return [_deadline_to_out(dl) for dl in deadlines]


@api_router.post("", status_code=status.HTTP_201_CREATED)
def create_deadline(
    data: DeadlineIn,
    _auth: None = Depends(require_team),
) -> dict[str, Any]:
    """Create a deadline and return it (SPEC 3.5)."""
    from app.db import get_db

    with next(get_db()) as session:
        deadline = create(session, data, now=_now_utc())
        session.commit()
        return _deadline_to_out(deadline)


@api_router.delete("/{deadline_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deadline(
    deadline_id: int,
    _auth: None = Depends(require_team),
) -> None:
    """Delete a deadline by id; 404 when not found (SPEC 3.5)."""
    from app.db import get_db

    with next(get_db()) as session:
        found = delete(session, deadline_id)
        if not found:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Deadline not found",
            )
        session.commit()
