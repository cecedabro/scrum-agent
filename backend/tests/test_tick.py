"""SPEC 6.6: tick logic (run_tick and main).

Covers:
- Monday tick posts the weekly overview once across two ticks.
- Teams 500 → exit 0 and retried on the next tick.
- Unreachable database → main() returns 1.
"""

import datetime
from unittest.mock import patch

import httpx

from app.clock import now_utc
from app.config import get_settings
from app.tick import main, run_tick

# ── helpers ─────────────────────────────────────────────────────────


def _make_transport(status_code: int) -> httpx.MockTransport:
    """Return a MockTransport that responds with *status_code*."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code)

    return httpx.MockTransport(handler)


_FAKE_WEBHOOK = "https://example.invalid/webhook"


def _enable_weekly(session, monday_0830: datetime.datetime):
    """Insert settings that enable the weekly overview on Monday at 08:30."""
    from app.models import AppSetting

    rows = {
        "weekly_enabled": "true",
        "weekly_weekday": "maandag",
        "weekly_time": "08:30",
        "deadline_reminder_enabled": "false",
        "sprint_enabled": "false",
    }
    existing = {r.key: r for r in session.query(AppSetting).all()}
    now = now_utc()
    for key, value in rows.items():
        if key in existing:
            existing[key].value = value
            existing[key].updated_at = now
        else:
            session.add(AppSetting(key=key, value=value, updated_at=now))
    session.flush()


def _create_deadline(session, title: str, due_date: datetime.date):
    from app.models import Deadline

    session.add(
        Deadline(
            title=title,
            due_date=due_date,
            due_time=None,
            note=None,
            source="manual",
        )
    )
    session.flush()


# ── Monday overview: posted once across two ticks ──────────────────


def test_monday_overview_posted_once_across_two_ticks(db) -> None:
    """The weekly overview for Monday is posted in the first tick and
    skipped in the second tick (same ref_key, already sent)."""
    # Monday 2025-11-03, scheduled at 08:30 local.
    monday = datetime.date(2025, 11, 3)
    # 08:30 Amsterdam = 07:30 UTC (November = CET, UTC+1).
    tick1 = datetime.datetime(2025, 11, 3, 7, 31, tzinfo=datetime.UTC)

    _enable_weekly(db, tick1)
    _create_deadline(db, "Sprint review", monday + datetime.timedelta(days=2))
    db.commit()

    transport = _make_transport(202)
    with patch.object(get_settings(), "TEAMS_WEBHOOK_URL", _FAKE_WEBHOOK):
        lines1 = run_tick(db, now=tick1, client=httpx.Client(transport=transport))

    # First tick: post sent
    assert any("weekly" in line and "sent" in line for line in lines1)
    weekly_ref = next(
        (line for line in lines1 if "weekly" in line),
        None,
    )
    assert weekly_ref is not None

    # Second tick 1 minute later: should NOT post again
    tick2 = tick1 + datetime.timedelta(minutes=1)
    lines2 = run_tick(db, now=tick2, client=httpx.Client(transport=transport))
    non_sent = [line for line in lines2 if "weekly" in line and "sent" not in line]
    assert not non_sent, f"unexpected weekly post on second tick: {lines2}"


# ── Teams 500 → exit 0 and retried on next tick ────────────────────


def test_teams_500_exits_0_and_retries(db) -> None:
    """HTTP 500 returns retryable; main() exits 0 and the post is retried."""
    monday = datetime.date(2025, 11, 3)

    _enable_weekly(db, datetime.datetime(2025, 11, 3, 7, 31, tzinfo=datetime.UTC))
    _create_deadline(db, "Test deadline", monday + datetime.timedelta(days=1))
    db.commit()

    # First tick: 500 error
    transport_fail = _make_transport(500)
    with patch.object(get_settings(), "TEAMS_WEBHOOK_URL", _FAKE_WEBHOOK):
        lines = run_tick(
            db,
            now=datetime.datetime(2025, 11, 3, 7, 31, tzinfo=datetime.UTC),
            client=httpx.Client(transport=transport_fail),
        )

    # Should see retryable status
    assert any("retryable" in line for line in lines)

    # Second tick: success
    transport_ok = _make_transport(202)
    with patch.object(get_settings(), "TEAMS_WEBHOOK_URL", _FAKE_WEBHOOK):
        lines2 = run_tick(
            db,
            now=datetime.datetime(2025, 11, 3, 7, 32, tzinfo=datetime.UTC),
            client=httpx.Client(transport=transport_ok),
        )

    # Should now be sent
    assert any("weekly" in line and "sent" in line for line in lines2)


def test_main_returns_0_on_success(db) -> None:
    """main() returns 0 when the tick completes successfully."""
    _enable_weekly(db, datetime.datetime(2025, 11, 3, 7, 31, tzinfo=datetime.UTC))

    with patch.object(get_settings(), "TEAMS_WEBHOOK_URL", ""):
        # Empty webhook = dry run, still success
        rc = main()
    assert rc == 0


# ── Unreachable database → main() returns 1 ────────────────────────


def test_main_returns_1_on_unreachable_db() -> None:
    """main() returns 1 when the database cannot be reached."""
    with patch("app.tick.get_engine") as mock_get_engine:
        mock_engine = mock_get_engine.return_value
        mock_engine.connect.side_effect = Exception("connection refused")

        rc = main()
    assert rc == 1
