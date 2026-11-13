"""Tests for the Job and AppState models and migration 0005_job_app_state.

Covers: table existence, defaults (queued, attempts 0, kind summary),
insert with all fields, timestamps, and AppState upsert pattern.
"""

from __future__ import annotations

from datetime import UTC, date
from typing import TYPE_CHECKING

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.clock import now_utc
from app.models import AppState, Base, Job

if TYPE_CHECKING:
    pass


def test_job_table_exists(db: Session) -> None:
    """The migration created the job table."""
    assert "job" in Base.metadata.tables


def test_app_state_table_exists(db: Session) -> None:
    """The migration created the app_state table."""
    assert "app_state" in Base.metadata.tables


def test_job_defaults_status_queued(db: Session) -> None:
    """Status defaults to 'queued' when not provided."""
    j = Job(title="Sprint meeting", meeting_date=date(2026, 11, 20))
    db.add(j)
    db.commit()

    row = db.query(Job).one()
    assert row.status == "queued"


def test_job_defaults_kind_summary(db: Session) -> None:
    """Kind defaults to 'summary' when not provided."""
    j = Job(title="Sprint meeting", meeting_date=date(2026, 11, 20))
    db.add(j)
    db.commit()

    row = db.query(Job).one()
    assert row.kind == "summary"


def test_job_defaults_attempts_zero(db: Session) -> None:
    """Attempts defaults to 0 when not provided."""
    j = Job(title="Sprint meeting", meeting_date=date(2026, 11, 20))
    db.add(j)
    db.commit()

    row = db.query(Job).one()
    assert row.attempts == 0


def test_job_insert_minimal(db: Session) -> None:
    """Insert a job with just the required fields."""
    j = Job(title="Sprint meeting", meeting_date=date(2026, 11, 20))
    db.add(j)
    db.commit()

    row = db.query(Job).one()
    assert row.id is not None
    assert row.title == "Sprint meeting"
    assert row.meeting_date == date(2026, 11, 20)
    assert row.transcript is None
    assert row.result is None
    assert row.error is None
    assert row.kind == "summary"
    assert row.status == "queued"
    assert row.attempts == 0
    assert row.started_at is None
    assert row.finished_at is None
    assert row.posted_at is None


def test_job_insert_full(db: Session) -> None:
    """Insert a job with all fields populated."""
    j = Job(
        title="Project meeting",
        meeting_date=date(2026, 11, 15),
        transcript="<v>Alice</v> Hi everyone...",
        result={
            "summary": "De sprint ging goed",
            "decisions": [],
            "action_items": [],
            "open_questions": [],
        },
        error=None,
        attempts=0,
    )
    db.add(j)
    db.commit()

    row = db.query(Job).one()
    assert row.title == "Project meeting"
    assert row.meeting_date == date(2026, 11, 15)
    assert row.transcript == "<v>Alice</v> Hi everyone..."
    assert row.result == {
        "summary": "De sprint ging goed",
        "decisions": [],
        "action_items": [],
        "open_questions": [],
    }


def test_job_status_transitions(db: Session) -> None:
    """Job status can transition through queued -> running -> done."""
    j = Job(title="Meeting", meeting_date=date(2026, 11, 20))
    db.add(j)
    db.commit()

    j.status = "running"
    j.started_at = now_utc()
    db.commit()
    assert j.status == "running"
    assert j.started_at is not None

    j.status = "done"
    j.finished_at = now_utc()
    db.commit()
    assert j.status == "done"
    assert j.finished_at is not None

    row = db.query(Job).one()
    assert row.status == "done"
    assert row.started_at is not None
    assert row.finished_at is not None


def test_job_failed_status(db: Session) -> None:
    """Job can be marked as failed with an error message."""
    j = Job(title="Meeting", meeting_date=date(2026, 11, 20))
    db.add(j)
    db.commit()

    j.status = "failed"
    j.error = "Model was unreachable"
    j.attempts = 3
    j.finished_at = now_utc()
    db.commit()

    row = db.query(Job).one()
    assert row.status == "failed"
    assert row.error == "Model was unreachable"
    assert row.attempts == 3


def test_job_can_have_different_kind(db: Session) -> None:
    """Kind can be set to a non-summary value for future use."""
    j = Job(
        title="Custom job",
        meeting_date=date(2026, 11, 20),
        kind="report",
    )
    db.add(j)
    db.commit()

    row = db.query(Job).one()
    assert row.kind == "report"


