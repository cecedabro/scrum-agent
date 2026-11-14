"""Tests for ``app.retention.apply_retention`` (SPEC 8.1-8.2).

Each rule is tested one day before and one day after its limit.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.config import get_settings
from app.models import Deadline, Job, PostLog
from app.retention import apply_retention


class TestTranscriptRetention:
    """SPEC 8.1: transcript deleted when summary stored; failed job transcript after 7 days."""

    def test_done_job_transcript_cleared(self, db):
        """A 'done' job with a non-empty transcript should have it cleared."""
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        job = Job(
            kind="summary",
            status="done",
            title="Planning",
            meeting_date=now.date(),
            transcript="Alice: Let's go.\nBob: Agreed.",
            result={"summary": "Agreed to proceed."},
        )
        db.add(job)
        db.commit()

        logs = apply_retention(db, now)
        assert any("cleared transcripts" in line for line in logs)

        fresh = db.execute(select(Job).where(Job.id == job.id)).scalar_one()
        assert fresh.transcript is None

    def test_queued_job_transcript_preserved(self, db):
        """A queued job's transcript should not be touched."""
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        job = Job(
            kind="summary",
            status="queued",
            title="Planning",
            meeting_date=now.date(),
            transcript="Alice: Let's go.",
        )
        db.add(job)
        db.commit()

        apply_retention(db, now)

        fresh = db.execute(select(Job).where(Job.id == job.id)).scalar_one()
        assert fresh.transcript == "Alice: Let's go."

    def test_done_job_no_transcript_noop(self, db):
        """A done job without a transcript is a no-op."""
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        job = Job(
            kind="summary",
            status="done",
            title="Planning",
            meeting_date=now.date(),
            result={"summary": "Done."},
            transcript=None,
        )
        db.add(job)
        db.commit()

        logs = apply_retention(db, now)
        assert not any("cleared transcripts" in line for line in logs)

    def test_failed_job_transcript_preserved_before_7_days(self, db):
        """Failed job transcript is preserved one day before the 7-day limit."""
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        job = Job(
            kind="summary",
            status="failed",
            title="Old meeting",
            meeting_date=now.date() - timedelta(days=6),
            created_at=now - timedelta(days=6),
            transcript="Alice: We failed.",
        )
        db.add(job)
        db.commit()

        apply_retention(db, now)

        fresh = db.execute(select(Job).where(Job.id == job.id)).scalar_one()
        assert fresh.transcript == "Alice: We failed."

    def test_failed_job_transcript_deleted_after_7_days(self, db):
        """Failed job transcript is deleted one day after the 7-day limit."""
        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        job = Job(
            kind="summary",
            status="failed",
            title="Old meeting",
            meeting_date=now.date() - timedelta(days=8),
            created_at=now - timedelta(days=8),
            transcript="Alice: We failed.",
        )
        db.add(job)
        db.commit()

        logs = apply_retention(db, now)
        assert any("expired failed jobs" in line for line in logs)

        remaining = db.execute(select(Job).where(Job.id == job.id)).scalar_one_or_none()
        assert remaining is None


