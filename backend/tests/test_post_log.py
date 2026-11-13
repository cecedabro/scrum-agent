"""SPEC 5.3–5.4: send_once post-log logic.

Tests send_once(session, kind, ref_key, card, *, client=None, now=None):
- skip when already sent
- dry_run when no webhook URL
- skip when attempts >= 5 or permanent
- post and record (ok, retryable, permanent)
- retryable increments attempts; permanent does not retry
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import httpx
import pytest
from sqlalchemy import select

from app.clock import now_utc
from app.config import get_settings
from app.models import PostLog
from app.teams import send_once

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ── helpers ───────────────────────────────────────────────────────────


def _make_transport(
    status_code: int, body: str = "", headers: dict | None = None
) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        resp_headers = headers or {"Content-Type": "application/json"}
        return httpx.Response(status_code, content=body, headers=resp_headers)

    return httpx.MockTransport(handler)


_WEBHOOK = "https://example.invalid/webhook"


def _now(ago_seconds: int = 0) -> datetime:
    return datetime.now(UTC) - timedelta(seconds=ago_seconds)


# ── successful send ───────────────────────────────────────────────────


def test_send_once_202_returns_sent(db: Session) -> None:
    """HTTP 202 → row status 'sent', sent_at set, returns 'sent'."""
    transport = _make_transport(202)
    card = {"type": "AdaptiveCard", "body": []}
    now = _now()

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        result = send_once(
            db,
            "reminder",
            "dl:1:2026-11-20",
            card,
            client=httpx.Client(transport=transport),
            now=now,
        )

    assert result == "sent"
    row = db.execute(
        select(PostLog).where(PostLog.ref_key == "dl:1:2026-11-20")
    ).scalar_one_or_none()
    assert row is not None
    assert row.status == "sent"
    assert row.sent_at == now
    assert row.attempts == 0


def test_send_once_200_returns_sent(db: Session) -> None:
    """HTTP 200 → also counts as ok."""
    transport = _make_transport(200)
    card = {"type": "AdaptiveCard", "body": []}

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        result = send_once(
            db,
            "reminder",
            "dl:2:2026-11-20",
            card,
            client=httpx.Client(transport=transport),
        )

    assert result == "sent"
    row = db.scalar(select(PostLog).where(PostLog.ref_key == "dl:2:2026-11-20"))
    assert row.status == "sent"


# ── retryable → increment attempts ────────────────────────────────────


def test_send_once_429_increments(db: Session) -> None:
    """HTTP 429 → retryable, attempts incremented to 1."""
    transport = _make_transport(429)

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        result = send_once(
            db,
            "reminder",
            "dl:3:2026-11-20",
            {"type": "AdaptiveCard", "body": []},
            client=httpx.Client(transport=transport),
        )

    assert result == "retryable"
    row = db.scalar(select(PostLog).where(PostLog.ref_key == "dl:3:2026-11-20"))
    assert row.status == "retryable"
    assert row.attempts == 1
    assert row.last_error == "status 429"


def test_send_once_503_increments(db: Session) -> None:
    """HTTP 503 → retryable, attempts incremented."""
    transport = _make_transport(503)

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        result = send_once(
            db,
            "reminder",
            "dl:4:2026-11-20",
            {"type": "AdaptiveCard", "body": []},
            client=httpx.Client(transport=transport),
        )

    assert result == "retryable"
    row = db.scalar(select(PostLog).where(PostLog.ref_key == "dl:4:2026-11-20"))
    assert row.attempts == 1
    assert row.status == "retryable"


def test_send_once_429_retry_after_logged(db: Session) -> None:
    """429 with Retry-After header: error still shows status code."""
    transport = _make_transport(
        429,
        headers={"Retry-After": "30", "Content-Type": "application/json"},
    )

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        result = send_once(
            db,
            "reminder",
            "dl:5:2026-11-20",
            {"type": "AdaptiveCard", "body": []},
            client=httpx.Client(transport=transport),
        )

    assert result == "retryable"
    row = db.scalar(select(PostLog).where(PostLog.ref_key == "dl:5:2026-11-20"))
    assert row.last_error == "status 429"


# ── permanent → status 'permanent', no retry ──────────────────────────


def test_send_once_400_marks_permanent(db: Session) -> None:
    """HTTP 4xx (not 429) → permanent."""
    transport = _make_transport(400, body='{"error":"bad"}')

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        result = send_once(
            db,
            "reminder",
            "dl:6:2026-11-20",
            {"type": "AdaptiveCard", "body": []},
            client=httpx.Client(transport=transport),
        )

    assert result == "permanent"
    row = db.scalar(select(PostLog).where(PostLog.ref_key == "dl:6:2026-11-20"))
    assert row.status == "permanent"
    assert row.attempts == 1


def test_send_once_401_marks_permanent(db: Session) -> None:
    """HTTP 401 → permanent."""
    transport = _make_transport(401)

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        result = send_once(
            db,
            "reminder",
            "dl:7:2026-11-20",
            {"type": "AdaptiveCard", "body": []},
            client=httpx.Client(transport=transport),
        )

    assert result == "permanent"
    row = db.scalar(select(PostLog).where(PostLog.ref_key == "dl:7:2026-11-20"))
    assert row.status == "permanent"


# ── skip conditions ───────────────────────────────────────────────────


def test_send_once_already_sent_skips(db: Session) -> None:
    """Row already 'sent' → no HTTP call, returns 'sent'."""
    row = PostLog(kind="reminder", ref_key="dl:8:2026-11-20", status="sent", sent_at=now_utc())
    db.add(row)
    db.commit()

    transport_called = False

    def fail_handler(request: httpx.Request) -> httpx.Response:  # type: ignore[no-untyped-def]
        nonlocal transport_called
        transport_called = True
        return httpx.Response(200)

    transport = httpx.MockTransport(fail_handler)

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        result = send_once(
            db,
            "reminder",
            "dl:8:2026-11-20",
            {"type": "AdaptiveCard", "body": []},
            client=httpx.Client(transport=transport),
        )

    assert result == "sent"
    assert not transport_called


def test_send_once_5_attempts_skips(db: Session) -> None:
    """attempts >= 5 → skipped, no HTTP call."""
    row = PostLog(
        kind="reminder",
        ref_key="dl:9:2026-11-20",
        status="retryable",
        attempts=5,
        last_error="status 429",
    )
    db.add(row)
    db.commit()

    transport_called = False

    def fail_handler(request: httpx.Request) -> httpx.Response:  # type: ignore[no-untyped-def]
        nonlocal transport_called
        transport_called = True
        return httpx.Response(200)

    transport = httpx.MockTransport(fail_handler)

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        result = send_once(
            db,
            "reminder",
            "dl:9:2026-11-20",
            {"type": "AdaptiveCard", "body": []},
            client=httpx.Client(transport=transport),
        )

    assert result == "skipped"
    assert not transport_called


def test_send_once_permanent_status_skips(db: Session) -> None:
    """Row with 'permanent' status → skipped, no retry."""
    row = PostLog(
        kind="reminder",
        ref_key="dl:10:2026-11-20",
        status="permanent",
        attempts=1,
        last_error="status 400",
    )
    db.add(row)
    db.commit()

    transport_called = False

    def ok_handler(request: httpx.Request) -> httpx.Response:  # type: ignore[no-untyped-def]
        nonlocal transport_called
        transport_called = True
        return httpx.Response(202)

    transport = httpx.MockTransport(ok_handler)

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        result = send_once(
            db,
            "reminder",
            "dl:10:2026-11-20",
            {"type": "AdaptiveCard", "body": []},
            client=httpx.Client(transport=transport),
        )

    assert result == "skipped"
    assert not transport_called
    # Row is unchanged
    row = db.scalar(select(PostLog).where(PostLog.ref_key == "dl:10:2026-11-20"))
    assert row.status == "permanent"
    assert row.attempts == 1


# ── dry run ───────────────────────────────────────────────────────────


def test_send_once_dry_run(db: Session) -> None:
    """No webhook URL → dry_run, row created with status 'dry_run'."""
    card = {"type": "AdaptiveCard", "body": []}

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", "")
        get_settings.cache_clear()
        result = send_once(
            db,
            "reminder",
            "dl:11:2026-11-20",
            card,
        )

    assert result == "dry_run"
    row = db.scalar(select(PostLog).where(PostLog.ref_key == "dl:11:2026-11-20"))
    assert row is not None
    assert row.status == "dry_run"


def test_send_once_dry_run_does_not_call_http(db: Session) -> None:
    """Dry run must never make an HTTP call."""
    called = False

    def fail_handler(request: httpx.Request) -> httpx.Response:  # type: ignore[no-untyped-def]
        nonlocal called
        called = True
        return httpx.Response(200)

    transport = httpx.MockTransport(fail_handler)

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", "")
        get_settings.cache_clear()
        result = send_once(
            db,
            "reminder",
            "dl:12:2026-11-20",
            {"type": "AdaptiveCard", "body": []},
            client=httpx.Client(transport=transport),
        )

    assert result == "dry_run"
    assert not called


# ── network errors ────────────────────────────────────────────────────


def test_send_once_timeout(db: Session) -> None:
    """TimeoutException → retryable."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        with httpx.Client() as client:
            client.post = lambda *a, **kw: (_ for _ in ()).throw(  # type: ignore[assignment]
                httpx.TimeoutException("timeout")
            )
            result = send_once(
                db,
                "reminder",
                "dl:13:2026-11-20",
                {"type": "AdaptiveCard", "body": []},
                client=client,
            )

    assert result == "retryable"
    row = db.scalar(select(PostLog).where(PostLog.ref_key == "dl:13:2026-11-20"))
    assert row.status == "retryable"
    assert row.attempts == 1
    assert row.last_error == "timeout"