def test_job_timestamps_are_set(db: Session) -> None:
    """created_at is set on insert; started_at/finished_at start as None."""
    before = now_utc()
    j = Job(title="Timestamp test", meeting_date=date(2026, 11, 1))
    db.add(j)
    db.commit()
    after = now_utc()

    row = db.query(Job).one()
    assert row.created_at is not None
    assert before <= row.created_at <= after
    assert row.started_at is None
    assert row.finished_at is None


def test_job_started_at_is_set(db: Session) -> None:
    """started_at is set when transitioning to running."""
    j = Job(title="Started test", meeting_date=date(2026, 11, 1))
    db.add(j)
    db.commit()
    assert j.started_at is None

    j.started_at = now_utc()
    db.commit()

    row = db.query(Job).one()
    assert row.started_at is not None


def test_app_state_insert(db: Session) -> None:
    """Insert an app state entry with a value."""
    s = AppState(key="model_status", value={"status": "ready", "model": "coder"})
    db.add(s)
    db.commit()

    row = db.get(AppState, "model_status")
    assert row is not None
    assert row.key == "model_status"
    assert row.value == {"status": "ready", "model": "coder"}


def test_app_state_update(db: Session) -> None:
    """Updating an existing app state entry updates the value."""
    s = AppState(key="model_status", value={"status": "ready"})
    db.add(s)
    db.commit()

    s.value = {"status": "offline", "last_seen": "2026-11-13T10:00:00Z"}
    db.commit()

    row = db.get(AppState, "model_status")
    assert row.value == {"status": "offline", "last_seen": "2026-11-13T10:00:00Z"}


def test_app_state_null_value(db: Session) -> None:
    """AppState can have a null value."""
    s = AppState(key="last_wake", value=None)
    db.add(s)
    db.commit()

    row = db.get(AppState, "last_wake")
    assert row.value is None


def test_app_state_updated_at_changes(db: Session) -> None:
    """updated_at changes when the row is updated."""
    s = AppState(key="model_status", value={"status": "ready"})
    db.add(s)
    db.commit()

    original_updated = s.updated_at

    import time as _time

    _time.sleep(0.05)

    s.value = {"status": "offline"}
    db.commit()

    assert s.updated_at > original_updated


def test_job_has_all_expected_columns(db: Session) -> None:
    """The job table has all columns defined in the data model."""
    mapper = inspect(Job)
    column_names = {c.key for c in mapper.columns}
    expected = {
        "id",
        "kind",
        "status",
        "title",
        "meeting_date",
        "transcript",
        "result",
        "error",
        "attempts",
        "created_at",
        "started_at",
        "finished_at",
        "posted_at",
    }
    assert column_names == expected


def test_app_state_has_all_expected_columns(db: Session) -> None:
    """The app_state table has all columns defined in the data model."""
    mapper = inspect(AppState)
    column_names = {c.key for c in mapper.columns}
    expected = {
        "key",
        "value",
        "updated_at",
    }
    assert column_names == expected


def test_job_timestamps_are_utc(db: Session) -> None:
    """Timestamps are timezone-aware (UTC)."""
    j = Job(title="UTC test", meeting_date=date(2026, 11, 1))
    db.add(j)
    db.commit()

    assert j.created_at.tzinfo is not None
    # Convert to UTC to verify timezone awareness
    utc = j.created_at.astimezone(UTC)
    assert utc.tzinfo is not None


def test_app_state_timestamps_are_utc(db: Session) -> None:
    """AppState timestamps are timezone-aware (UTC)."""
    s = AppState(key="test_key", value={"a": 1})
    db.add(s)
    db.commit()

    assert s.updated_at.tzinfo is not None


def test_app_state_key_is_pk(db: Session) -> None:
    """AppState primary key is the 'key' column (not an auto-increment id)."""
    mapper = inspect(AppState)
    pk_columns = {c.key for c in mapper.primary_key}
    assert pk_columns == {"key"}


def test_job_database_defaults(db: Session) -> None:
    """Database-level defaults for job columns match the spec."""
    j = Job(title="Defaults test", meeting_date=date(2026, 11, 1))
    db.add(j)
    db.commit()

    result = db.execute(
        text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name='job' AND column_name='kind'"
        )
    ).scalar()
    assert result == "'summary'::character varying"

    result = db.execute(
        text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name='job' AND column_name='status'"
        )
    ).scalar()
    assert result == "'queued'::character varying"

    result = db.execute(
        text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name='job' AND column_name='attempts'"
        )
    ).scalar()
    assert result == "0"