class TestSummaryRetention:
    """SPEC 8.2: summaries deleted after SUMMARY_RETENTION_DAYS."""

    def test_old_summary_deleted_after_retention(self, db, monkeypatch):
        """Summary one day past the retention limit is deleted."""
        monkeypatch.setenv("SUMMARY_RETENTION_DAYS", "180")
        get_settings.cache_clear()

        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        cutoff = now - timedelta(days=181)
        job = Job(
            kind="summary",
            status="done",
            title="Ancient meeting",
            meeting_date=now.date() - timedelta(days=300),
            result={"summary": "Long ago."},
            finished_at=cutoff,
        )
        db.add(job)
        db.commit()

        apply_retention(db, now)

        remaining = db.execute(select(Job).where(Job.id == job.id)).scalar_one_or_none()
        assert remaining is None

    def test_summary_within_retention_preserved(self, db, monkeypatch):
        """Summary one day within the retention limit is preserved."""
        monkeypatch.setenv("SUMMARY_RETENTION_DAYS", "180")
        get_settings.cache_clear()

        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        cutoff = now - timedelta(days=179)
        job = Job(
            kind="summary",
            status="done",
            title="Recent meeting",
            meeting_date=now.date() - timedelta(days=300),
            result={"summary": "Recent."},
            finished_at=cutoff,
        )
        db.add(job)
        db.commit()

        apply_retention(db, now)

        remaining = db.execute(select(Job).where(Job.id == job.id)).scalar_one()
        assert remaining is not None
        assert remaining.result is not None

    def test_summary_without_result_not_deleted(self, db, monkeypatch):
        """Job with no result is not deleted by summary retention."""
        monkeypatch.setenv("SUMMARY_RETENTION_DAYS", "180")
        get_settings.cache_clear()

        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        cutoff = now - timedelta(days=181)
        job = Job(
            kind="summary",
            status="failed",
            title="No result",
            meeting_date=now.date(),
            created_at=now - timedelta(days=1),
            result=None,
            finished_at=cutoff,
        )
        db.add(job)
        db.commit()

        apply_retention(db, now)

        remaining = db.execute(select(Job).where(Job.id == job.id)).scalar_one()
        assert remaining is not None


class TestDeadlineRetention:
    """SPEC 8.2: deadlines deleted after DEADLINE_RETENTION_DAYS from due_date."""

    def test_old_deadline_deleted_after_retention(self, db, monkeypatch):
        """Deadline one day past retention limit is deleted."""
        monkeypatch.setenv("DEADLINE_RETENTION_DAYS", "60")
        get_settings.cache_clear()

        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        due = now.date() - timedelta(days=61)
        deadline = Deadline(
            title="Ancient task",
            due_date=due,
        )
        db.add(deadline)
        db.commit()

        apply_retention(db, now)

        remaining = db.execute(
            select(Deadline).where(Deadline.id == deadline.id)
        ).scalar_one_or_none()
        assert remaining is None

    def test_recent_deadline_preserved(self, db, monkeypatch):
        """Deadline one day within retention limit is preserved."""
        monkeypatch.setenv("DEADLINE_RETENTION_DAYS", "60")
        get_settings.cache_clear()

        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        due = now.date() - timedelta(days=59)
        deadline = Deadline(
            title="Recent task",
            due_date=due,
        )
        db.add(deadline)
        db.commit()

        apply_retention(db, now)

        remaining = db.execute(select(Deadline).where(Deadline.id == deadline.id)).scalar_one()
        assert remaining is not None

    def test_today_deadline_preserved(self, db, monkeypatch):
        """Today's deadline is preserved."""
        monkeypatch.setenv("DEADLINE_RETENTION_DAYS", "60")
        get_settings.cache_clear()

        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        deadline = Deadline(
            title="Today's task",
            due_date=now.date(),
        )
        db.add(deadline)
        db.commit()

        apply_retention(db, now)

        remaining = db.execute(select(Deadline).where(Deadline.id == deadline.id)).scalar_one()
        assert remaining is not None


