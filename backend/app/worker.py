"""Worker that processes queued summary jobs (TASK T30, T31).

``run_once(session, now, llm_client, teams_client) -> str`` claims one
queued *Job*, runs ``summarize()``, and updates the job status.

Return values: ``"idle"``, ``"model_offline"``, ``"done"``, ``"retry"``,
``"failed"``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.llm import is_up
from app.models import AppState, Job
from app.summarize import SummaryError, summarize

RUN_STUCK_THRESHOLD = timedelta(minutes=30)


def _store_model_status(session: Session, up: bool, now: datetime) -> None:
    """Store model health status in app_state."""
    row = session.query(AppState).filter(AppState.key == "model_status").first()
    value: dict[str, Any] = {
        "up": up,
        "checked_at": now.isoformat(),
        "last_up_at": now.isoformat() if up else None,
    }
    if row is None:
        row = AppState(key="model_status", value=value)
        session.add(row)
    else:
        row.value = value
    session.flush()


def run_once(
    session: Session,
    now: Any,
    llm_client: httpx.Client | None = None,
    teams_client: httpx.Client | None = None,
) -> str:
    """Process one queued job and return what happened.

    Returns ``"idle"`` when no job was available,
    ``"model_offline"`` when the LLM is unreachable,
    ``"done"`` when the job succeeded,
    ``"retry"`` when it failed but should be retried,
    ``"failed"`` when it exhausted all attempts.
    """
    # Check model health (SPEC 7.4).
    up = is_up()
    _store_model_status(session, up, now)

    if not up:
        return "model_offline"

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


def reset_stuck(session: Session, now: datetime) -> None:
    """Reset jobs running longer than 30 minutes back to queued (SPEC 7.7)."""
    cutoff = now - RUN_STUCK_THRESHOLD
    stuck = (
        session.query(Job)
        .filter(Job.status == "running", Job.started_at < cutoff)
        .all()
    )
    for job in stuck:
        job.status = "queued"
        job.started_at = None
    session.commit()


def main() -> None:
    """Main loop: reset stuck jobs, then process one job per iteration."""
    from app.clock import now_utc
    from app.db import session_factory

    reset_stuck(session_factory()(), now_utc())

    while True:
        result = run_once(session_factory()(), now_utc())
        if result in ("idle", "model_offline"):
            import time
            time.sleep(60)
