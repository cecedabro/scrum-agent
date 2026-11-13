"""Tests for the deadlines service module (app/deadlines.py).

Covers: DeadlineIn validation (SPEC 3.1), CRUD operations, and query
helpers (upcoming / between / past) with correct sorting.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from app.deadlines import (
    DeadlineIn,
    between,
    create,
    delete,
    past,
    upcoming,
    update,
)
from app.models import Deadline

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

# ---------------------------------------------------------------------------
# DeadlineIn validation
# ---------------------------------------------------------------------------


def test_title_200_chars_accepted() -> None:
    """A title of exactly 200 characters is valid."""
    title = "A" * 200
    data = DeadlineIn(title=title, due_date=date(2026, 11, 20))
    assert data.title == title


def test_title_201_chars_rejected() -> None:
    """A title of 201 characters raises a validation error."""
    title = "A" * 201
    with pytest.raises(ValidationError) as exc_info:
        DeadlineIn(title=title, due_date=date(2026, 11, 20))
    errors = exc_info.value.errors()
    titles = [e["loc"][-1] for e in errors]
    assert "title" in titles


def test_empty_title_rejected() -> None:
    """An empty or whitespace-only title is rejected."""
    for empty in ("", "   ", "\t"):
        with pytest.raises(ValidationError) as exc_info:
            DeadlineIn(title=empty, due_date=date(2026, 11, 20))
        errors = exc_info.value.errors()
        titles = [e["loc"][-1] for e in errors]
        assert "title" in titles


def test_empty_title_dutch_message() -> None:
    """The empty-title error message is in Dutch."""
    with pytest.raises(ValidationError) as exc_info:
        DeadlineIn(title="", due_date=date(2026, 11, 20))
    msgs = [e["msg"] for e in exc_info.value.errors()]
    assert any("titel" in m.lower() for m in msgs)


def test_bad_due_time_rejected() -> None:
    """A due_time value that is out of range raises a validation error."""
    # Pydantic coerces "HH:MM" strings to time objects.  An invalid hour
    # (25) in a string cannot be coerced, so it raises ValidationError.
    with pytest.raises(ValidationError):
        DeadlineIn(title="Test", due_date=date(2026, 11, 20), due_time="25:00")


def test_valid_due_time_accepted() -> None:
    """A valid time (e.g. 09:30) is accepted as-is."""
    data = DeadlineIn(
        title="Test",
        due_date=date(2026, 11, 20),
        due_time=time(9, 30),
    )
    assert data.due_time == time(9, 30)


def test_note_max_1000_chars_accepted() -> None:
    """A note of exactly 1000 characters is valid."""
    note = "N" * 1000
    data = DeadlineIn(title="Test", due_date=date(2026, 11, 20), note=note)
    assert data.note == note


def test_note_1001_chars_rejected() -> None:
    """A note of 1001 characters raises a validation error."""
    note = "N" * 1001
    with pytest.raises(ValidationError):
        DeadlineIn(title="Test", due_date=date(2026, 11, 20), note=note)


def test_invalid_source_rejected() -> None:
    """A source that is neither 'manual' nor 'github' is rejected."""
    with pytest.raises(ValidationError) as exc_info:
        DeadlineIn(title="Test", due_date=date(2026, 11, 20), source="slack")
    msgs = [e["msg"] for e in exc_info.value.errors()]
    assert any("bron" in m.lower() for m in msgs)


def test_defaults_manual_and_none() -> None:
    """Source defaults to 'manual'; time, note, external_ref default to None."""
    data = DeadlineIn(title="Test", due_date=date(2026, 11, 20))
    assert data.source == "manual"
    assert data.due_time is None
    assert data.note is None
    assert data.external_ref is None


# ---------------------------------------------------------------------------
# CRUD: create
# ---------------------------------------------------------------------------


def test_create_minimal(db: Session) -> None:
    """create() stores a minimal deadline and returns it."""
    data = DeadlineIn(title="Dutch homework", due_date=date(2026, 11, 25))
    now = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
    result = create(db, data, now=now)
    db.commit()

    assert result.title == "Dutch homework"
    assert result.due_date == date(2026, 11, 25)
    assert result.due_time is None
    assert result.source == "manual"
    assert result.created_at == now
    assert result.updated_at == now

    row = db.query(Deadline).one()
    assert row.id is not None


def test_create_with_all_fields(db: Session) -> None:
    """create() stores every field when provided."""
    data = DeadlineIn(
        title="Full deadline",
        due_date=date(2026, 12, 1),
        due_time=time(14, 0),
        note="Bring calculator",
        source="github",
        external_ref="issue/42",
    )
    now = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
    result = create(db, data, now=now)
    db.commit()

    assert result.due_time == time(14, 0)
    assert result.note == "Bring calculator"
    assert result.source == "github"
    assert result.external_ref == "issue/42"


# ---------------------------------------------------------------------------
# CRUD: update
# ---------------------------------------------------------------------------


def test_update_existing(db: Session) -> None:
    """update() changes the deadline and returns it."""
    now = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
    original = create(db, DeadlineIn(title="Old", due_date=date(2026, 11, 20)), now=now)
    db.commit()

    new_time = datetime(2026, 11, 17, 8, 0, tzinfo=UTC)
    data = DeadlineIn(title="New title", due_date=date(2026, 12, 1))
    result = update(db, original.id, data, now=new_time)
    db.commit()

    assert result is not None
    assert result.title == "New title"
    assert result.due_date == date(2026, 12, 1)
    assert result.updated_at == new_time


def test_update_nonexistent_returns_none(db: Session) -> None:
    """update() on a missing id returns None."""
    data = DeadlineIn(title="Ghost", due_date=date(2026, 11, 20))
    result = update(db, 99999, data)
    assert result is None


# ---------------------------------------------------------------------------
# CRUD: delete
# ---------------------------------------------------------------------------


def test_delete_existing(db: Session) -> None:
    """delete() removes a deadline and returns True."""
    dl = create(db, DeadlineIn(title="Delete me", due_date=date(2026, 11, 20)))
    db.commit()

    assert delete(db, dl.id) is True
    assert db.query(Deadline).count() == 0


def test_delete_nonexistent_returns_false(db: Session) -> None:
    """delete() on a missing id returns False."""
    assert delete(db, 99999) is False


# ---------------------------------------------------------------------------
# Query: sorting (upcoming / past)
# ---------------------------------------------------------------------------


def test_upcoming_sorted_by_date_and_time(db: Session) -> None:
    """Upcoming deadlines are sorted by date, then time."""
    now = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
    today = date(2026, 11, 16)
    create(db, DeadlineIn(title="Later today", due_date=today, due_time=time(15, 0)), now=now)
    create(db, DeadlineIn(title="Morning", due_date=today, due_time=time(8, 0)), now=now)
    create(db, DeadlineIn(title="No time", due_date=today), now=now)
    create(db, DeadlineIn(title="Tomorrow", due_date=date(2026, 11, 17)), now=now)
    db.commit()

    results = upcoming(db, today=today)
    titles = [r.title for r in results]
    # "No time" has no due_time → end of day → sorted after "Later today"
    assert titles == ["Morning", "Later today", "No time", "Tomorrow"]


def test_past_sorted_by_date(db: Session) -> None:
    """Past deadlines are sorted by date (oldest first)."""
    now = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
    create(db, DeadlineIn(title="Nov 1", due_date=date(2026, 11, 1)), now=now)
    create(db, DeadlineIn(title="Nov 10", due_date=date(2026, 11, 10)), now=now)
    create(db, DeadlineIn(title="Nov 15", due_date=date(2026, 11, 15)), now=now)
    db.commit()

    results = past(db, today=date(2026, 11, 16))
    titles = [r.title for r in results]
    assert titles == ["Nov 1", "Nov 10", "Nov 15"]


def test_no_time_sorts_to_end_of_day(db: Session) -> None:
    """A deadline with no time is sorted after same-day deadlines with times."""
    now = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
    today = date(2026, 11, 16)
    create(db, DeadlineIn(title="8am", due_date=today, due_time=time(8, 0)), now=now)
    create(db, DeadlineIn(title="No time (end of day)", due_date=today), now=now)
    create(db, DeadlineIn(title="17h", due_date=today, due_time=time(17, 0)), now=now)
    db.commit()

    results = upcoming(db, today=today)
    titles = [r.title for r in results]
    assert titles == ["8am", "17h", "No time (end of day)"]


# ---------------------------------------------------------------------------
# Query: between (inclusive on both ends)
# ---------------------------------------------------------------------------


def test_between_inclusive_on_both_ends(db: Session) -> None:
    """between() includes deadlines on both start and end dates."""
    now = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
    create(db, DeadlineIn(title="Nov 10", due_date=date(2026, 11, 10)), now=now)
    create(db, DeadlineIn(title="Nov 15", due_date=date(2026, 11, 15)), now=now)
    create(db, DeadlineIn(title="Nov 20", due_date=date(2026, 11, 20)), now=now)
    create(db, DeadlineIn(title="Nov 25", due_date=date(2026, 11, 25)), now=now)
    create(db, DeadlineIn(title="Nov 30", due_date=date(2026, 11, 30)), now=now)
    db.commit()

    results = between(db, start=date(2026, 11, 15), end=date(2026, 11, 25))
    titles = [r.title for r in results]
    assert titles == ["Nov 15", "Nov 20", "Nov 25"]


def test_between_no_results(db: Session) -> None:
    """between() returns an empty list when no deadlines match."""
    now = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
    create(db, DeadlineIn(title="Nov 1", due_date=date(2026, 11, 1)), now=now)
    db.commit()

    results = between(db, start=date(2026, 12, 1), end=date(2026, 12, 31))
    assert results == []


# ---------------------------------------------------------------------------
# Query: upcoming excludes past
# ---------------------------------------------------------------------------


def test_upcoming_excludes_past(db: Session) -> None:
    """upcoming() does not return deadlines before today."""
    now = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
    today = date(2026, 11, 16)
    create(db, DeadlineIn(title="Past", due_date=date(2026, 11, 10)), now=now)
    create(db, DeadlineIn(title="Today", due_date=today), now=now)
    create(db, DeadlineIn(title="Tomorrow", due_date=date(2026, 11, 17)), now=now)
    db.commit()

    results = upcoming(db, today=today)
    titles = [r.title for r in results]
    assert "Past" not in titles
    assert "Today" in titles
    assert "Tomorrow" in titles


# ---------------------------------------------------------------------------
# Query: past excludes today
# ---------------------------------------------------------------------------


def test_past_excludes_today(db: Session) -> None:
    """past() does not return deadlines on today's date."""
    now = datetime(2026, 11, 16, 10, 0, tzinfo=UTC)
    today = date(2026, 11, 16)
    create(db, DeadlineIn(title="Today", due_date=today), now=now)
    create(db, DeadlineIn(title="Yesterday", due_date=date(2026, 11, 15)), now=now)
    db.commit()

    results = past(db, today=today)
    titles = [r.title for r in results]
    assert "Today" not in titles
    assert "Yesterday" in titles
