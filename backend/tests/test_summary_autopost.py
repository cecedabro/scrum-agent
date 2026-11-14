"""Tests for auto-post summary cards after done jobs (SPEC 7.8, TASK T33).

Covers:
- auto-post ON  → card posted once, ``posted_at`` set
- auto-post OFF → nothing posted
- Teams failure → job still ``done``, ``posted_at`` empty
"""

from datetime import datetime
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import select

from app.models import AppSetting, Job, PostLog
from app.summarize import Summary
from app.worker import run_once

_FAKE_WEBHOOK_URL = "https://outlook.office.com/webhook/fake"


@pytest.fixture(autouse=True)
def _fake_teams_url(monkeypatch):
    """Ensure TEAMS_WEBHOOK_URL is set for all tests and clear cached settings."""
    monkeypatch.setenv("TEAMS_WEBHOOK_URL", _FAKE_WEBHOOK_URL)
    from app.config import get_settings

    get_settings.cache_clear()


@pytest.fixture()
def auto_post_job(db):
    """Create a queued summary job with settings row."""
    setting = AppSetting(key="summary_auto_post", value="true")
    db.add(setting)
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


@pytest.fixture()
def auto_post_disabled(db):
    """Create a queued summary job with auto-post disabled."""
    setting = AppSetting(key="summary_auto_post", value="false")
    db.add(setting)
    job = Job(
        kind="summary",
        status="queued",
        title="Retrospective",
        meeting_date=datetime(2024, 2, 1).date(),
        transcript="Carol: What went well?\nDave: The tests.",
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


class TestAutoPostOn:
    """Auto-post is enabled: card should be posted once and posted_at set."""

    @patch("app.worker.summarize")
    def test_summary_card_posted_once_and_posted_at_set(self, mock_summarize, db, auto_post_job):
        """When auto-post is on, the card is sent and posted_at is set."""
        mock_summarize.return_value = Summary(
            summary="De samenvatting van de meeting.",
            decisions=["Backend afronden"],
            action_items=[],
            open_questions=[],
        )

        mock_response = httpx.Response(202, json={})
        mock_transport = httpx.MockTransport(lambda r: mock_response)
        teams_client = httpx.Client(transport=mock_transport)

        try:
            result = run_once(db, datetime.utcnow(), teams_client=teams_client)
        finally:
            teams_client.close()

        assert result == "done"

        job = db.execute(select(Job).where(Job.id == auto_post_job.id)).scalar_one()
        assert job.posted_at is not None

        post_log = db.execute(
            select(PostLog).where(PostLog.ref_key == f"summary:{auto_post_job.id}")
        ).scalar_one()
        assert post_log.status == "sent"

    @patch("app.worker.summarize")
    def test_post_not_called_twice(self, mock_summarize, db, auto_post_job):
        """Running run_once a second time should not post again (ref_key already sent)."""
        mock_summarize.return_value = Summary(
            summary="Samenvatting.",
            decisions=[],
            action_items=[],
            open_questions=[],
        )

        mock_response = httpx.Response(202, json={})
        mock_transport = httpx.MockTransport(lambda r: mock_response)
        teams_client = httpx.Client(transport=mock_transport)

        try:
            now = datetime.utcnow()

            # First run: should post.
            result1 = run_once(db, now, teams_client=teams_client)
            assert result1 == "done"

            # Second run: no queued job left, returns idle.
            result2 = run_once(db, now)
            assert result2 == "idle"
        finally:
            teams_client.close()

        post_logs = (
            db.execute(select(PostLog).where(PostLog.ref_key == f"summary:{auto_post_job.id}"))
            .scalars()
            .all()
        )
        assert len(post_logs) == 1


class TestAutoPostOff:
    """Auto-post is disabled: nothing should be posted."""

    @patch("app.worker.summarize")
    def test_nothing_posted_when_disabled(self, mock_summarize, db, auto_post_disabled):
        """When auto-post is off, no card is sent and no PostLog row is created."""
        mock_summarize.return_value = Summary(
            summary="Samenvatting retro.",
            decisions=[],
            action_items=[],
            open_questions=[],
        )

        run_once(db, datetime.utcnow())

        job = db.execute(select(Job).where(Job.id == auto_post_disabled.id)).scalar_one()
        assert job.status == "done"
        assert job.posted_at is None

        post_logs = (
            db.execute(select(PostLog).where(PostLog.ref_key == f"summary:{auto_post_disabled.id}"))
            .scalars()
            .all()
        )
        assert len(post_logs) == 0


class TestTeamsFailure:
    """Teams failures must not break the done state."""

    @patch("app.worker.summarize")
    def test_retryable_failure_job_still_done(self, mock_summarize, db, auto_post_job):
        """A retryable Teams failure leaves the job done but posted_at empty."""
        mock_summarize.return_value = Summary(
            summary="Samenvatting.",
            decisions=[],
            action_items=[],
            open_questions=[],
        )

        mock_response = httpx.Response(503, json={"error": "Service unavailable"})
        mock_transport = httpx.MockTransport(lambda r: mock_response)
        teams_client = httpx.Client(transport=mock_transport)

        try:
            result = run_once(db, datetime.utcnow(), teams_client=teams_client)
        finally:
            teams_client.close()

        assert result == "done"

        job = db.execute(select(Job).where(Job.id == auto_post_job.id)).scalar_one()
        assert job.posted_at is None

        post_log = db.execute(
            select(PostLog).where(PostLog.ref_key == f"summary:{auto_post_job.id}")
        ).scalar_one()
        assert post_log.status == "retryable"

    @patch("app.worker.summarize")
    def test_permanent_failure_job_still_done(self, mock_summarize, db, auto_post_job):
        """A permanent Teams failure (4xx) leaves the job done but posted_at empty."""
        mock_summarize.return_value = Summary(
            summary="Samenvatting.",
            decisions=[],
            action_items=[],
            open_questions=[],
        )

        mock_response = httpx.Response(401, json={"error": "Unauthorized"})
        mock_transport = httpx.MockTransport(lambda r: mock_response)
        teams_client = httpx.Client(transport=mock_transport)

        try:
            result = run_once(db, datetime.utcnow(), teams_client=teams_client)
        finally:
            teams_client.close()

        assert result == "done"

        job = db.execute(select(Job).where(Job.id == auto_post_job.id)).scalar_one()
        assert job.posted_at is None

        post_log = db.execute(
            select(PostLog).where(PostLog.ref_key == f"summary:{auto_post_job.id}")
        ).scalar_one()
        assert post_log.status == "permanent"

    @patch("app.worker.summarize")
    def test_teams_exception_does_not_break_done(self, mock_summarize, db, auto_post_job):
        """A network exception during posting must not break the done state."""
        mock_summarize.return_value = Summary(
            summary="Samenvatting.",
            decisions=[],
            action_items=[],
            open_questions=[],
        )

        def raise_error(request):
            raise httpx.ConnectError("connection refused")

        mock_transport = httpx.MockTransport(raise_error)
        teams_client = httpx.Client(transport=mock_transport)

        try:
            result = run_once(db, datetime.utcnow(), teams_client=teams_client)
        finally:
            teams_client.close()

        assert result == "done"

        job = db.execute(select(Job).where(Job.id == auto_post_job.id)).scalar_one()
        assert job.posted_at is None
