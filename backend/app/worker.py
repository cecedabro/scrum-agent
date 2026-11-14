"""Worker that processes queued summary jobs (TASK T30).

``run_once(session, now, llm_client, teams_client) -> str`` claims one
queued *Job*, runs ``summarize()``, and updates the job status.

Return values: ``"idle"``, ``"done"``, ``"retry"``, ``"failed"``.
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Job
from app.summarize import SummaryError, summarize


def run_once(
    session: Session,
    now: Any,
    llm_client: httpx.Client | None = None,
    teams_client: httpx.Client | None = None,
) -> str:
    """Process one queued job and return what happened.

    Returns ``"idle"`` when no job was available,
    ``"done"`` when the job succeeded,
    ``"retry"`` when it failed but should be retried,
    ``"failed"`` when it exhausted all attempts.
    """
    # Claim one queued job (SPEC 7.7: skip locked).
    stmt = (
        select(Job)
        .where(Job.status == "queued")
        .order_by(Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = session.execute(stmt).scalar_one_or_none()

    if job is None:
        return "idle"

    # Mark as running.
    job.status = "running"
    job.started_at = now
    job.attempts += 1
    session.flush()

    try:
        # Run the summarization.
        if job.transcript is None:
            raise SummaryError("Transcript is empty")
        result = summarize(job.transcript, client=llm_client)
        result_dict = result.model_dump()

        # Success path.
        job.result = result_dict
        job.transcript = None
        job.status = "done"
        job.finished_at = now
        session.commit()

        return "done"

    except SummaryError as exc:
        # Failure path.
        _handle_failure(session, job, now, str(exc))
        return "retry"


def _handle_failure(
    session: Session, job: Job, now: Any, error_msg: str
) -> None:
    """Mark a job as failed or retryable."""
    job.error = error_msg

    if job.attempts >= 3:
        job.status = "failed"
        job.finished_at = now
        job.error = "Samenvatting mislukt na 3 pogingen"
    else:
        job.status = "queued"

    session.commit()
