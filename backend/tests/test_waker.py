"""Tests for optional PC wake mechanism (SPEC 7.9)."""

import os
from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from app.config import get_settings
from app.models import AppState, Job
from app.worker import _wake, run_once


def _make_wake_transport(expected_token: str) -> httpx.MockTransport:
    """Return a transport that verifies token and returns 200."""
    count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        count[0] += 1
        assert request.url.path.endswith("/wake")
        assert request.headers.get("X-Waker-Token") == expected_token
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    return transport, count


def _make_error_transport(status: int) -> tuple[httpx.MockTransport, list[int]]:
    count = [0]

    def handler(request: httpx.Request) -> httpx.Response:
        count[0] += 1
        return httpx.Response(status)

    return httpx.MockTransport(handler), count


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def _create_settings(waker_url: str = "", waker_token: str = "") -> None:
    """Override environment variables and refresh settings cache."""
    os.environ["WAKER_URL"] = waker_url
    os.environ["WAKER_TOKEN"] = waker_token
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Test 1: Unconfigured (no WAKER_URL) -> no wake call
# ---------------------------------------------------------------------------


def test_wake_no_url(db: Any) -> None:
    _create_settings(waker_token="secret")
    get_settings.cache_clear()

    transport, count = _make_wake_transport("secret")
    with httpx.Client(transport=transport) as client:
        _wake(db, datetime.utcnow(), client=client)

    assert count[0] == 0
    row = db.query(AppState).filter(AppState.key == "last_wake").first()
    assert row is None


def test_wake_no_token(db: Any) -> None:
    _create_settings(waker_url="http://waker.example.com")
    get_settings.cache_clear()

    transport, count = _make_wake_transport("any")
    with httpx.Client(transport=transport) as client:
        _wake(db, datetime.utcnow(), client=client)

    assert count[0] == 0
    row = db.query(AppState).filter(AppState.key == "last_wake").first()
    assert row is None


# ---------------------------------------------------------------------------
# Test 2: Configured + model down + queued job -> 1 POST with token
# ---------------------------------------------------------------------------


def test_wake_called_when_configured(db: Any) -> None:
    _create_settings(waker_url="http://waker.example.com", waker_token="my-secret")
    get_settings.cache_clear()

    transport, count = _make_wake_transport("my-secret")
    with httpx.Client(transport=transport) as client:
        _wake(db, datetime.utcnow(), client=client)

    assert count[0] == 1
    row = db.query(AppState).filter(AppState.key == "last_wake").first()
    assert row is not None
    assert isinstance(row.value, str)


# ---------------------------------------------------------------------------
# Test 3: Cooldown enforced (<30 min) -> no wake call
# ---------------------------------------------------------------------------


def test_wake_cooldown_enforced(db: Any) -> None:
    _create_settings(waker_url="http://waker.example.com", waker_token="my-secret")
    get_settings.cache_clear()

    now = datetime.utcnow()
    transport, count = _make_wake_transport("my-secret")
    with httpx.Client(transport=transport) as client:
        _wake(db, now, client=client)

    assert count[0] == 1

    # Call again within cooldown (< 30 min later)
    transport2, count2 = _make_wake_transport("my-secret")
    with httpx.Client(transport=transport2) as client2:
        _wake(db, now + timedelta(minutes=15), client=client2)

    assert count2[0] == 0


# ---------------------------------------------------------------------------
# Test 4: Cooldown expired (>31 min) -> wake call triggered again
# ---------------------------------------------------------------------------


def test_wake_cooldown_expired(db: Any) -> None:
    _create_settings(waker_url="http://waker.example.com", waker_token="my-secret")
    get_settings.cache_clear()

    now = datetime.utcnow()
    transport, count = _make_wake_transport("my-secret")
    with httpx.Client(transport=transport) as client:
        _wake(db, now, client=client)

    assert count[0] == 1

    # Call again after cooldown (> 30 min later)
    transport2, count2 = _make_wake_transport("my-secret")
    with httpx.Client(transport=transport2) as client2:
        _wake(db, now + timedelta(minutes=31), client=client2)

    assert count2[0] == 1


# ---------------------------------------------------------------------------
# Test 5: Waker 500 error -> no crash
# ---------------------------------------------------------------------------


def test_wake_500_no_crash(db: Any) -> None:
    _create_settings(waker_url="http://waker.example.com", waker_token="my-secret")
    get_settings.cache_clear()

    transport, count = _make_error_transport(500)
    with httpx.Client(transport=transport) as client:
        # Should not raise
        _wake(db, datetime.utcnow(), client=client)

    # Even on 500, last_wake is stored (the attempt was made)
    assert count[0] == 1
    row = db.query(AppState).filter(AppState.key == "last_wake").first()
    assert row is not None


# ---------------------------------------------------------------------------
# Test 6: run_once with model down triggers wake
# ---------------------------------------------------------------------------


def test_run_once_model_offline_triggers_wake(db: Any) -> None:
    _create_settings(waker_url="http://waker.example.com", waker_token="my-secret")
    get_settings.cache_clear()

    # Add a queued job so we can verify run_once gets there
    job = Job(
        status="queued",
        transcript="test transcript",
        title="Test Meeting",
        meeting_date=datetime.utcnow().date(),
    )
    db.add(job)
    db.commit()

    # Patch _wake to verify it is called and inject a mock transport
    transport, count = _make_wake_transport("my-secret")
    fake_client = httpx.Client(transport=transport)

    with patch("app.worker.is_up", return_value=False), patch("app.worker._wake") as mock_wake:
        mock_wake.side_effect = lambda s, n, *, client=None: _wake(s, n, client=fake_client)
        result = run_once(db, datetime.utcnow())

    assert result == "model_offline"
    assert mock_wake.called
    assert count[0] == 1
