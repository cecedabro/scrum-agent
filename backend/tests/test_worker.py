"""Tests for ``app.worker`` (TASK T30)."""

from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models import Job
from app.summarize import Summary, SummaryError
from app.worker import run_once


@pytest.fixture()
def sample_job(db):
    """Create a queued job for testing."""
    job = Job(
        kind="summary",
        status="queued",
        title="Sprint planning",
        meeting_date=datetime(2024, 1, 15).date(),
        transcript="Alice: We need to finish the backend.\nBob: I agree.",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


class TestRunOnce:
    """Tests for the worker ``run_once`` function."""

    @patch("app.worker.summarize")
    def test_idle_no_jobs(self, mock_summarize, db):
        """When there are no queued jobs, return 'idle'."""
        result = run_once(db, datetime.utcnow())
        assert result == "idle"
        mock_summarize.assert_not_called()

    @patch("app.worker.summarize")
    def test_success_stores_result(self, mock_summarize, db, sample_job):
        """Successful summarization should update job to 'done'."""
        mock_result = Summary(
            summary="De samenvatting van de meeting.",
            decisions=["Backend afronden"],
            action_items=[],
            open_questions=[],
        )
        mock_summarize.return_value = mock_result

        result = run_once(db, datetime.utcnow())
        assert result == "done"

        job = db.execute(select(Job).where(Job.id == sample_job.id)).scalar_one()
        assert job.status == "done"
        assert job.result is not None
        assert job.result["summary"] == "De samenvatting van de meeting."
        assert job.transcript is None
        assert job.finished_at is not None

    @patch("app.worker.summarize")
    def test_failure_retries(self, mock_summarize, db, sample_job):
        """A single failure should set job back to 'queued' for retry."""
        mock_summarize.side_effect = SummaryError("LLM error")

        result = run_once(db, datetime.utcnow())
        assert result == "retry"

        job = db.execute(select(Job).where(Job.id == sample_job.id)).scalar_one()
        assert job.status == "queued"
        assert job.attempts == 1
        assert "LLM error" in job.error

    @patch("app.worker.summarize")
    def test_failure_three_attempts_fails(self, mock_summarize, db, sample_job):
        """After 3 failed attempts, job should be permanently 'failed'."""
        # First attempt
        mock_summarize.side_effect = SummaryError("LLM error 1")
        result1 = run_once(db, datetime.utcnow())
        assert result1 == "retry"

        # Second attempt
        mock_summarize.side_effect = SummaryError("LLM error 2")
        result2 = run_once(db, datetime.utcnow())
        assert result2 == "retry"

        # Third attempt
        mock_summarize.side_effect = SummaryError("LLM error 3")
        result3 = run_once(db, datetime.utcnow())
        assert result3 == "retry"

        job = db.execute(select(Job).where(Job.id == sample_job.id)).scalar_one()
        assert job.status == "failed"
        assert job.attempts == 3
        assert job.error == "Samenvatting mislukt na 3 pogingen"
        assert job.finished_at is not None

    @patch("app.worker.summarize")
    def test_success_clears_transcript(self, mock_summarize, db, sample_job):
        """On success, the transcript should be cleared."""
        mock_result = Summary(
            summary="Samenvatting.",
            decisions=[],
            action_items=[],
            open_questions=[],
        )
        mock_summarize.return_value = mock_result

        run_once(db, datetime.utcnow())

        job = db.execute(select(Job).where(Job.id == sample_job.id)).scalar_one()
        assert job.transcript is None

    @patch("app.worker.summarize")
    def test_attempts_increment(self, mock_summarize, db, sample_job):
        """Each attempt should increment the attempts counter."""
        mock_summarize.side_effect = SummaryError("Error")

        run_once(db, datetime.utcnow())
        job = db.execute(select(Job).where(Job.id == sample_job.id)).scalar_one()
        assert job.attempts == 1

        run_once(db, datetime.utcnow())
        job = db.execute(select(Job).where(Job.id == sample_job.id)).scalar_one()
        assert job.attempts == 2

    @patch("app.worker.summarize")
    def test_successful_job_sets_started_at(self, mock_summarize, db, sample_job):
        """The started_at field should be set when the job is processed."""
        mock_result = Summary(
            summary="Samenvatting.",
            decisions=[],
            action_items=[],
            open_questions=[],
        )
        mock_summarize.return_value = mock_result

        now = datetime.utcnow()
        run_once(db, now)

        job = db.execute(select(Job).where(Job.id == sample_job.id)).scalar_one()
        assert job.started_at is not None
