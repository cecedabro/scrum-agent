"""Retention rules: delete expired data (SPEC 8.1-8.2).

Usage: called from ``app.tick.run_tick``.
"""

from __future__ import annotations

import datetime
import logging

from sqlalchemy import String, cast, delete, update
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Deadline, Job, PostLog

logger = logging.getLogger(__name__)


def apply_retention(session: Session, now: datetime.datetime) -> list[str]:
    """Apply all retention rules.

    - Clear transcripts of completed jobs (SPEC 8.1).
    - Delete transcripts of failed jobs older than 7 days (SPEC 8.1).
    - Delete summary Jobs older than SUMMARY_RETENTION_DAYS (SPEC 8.2).
    - Delete deadlines older than DEADLINE_RETENTION_DAYS from their date (SPEC 8.2).
    - Delete post-log rows older than POST_LOG_RETENTION_DAYS (SPEC 8.2).

    Returns a list of log strings describing what was deleted.
    """
    log_lines: list[str] = []
    settings = get_settings()

    # SPEC 8.1: clear transcript of every completed job
    cleared = session.execute(
        update(Job)
        .where(
            Job.status == "done",
            Job.transcript.isnot(None),
            Job.transcript != "",
        )
        .values(transcript=None)
    )
    cleared_count = cleared.rowcount  # type: ignore[attr-defined]
    if cleared_count:
        log_lines.append(f"retention cleared transcripts for {cleared_count} done jobs")

    # SPEC 8.1: delete transcript of failed jobs older than 7 days
    seven_days_ago = now - datetime.timedelta(days=7)
    expired_failed = session.execute(
        delete(Job).where(
            Job.status == "failed",
            Job.created_at <= seven_days_ago,
        )
    )
    failed_count = expired_failed.rowcount  # type: ignore[attr-defined]
    if failed_count:
        log_lines.append(f"retention deleted {failed_count} expired failed jobs")

    # SPEC 8.2: delete summaries (Jobs with result) older than SUMMARY_RETENTION_DAYS
    summary_cutoff = now - datetime.timedelta(days=settings.SUMMARY_RETENTION_DAYS)
    old_summaries = session.execute(
        delete(Job).where(
            Job.kind == "summary",
            Job.result.isnot(None),
            cast(Job.result, String) != "null",
            Job.finished_at <= summary_cutoff,
        )
    )
    summary_count = old_summaries.rowcount  # type: ignore[attr-defined]
    if summary_count:
        log_lines.append(f"retention deleted {summary_count} old summaries")

    # SPEC 8.2: delete deadlines older than DEADLINE_RETENTION_DAYS from due_date
    deadline_cutoff = (now - datetime.timedelta(days=settings.DEADLINE_RETENTION_DAYS)).date()
    old_deadlines = session.execute(
        delete(Deadline).where(
            Deadline.due_date <= deadline_cutoff,
        )
    )
    deadline_count = old_deadlines.rowcount  # type: ignore[attr-defined]
    if deadline_count:
        log_lines.append(f"retention deleted {deadline_count} old deadlines")

    # SPEC 8.2: delete post-log rows older than POST_LOG_RETENTION_DAYS
    postlog_cutoff = now - datetime.timedelta(days=settings.POST_LOG_RETENTION_DAYS)
    old_postlog = session.execute(
        delete(PostLog).where(
            PostLog.status == "sent",
            PostLog.sent_at <= postlog_cutoff,
        )
    )
    postlog_count = old_postlog.rowcount  # type: ignore[attr-defined]
    if postlog_count:
        log_lines.append(f"retention deleted {postlog_count} old post_log rows")

    return log_lines