def test_send_once_connection_error(db: Session) -> None:
    """ConnectError → retryable."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        client = httpx.Client(base_url="http://127.0.0.1:1")
        try:
            result = send_once(
                db,
                "reminder",
                "dl:14:2026-11-20",
                {"type": "AdaptiveCard", "body": []},
                client=client,
            )
        finally:
            client.close()

    assert result == "retryable"
    row = db.scalar(select(PostLog).where(PostLog.ref_key == "dl:14:2026-11-20"))
    assert row.status == "retryable"
    assert row.attempts == 1


# ── explicit now parameter ────────────────────────────────────────────


def test_send_once_explicit_now(db: Session) -> None:
    """When now is provided it is used for sent_at (not the real clock)."""
    expected_now = datetime(2026, 11, 20, 14, 30, tzinfo=UTC)
    transport = _make_transport(202)

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        send_once(
            db,
            "reminder",
            "dl:15:2026-11-20",
            {"type": "AdaptiveCard", "body": []},
            client=httpx.Client(transport=transport),
            now=expected_now,
        )

    row = db.scalar(select(PostLog).where(PostLog.ref_key == "dl:15:2026-11-20"))
    assert row.sent_at == expected_now


# ── recovery: retryable → sent on subsequent call ─────────────────────


def test_send_once_recovery(db: Session) -> None:
    """A retryable row that succeeds on retry → sent, attempts unchanged."""
    attempt = [0]

    def handler(request: httpx.Request) -> httpx.Response:  # type: ignore[no-untyped-def]
        attempt[0] += 1
        if attempt[0] == 1:
            return httpx.Response(429)
        return httpx.Response(202)

    transport = httpx.MockTransport(handler)

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()

        # First attempt: fails
        send_once(
            db,
            "reminder",
            "dl:16:2026-11-20",
            {"type": "AdaptiveCard", "body": []},
            client=httpx.Client(transport=transport),
        )

    row = db.scalar(select(PostLog).where(PostLog.ref_key == "dl:16:2026-11-20"))
    assert row.status == "retryable"
    assert row.attempts == 1

    # Second attempt: succeeds
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        result = send_once(
            db,
            "reminder",
            "dl:16:2026-11-20",
            {"type": "AdaptiveCard", "body": []},
            client=httpx.Client(transport=transport),
        )

    assert result == "sent"
    row = db.scalar(select(PostLog).where(PostLog.ref_key == "dl:16:2026-11-20"))
    assert row.status == "sent"
    assert row.attempts == 1  # attempts preserved


# ── isolation ─────────────────────────────────────────────────────────


def test_send_once_multiple_rows_isolated(db: Session) -> None:
    """Different ref_keys do not interfere with each other."""
    transport = _make_transport(202)

    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        send_once(
            db,
            "reminder",
            "dl:A",
            {"type": "AdaptiveCard", "body": []},
            client=httpx.Client(transport=transport),
        )
        send_once(
            db,
            "reminder",
            "dl:B",
            {"type": "AdaptiveCard", "body": []},
            client=httpx.Client(transport=transport),
        )

    rows = db.execute(select(PostLog).where(PostLog.ref_key.in_(["dl:A", "dl:B"]))).scalars().all()
    assert len(rows) == 2
    for row in rows:
        assert row.status == "sent"
        assert row.attempts == 0


def test_send_once_unexpected_exception(db: Session) -> None:
    """An unexpected exception during POST → permanent."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("TEAMS_WEBHOOK_URL", _WEBHOOK)
        get_settings.cache_clear()
        with httpx.Client() as client:
            client.post = lambda *a, **kw: (_ for _ in ()).throw(  # type: ignore[assignment]
                RuntimeError("boom")
            )
            result = send_once(
                db,
                "reminder",
                "dl:17:2026-11-20",
                {"type": "AdaptiveCard", "body": []},
                client=client,
            )

    assert result == "permanent"
    row = db.scalar(select(PostLog).where(PostLog.ref_key == "dl:17:2026-11-20"))
    assert row.status == "permanent"
    assert row.attempts == 1
    assert row.last_error == "RuntimeError"
