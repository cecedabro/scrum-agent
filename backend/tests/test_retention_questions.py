"""Tests for question-job retention (SPEC 10.6) and privacy page.

- 31-day-old question deleted by retention
- 29-day-old question kept by retention
- summary jobs are untouched by question retention
- /privacy mentions "Vragen aan @Agent"
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.models import Job
from app.retention import apply_retention


class TestQuestionRetention:
    """SPEC 10.6: question jobs deleted 30 days after creation."""

    def test_31_day_old_question_deleted(self, db, monkeypatch):
        """A question job 31 days old is deleted by retention."""
        monkeypatch.setenv("QUESTION_RETENTION_DAYS", "30")
        get_settings.cache_clear()

        now = datetime(2025, 2, 15, 12, 0, 0, tzinfo=UTC)
        old_created = now - timedelta(days=31)
        job = Job(
            kind="question",
            status="done",
            title="Hoe werkt sprint?",
            meeting_date=now.date(),
            created_at=old_created,
            result={"answer": "Sprint is een vaste periode."},
        )
        db.add(job)
        db.commit()

        logs = apply_retention(db, now)

        assert any("question jobs" in line for line in logs)
        remaining = db.execute(select(Job).where(Job.id == job.id)).scalar_one_or_none()
        assert remaining is None

    def test_29_day_old_question_kept(self, db, monkeypatch):
        """A question job 29 days old is kept by retention."""
        monkeypatch.setenv("QUESTION_RETENTION_DAYS", "30")
        get_settings.cache_clear()

        now = datetime(2025, 2, 15, 12, 0, 0, tzinfo=UTC)
        recent_created = now - timedelta(days=29)
        job = Job(
            kind="question",
            status="queued",
            title="Wat is de sprint datum?",
            meeting_date=now.date(),
            created_at=recent_created,
        )
        db.add(job)
        db.commit()

        apply_retention(db, now)

        remaining = db.execute(select(Job).where(Job.id == job.id)).scalar_one()
        assert remaining is not None
        assert remaining.kind == "question"

    def test_summary_jobs_untouched(self, db, monkeypatch):
        """Summary jobs are not deleted by question retention."""
        monkeypatch.setenv("QUESTION_RETENTION_DAYS", "30")
        get_settings.cache_clear()

        now = datetime(2025, 2, 15, 12, 0, 0, tzinfo=UTC)
        old_question = Job(
            kind="question",
            status="done",
            title="Old question",
            meeting_date=now.date(),
            created_at=now - timedelta(days=35),
        )
        recent_summary = Job(
            kind="summary",
            status="done",
            title="Recent summary",
            meeting_date=now.date(),
            created_at=now - timedelta(days=5),
            result={"summary": "De vergadering ging goed."},
            finished_at=now - timedelta(days=4),
        )
        old_summary = Job(
            kind="summary",
            status="done",
            title="Old summary",
            meeting_date=now.date(),
            created_at=now - timedelta(days=35),
            result={"summary": "Oud."},
            finished_at=now - timedelta(days=34),
        )
        db.add_all([old_question, recent_summary, old_summary])
        db.commit()

        apply_retention(db, now)

        # Old question should be deleted
        assert db.execute(select(Job).where(Job.id == old_question.id)).scalar_one_or_none() is None

        # Recent summary should still exist (within retention)
        result = db.execute(select(Job).where(Job.id == recent_summary.id)).scalar_one_or_none()
        assert result is not None

        # Old summary may be deleted by summary retention but that's unrelated to question retention
        # (it's deleted because it has a result and finished_at > SUMMARY_RETENTION_DAYS)


class TestPrivacyPage:
    """SPEC 10.6: /privacy page mentions question retention."""

    def test_privacy_mentions_vragen_aan_agent(self, auth_client: TestClient) -> None:
        """/privacy page mentions 'Vragen aan @Agent'."""
        r = auth_client.get("/privacy")
        assert r.status_code == 200
        assert "Vragen aan" in r.text
        assert "@Agent" in r.text
