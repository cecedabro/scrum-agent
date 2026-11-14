"""Tests for model check and recovery in the worker (TASK T31).

Covers:
- Model down → run_once returns "model_offline", job stays queued,
  model_status stored in app_state.
- Model up → last_up_at updated, job processing proceeds normally.
- reset_stuck → jobs running > 30 min go back to queued.
- reset_stuck → jobs running < 30 min are untouched.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.clock import now_utc
from app.models import AppState, Job
from app.worker import reset_stuck, run_once


class TestModelDown:
    """When the model is down, jobs stay queued and status is stored."""

    @pytest.fixture(autouse=True)
    def _mock_model_down(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.worker.is_up", lambda *a, **k: False)

    def test_model_down_stays_queued(self, db: object) -> None:
        """Model down: no job is claimed, status stored with up=False."""
        job = Job(
            kind="summary",
            status="queued",
            title="Sprint planning",
            meeting_date=datetime(2024, 1, 15).date(),
            transcript="Alice: We need to finish the backend.",
        )
        db.add(job)
        db.commit()

        now = now_utc()
        result = run_once(db, now)

        assert result == "model_offline"

        # Job stays unchanged.
        job = db.execute(select(Job).where(Job.id == job.id)).scalar_one()
        assert job.status == "queued"
        assert job.attempts == 0
        assert job.started_at is None

        # Model status stored with up=False.
        row = db.execute(
            select(AppState).where(AppState.key == "model_status")
        ).scalar_one()
        assert row.value["up"] is False
        assert row.value["checked_at"] is not None
        assert row.value["last_up_at"] is None

    def test_model_down_no_jobs(self, db: object) -> None:
        """Model down with no jobs: still returns model_offline, status stored."""
        now = now_utc()
        result = run_once(db, now)

        assert result == "model_offline"

        row = db.execute(
            select(AppState).where(AppState.key == "model_status")
        ).scalar_one()
        assert row.value["up"] is False


class TestModelUp:
    """When the model is up, last_up_at is updated and jobs are processed."""

    @pytest.fixture(autouse=True)
    def _mock_model_up(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("app.worker.is_up", lambda *a, **k: True)

    @pytest.fixture(autouse=True)
    def _mock_summarize(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import MagicMock

        mock_result = MagicMock()
        mock_result.model_dump.return_value = {
            "summary": "Samenvatting.",
            "decisions": [],
            "action_items": [],
            "open_questions": [],
        }
        monkeypatch.setattr("app.worker.summarize", lambda *a, **k: mock_result)

    def test_model_up_updates_last_up_at(self, db: object) -> None:
        """Model up with a job: last_up_at updated, job processed to done."""
        job = Job(
            kind="summary",
            status="queued",
            title="Sprint planning",
            meeting_date=datetime(2024, 1, 15).date(),
            transcript="Alice: We need to finish the backend.",
        )
        db.add(job)
        db.commit()

        now = now_utc()
        result = run_once(db, now)

        assert result == "done"

        job = db.execute(select(Job).where(Job.id == job.id)).scalar_one()
        assert job.status == "done"

        # last_up_at updated to the current time.
        row = db.execute(
            select(AppState).where(AppState.key == "model_status")
        ).scalar_one()
        assert row.value["up"] is True
        assert row.value["last_up_at"] is not None


class TestResetStuck:
    """Jobs running > 30 min are reset to queued."""

    def test_reset_stuck_31_minutes(self, db: object) -> None:
        """Job running for 31 minutes is reset to queued."""
        now = now_utc()
        old_started = now - timedelta(minutes=31)

        job = Job(
            kind="summary",
            status="running",
            title="Old meeting",
            meeting_date=datetime(2024, 1, 15).date(),
            started_at=old_started,
        )
        db.add(job)
        db.commit()

        reset_stuck(db, now)

        job = db.execute(select(Job).where(Job.id == job.id)).scalar_one()
        assert job.status == "queued"
        assert job.started_at is None

    def test_reset_stuck_29_minutes_not_reset(self, db: object) -> None:
        """Job running for 29 minutes stays running."""
        now = now_utc()
        recent_started = now - timedelta(minutes=29)

        job = Job(
            kind="summary",
            status="running",
            title="Recent meeting",
            meeting_date=datetime(2024, 1, 15).date(),
            started_at=recent_started,
        )
        db.add(job)
        db.commit()

        reset_stuck(db, now)

        job = db.execute(select(Job).where(Job.id == job.id)).scalar_one()
        assert job.status == "running"
        assert job.started_at is not None

    def test_reset_stuck_no_stuck_jobs(self, db: object) -> None:
        """No stuck jobs: nothing changes."""
        now = now_utc()

        done_job = Job(
            kind="summary",
            status="done",
            title="Done meeting",
            meeting_date=datetime(2024, 1, 15).date(),
            started_at=now - timedelta(hours=2),
        )
        db.add(done_job)
        db.commit()

        reset_stuck(db, now)

        done_job = db.execute(
            select(Job).where(Job.id == done_job.id)
        ).scalar_one()
        assert done_job.status == "done"
