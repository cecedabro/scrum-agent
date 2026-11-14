"""Tests for the Deadline model and migration 0002_deadline.

Covers: insert with and without time/note, source defaults to manual,
timestamps are set, and the row is retrievable.
"""

from __future__ import annotations

from datetime import date, time
from typing import TYPE_CHECKING

from sqlalchemy import inspect, text

from app.clock import now_utc
from app.models import Base, Deadline

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def test_deadline_table_exists(db: Session) -> None:
    """The migration created the deadline table."""
    assert "deadline" in Base.metadata.tables


def test_insert_minimal(db: Session) -> None:
    """Insert a deadline without time or note; source defaults to manual."""
    d = Deadline(title="Sprint eindigen", due_date=date(2026, 11, 20))
    db.add(d)
    db.commit()

    row = db.query(Deadline).one()
    assert row.id is not None
    assert row.title == "Sprint eindigen"
    assert row.due_date == date(2026, 11, 20)
    assert row.due_time is None
    assert row.note is None
    assert row.source == "manual"
    assert row.external_ref is None


def test_insert_with_time_and_note(db: Session) -> None:
    """Insert a deadline with all fields populated."""
    d = Deadline(
        title="Opdracht inleveren",
        due_date=date(2026, 12, 1),
        due_time=time(14, 30),
        note="Alleen PDF, maximaal 10 pagina's.",
    )
    db.add(d)
    db.commit()

    row = db.query(Deadline).one()
    assert row.title == "Opdracht inleveren"
    assert row.due_date == date(2026, 12, 1)
    assert row.due_time == time(14, 30)
    assert row.note == "Alleen PDF, maximaal 10 pagina's."
    assert row.source == "manual"


def test_insert_with_external_ref(db: Session) -> None:
    """Insert a deadline with an external reference."""
    d = Deadline(
        title="GitHub issue #42",
        due_date=date(2026, 11, 25),
        external_ref="https://github.com/example/repo/issues/42",
    )
    db.add(d)
    db.commit()

    row = db.query(Deadline).one()
    assert row.external_ref == "https://github.com/example/repo/issues/42"


def test_source_default_is_manual(db: Session) -> None:
    """source column defaults to 'manual' when not provided."""
    d = Deadline(title="Default source", due_date=date(2026, 11, 15))
    db.add(d)
    db.commit()

    # Check the database default as well
    result = db.execute(
        text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name='deadline' AND column_name='source'"
        )
    ).scalar()
    assert result == "'manual'::character varying"


def test_source_can_be_set(db: Session) -> None:
    """source can be explicitly set to a different value."""
    d = Deadline(
        title="Imported",
        due_date=date(2026, 11, 10),
        source="github",
    )
    db.add(d)
    db.commit()

    row = db.query(Deadline).one()
    assert row.source == "github"


def test_timestamps_are_set(db: Session) -> None:
    """created_at and updated_at are set on insert."""
    before = now_utc()
    d = Deadline(title="Timestamp test", due_date=date(2026, 11, 1))
    db.add(d)
    db.commit()
    after = now_utc()

    row = db.query(Deadline).one()
    assert row.created_at is not None
    assert row.updated_at is not None
    # Timestamps should be between before/after (with some tolerance for test speed)
    assert before <= row.created_at <= after
    assert before <= row.updated_at <= after


def test_updated_at_changes_on_update(db: Session) -> None:
    """updated_at changes when the row is updated."""
    d = Deadline(title="Old title", due_date=date(2026, 11, 1))
    db.add(d)
    db.commit()

    original_updated = d.updated_at

    # Small delay to ensure different timestamp
    import time as _time

    _time.sleep(0.05)

    d.title = "New title"
    db.commit()

    assert d.updated_at > original_updated


def test_deadline_has_all_expected_columns(db: Session) -> None:
    """The deadline table has all columns defined in the data model."""
    mapper = inspect(Deadline)
    column_names = {c.key for c in mapper.columns}
    expected = {
        "id",
        "title",
        "due_date",
        "due_time",
        "note",
        "source",
        "external_ref",
        "created_at",
        "updated_at",
    }
    assert column_names == expected


def test_timestamps_are_utc(db: Session) -> None:
    """Timestamps are timezone-aware (UTC)."""
    d = Deadline(title="UTC test", due_date=date(2026, 11, 1))
    db.add(d)
    db.commit()

    assert d.created_at.tzinfo is not None
    assert d.updated_at.tzinfo is not None


def test_title_max_length(db: Session) -> None:
    """Title can be at the maximum allowed length (200 chars)."""
    long_title = "A" * 200
    d = Deadline(title=long_title, due_date=date(2026, 11, 1))
    db.add(d)
    db.commit()

    row = db.query(Deadline).one()
    assert row.title == long_title