class TestPostLogRetention:
    """SPEC 8.2: post-log rows deleted after POST_LOG_RETENTION_DAYS."""

    def test_old_postlog_deleted_after_retention(self, db, monkeypatch):
        """Post-log row one day past retention limit is deleted."""
        monkeypatch.setenv("POST_LOG_RETENTION_DAYS", "180")
        get_settings.cache_clear()

        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        cutoff = now - timedelta(days=181)
        postlog = PostLog(
            kind="weekly",
            ref_key="weekly:2024-W01",
            status="sent",
            sent_at=cutoff,
        )
        db.add(postlog)
        db.commit()

        apply_retention(db, now)

        remaining = db.execute(select(PostLog).where(PostLog.id == postlog.id)).scalar_one_or_none()
        assert remaining is None

    def test_recent_postlog_preserved(self, db, monkeypatch):
        """Post-log row one day within retention limit is preserved."""
        monkeypatch.setenv("POST_LOG_RETENTION_DAYS", "180")
        get_settings.cache_clear()

        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        cutoff = now - timedelta(days=179)
        postlog = PostLog(
            kind="deadline",
            ref_key="deadline:1:2025-01-16:2",
            status="sent",
            sent_at=cutoff,
        )
        db.add(postlog)
        db.commit()

        apply_retention(db, now)

        remaining = db.execute(select(PostLog).where(PostLog.id == postlog.id)).scalar_one()
        assert remaining is not None

    def test_failed_postlog_preserved(self, db, monkeypatch):
        """Failed post-log rows are never deleted by retention."""
        monkeypatch.setenv("POST_LOG_RETENTION_DAYS", "180")
        get_settings.cache_clear()

        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)
        cutoff = now - timedelta(days=365)
        postlog = PostLog(
            kind="weekly",
            ref_key="weekly:2024-W01",
            status="failed",
            sent_at=cutoff,
        )
        db.add(postlog)
        db.commit()

        apply_retention(db, now)

        remaining = db.execute(select(PostLog).where(PostLog.id == postlog.id)).scalar_one()
        assert remaining is not None


class TestApplyRetentionIntegration:
    """Integration: all rules in a single call."""

    def test_all_rules_together(self, db, monkeypatch):
        """All retention rules fire in a single call."""
        monkeypatch.setenv("SUMMARY_RETENTION_DAYS", "180")
        monkeypatch.setenv("DEADLINE_RETENTION_DAYS", "60")
        monkeypatch.setenv("POST_LOG_RETENTION_DAYS", "180")
        get_settings.cache_clear()

        now = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)

        # Done job with transcript (no result, so only transcript clearing applies)
        done_job = Job(
            kind="summary",
            status="done",
            title="Done",
            meeting_date=now.date(),
            transcript=" transcript",
            finished_at=now - timedelta(days=300),
        )
        db.add(done_job)

        # Failed job > 7 days old (should be deleted)
        old_failed = Job(
            kind="summary",
            status="failed",
            title="Old failed",
            meeting_date=now.date() - timedelta(days=8),
            created_at=now - timedelta(days=8),
            transcript="failed",
        )
        db.add(old_failed)

        # Old summary with result (should be deleted)
        old_summary = Job(
            kind="summary",
            status="done",
            title="Old summary",
            meeting_date=now.date() - timedelta(days=200),
            result={"summary": "old."},
            finished_at=now - timedelta(days=181),
        )
        db.add(old_summary)

        # Old deadline (should be deleted)
        old_dl = Deadline(
            title="Old deadline",
            due_date=now.date() - timedelta(days=61),
        )
        db.add(old_dl)

        # Old post-log (should be deleted)
        old_pl = PostLog(
            kind="weekly",
            ref_key="weekly:2024-W01",
            status="sent",
            sent_at=now - timedelta(days=181),
        )
        db.add(old_pl)

        db.commit()

        apply_retention(db, now)

        # Done job transcript cleared
        fresh_done = db.execute(select(Job).where(Job.id == done_job.id)).scalar_one()
        assert fresh_done.transcript is None

        # Old failed job deleted
        assert db.execute(select(Job).where(Job.id == old_failed.id)).scalar_one_or_none() is None

        # Old summary deleted
        assert db.execute(select(Job).where(Job.id == old_summary.id)).scalar_one_or_none() is None

        # Old deadline deleted
        assert (
            db.execute(select(Deadline).where(Deadline.id == old_dl.id)).scalar_one_or_none()
            is None
        )

        # Old post-log deleted
        assert (
            db.execute(select(PostLog).where(PostLog.id == old_pl.id)).scalar_one_or_none() is None
        )
