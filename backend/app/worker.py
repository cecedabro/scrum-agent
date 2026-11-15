"""Worker that processes queued summary jobs (TASK T30, T31).

``run_once(session, now, llm_client, teams_client) -> str`` claims one
queued *Job*, runs ``summarize()``, and updates the job status.

Return values: ``"idle"``, ``"model_offline"``, ``"done"``, ``"retry"``,
``"failed"``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ask import QuestionError, ask
from app.cards import question_card, summary_card
from app.config import get_settings
from app.llm import is_up
from app.models import AppState, Job
from app.settings import load as load_settings
from app.summarize import SummaryError, summarize
from app.teams import send_once

logger = logging.getLogger(__name__)

RUN_STUCK_THRESHOLD = timedelta(minutes=30)
WAKE_COOLDOWN = timedelta(minutes=30)


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


# ---------------------------------------------------------------------------
# Optional PC wake (SPEC 7.9)
# ---------------------------------------------------------------------------

_LAST_WAKE_KEY = "last_wake"


def _store_last_wake(session: Session, now: datetime) -> None:
    """Persist the last wake attempt time in app_state."""
    row = session.query(AppState).filter(AppState.key == _LAST_WAKE_KEY).first()
    value = now.isoformat()
    if row is None:
        row = AppState(key=_LAST_WAKE_KEY, value=value)
        session.add(row)
    else:
        row.value = value
    session.flush()


def _should_wake(session: Session, now: datetime) -> bool:
    """Return True when a wake call is warranted (cooldown expired)."""
    row = session.query(AppState).filter(AppState.key == _LAST_WAKE_KEY).first()
    if row is None:
        return True
    last = datetime.fromisoformat(row.value)  # type: ignore[arg-type]
    return (now - last) >= WAKE_COOLDOWN


def _wake(session: Session, now: Any, *, client: httpx.Client | None = None) -> None:
    """POST to the wake endpoint when configured and cooldown permits."""
    settings = get_settings()
    waker_url = settings.WAKER_URL
    waker_token = settings.WAKER_TOKEN
    if not waker_url or not waker_token:
        return
    if not _should_wake(session, now):
        return
    local_client = client or httpx.Client()
    try:
        local_client.post(
            f"{waker_url}/wake",
            headers={"X-Waker-Token": waker_token},
            timeout=5,
        )
    except Exception:
        logger.exception("Wake call failed")
    finally:
        if client is None:
            local_client.close()
    _store_last_wake(session, now)


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
        _wake(session, now)
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
        if job.kind == "question":
            return _process_question(session, job, now, llm_client, teams_client)

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

        # Auto-post summary card (SPEC 7.8).
        try:
            settings = load_settings(session)
            if settings.summary_auto_post:
                post_status = send_once(
                    session,
                    kind="summary",
                    ref_key=f"summary:{job.id}",
                    card=summary_card(job),
                    client=teams_client,
                    now=now,
                )
                if post_status == "sent":
                    job.posted_at = now
        except Exception:
            logger.exception("Auto-post failed for job %s", job.id)

        session.commit()

        return "done"

    except SummaryError as exc:
        # Failure path.
        _handle_failure(session, job, now, str(exc))
        return "retry"


def _process_question(
    session: Session,
    job: Job,
    now: Any,
    llm_client: httpx.Client | None,
    teams_client: httpx.Client | None,
) -> str:
    """Process a question job: call the LLM, post the answer, update job."""
    # Parse context from transcript (JSON stored by web app).
    deadline_title = ""
    last_summary = ""
    if job.transcript:
        try:
            ctx = json.loads(job.transcript)
            deadline_title = ctx.get("deadline_title", "")
            last_summary = ctx.get("last_summary", "")
        except (json.JSONDecodeError, TypeError):
            pass

    try:
        answer = ask(
            job.title,
            deadline_title=deadline_title,
            last_summary=last_summary,
            client=llm_client,
        )
    except QuestionError as exc:
        _handle_failure(session, job, now, str(exc))
        return "retry"

    job.status = "done"
    job.result = {"answer": answer}
    job.finished_at = now

    # Always post question cards (not subject to auto-post setting).
    try:
        send_once(
            session,
            kind="question",
            ref_key=f"question:{job.id}",
            card=question_card(job.title, answer),
            client=teams_client,
            now=now,
        )
        job.posted_at = now
    except Exception:
        logger.exception("Post failed for question job %s", job.id)

    session.commit()
    return "done"


def _handle_failure(session: Session, job: Job, now: Any, error_msg: str) -> None:
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
    stuck = session.query(Job).filter(Job.status == "running", Job.started_at < cutoff).all()
    for job in stuck:
        job.status = "queued"
        job.started_at = None
    session.commit()


def main() -> None:
    """Main loop: reset stuck jobs, then process one job per iteration.

    Each iteration uses its own session, closed afterwards. An unexpected error is logged
    and retried after a pause, so a database or network blip does not stop the worker.
    """
    import logging
    import time

    from app.clock import now_utc
    from app.db import session_factory

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("worker")
    log.info("worker started")

    with session_factory()() as session:
        reset_stuck(session, now_utc())

    while True:
        try:
            with session_factory()() as session:
                result = run_once(session, now_utc())
        except Exception:
            log.exception("worker iteration failed")
            result = "error"
        if result != "idle":
            log.info("worker: %s", result)
        if result in ("idle", "model_offline", "error"):
            time.sleep(60)


if __name__ == "__main__":
    main()
