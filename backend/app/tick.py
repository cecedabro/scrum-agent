"""Cron tick: reminder posting and retention (SPEC 6.6).

Usage: python -m app.tick

Exits 0 on success, 1 when the database is unreachable.
"""

from __future__ import annotations

import datetime
import logging
import sys
from typing import TYPE_CHECKING, Any

from sqlalchemy.orm import Session

from app.clock import now_utc
from app.db import get_engine, session_factory
from app.retention import apply_retention
from app.schedule import due_posts
from app.settings import load as load_settings
from app.teams import send_once

if TYPE_CHECKING:
    import httpx

logger = logging.getLogger(__name__)


def _deadlines_to_dicts(session: Session) -> list[dict[str, Any]]:
    """Return upcoming deadlines as simple dicts for schedule.py."""
    from app.deadlines import upcoming

    items = upcoming(session)
    return [
        {
            "id": dl.id,
            "title": dl.title,
            "due_date": dl.due_date,
            "due_time": dl.due_time,
            "note": dl.note,
        }
        for dl in items
    ]


def run_tick(
    session: Session,
    now: datetime.datetime | None = None,
    client: httpx.Client | None = None,
) -> list[str]:
    """Run one tick: load settings, find due posts, send them, apply retention.

    Returns a list of log strings (one per post/action).
    """
    now = now or now_utc()
    log_lines: list[str] = []

    # Load settings and deadlines
    settings = load_settings(session)
    deadlines = _deadlines_to_dicts(session)

    # Get due posts
    posts = due_posts(now, settings, deadlines)

    # Send each due post (covers new posts and retries of failed rows)
    for post in posts:
        status = send_once(session, post.kind, post.ref_key, post.card, client=client)
        log_lines.append(f"{post.kind} {post.ref_key} {status}")

    # Apply retention: transcripts, summaries, deadlines, post-logs (SPEC 8)
    retention_log = apply_retention(session, now)
    log_lines.extend(retention_log)

    session.commit()

    return log_lines


def main() -> int:
    """CLI entrypoint. Exits 0 on success, 1 if DB is unreachable."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    # Check DB reachability
    engine = get_engine()
    try:
        engine.connect().close()
    except Exception:
        logger.error("database unreachable")
        return 1

    session = session_factory()()
    try:
        log_lines = run_tick(session)
        for line in log_lines:
            logger.info(line)
        logger.info("tick done")
        return 0
    except Exception:
        logger.exception("tick failed")
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
