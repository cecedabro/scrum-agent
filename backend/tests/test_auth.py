"""Tests for auth.py: HTTP Basic auth + failed-login limiter (SPEC 2.1, 2.2).

Tests live in ``backend/tests/`` so they run with ``cd backend &&
uv run pytest tests/test_auth.py -q``.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.auth import (
    _credentials,
    _failed_logins,
    _is_rate_limited,
    _record_failure,
    reset_login_state,
    set_clock,
)
from app.main import create_app


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _b64_credentials(user: str, password: str) -> str:
    """Return a properly encoded Basic auth header value."""
    encoded = base64.b64encode(f"{user}:{password}".encode()).decode("utf-8")
    return f"Basic {encoded}"


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_auth_state() -> None:
    """Reset auth state before every test."""
    reset_login_state()
    set_clock(None)
    _credentials.cache_clear()
    yield
    reset_login_state()
    set_clock(None)
    _credentials.cache_clear()


# ------------------------------------------------------------------
# No / wrong credentials → 401
# ------------------------------------------------------------------
def test_no_credentials_returns_401() -> None:
    """No Authorization header → 401."""
    with TestClient(create_app()) as c:
        r = c.get("/")
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers


def test_malformed_base64_returns_401() -> None:
    """Bad base64 in Authorization header → 401."""
    with TestClient(create_app()) as c:
        r = c.get("/", headers={"Authorization": "Basic !!!not-valid!!!"})
    assert r.status_code == 401


def test_wrong_password_returns_401() -> None:
    """Wrong password → 401."""
    settings = _credentials()
    wrong = _b64_credentials(settings[0], "wrong-password")
    with TestClient(create_app()) as c:
        r = c.get("/", headers={"Authorization": wrong})
    assert r.status_code == 401


def test_wrong_username_returns_401() -> None:
    """Wrong username → 401."""
    settings = _credentials()
    wrong = _b64_credentials("wronguser", settings[1])
    with TestClient(create_app()) as c:
        r = c.get("/", headers={"Authorization": wrong})
    assert r.status_code == 401


# ------------------------------------------------------------------
# Right credentials → 200
# ------------------------------------------------------------------
def test_success_with_valid_credentials() -> None:
    """Right user/password → 200."""
    settings = _credentials()
    creds = _b64_credentials(settings[0], settings[1])
    with TestClient(create_app()) as c:
        r = c.get("/", headers={"Authorization": creds})
    assert r.status_code == 200
    assert "Scrum agent" in r.text


# ------------------------------------------------------------------
# Rate limiting  (SPEC 2.2)
# ------------------------------------------------------------------
def test_11th_failure_returns_429() -> None:
    """More than 10 failures in 5 minutes → 429."""
    settings = _credentials()
    wrong = _b64_credentials(settings[0], "bad")
    creds = _b64_credentials(settings[0], settings[1])

    # 10 failures
    for _ in range(10):
        with TestClient(create_app()) as c:
            r = c.get("/", headers={"Authorization": wrong})
            assert r.status_code == 401

    # 11th → 429
    with TestClient(create_app()) as c:
        r = c.get("/", headers={"Authorization": wrong})
    assert r.status_code == 429

    # Success still works
    with TestClient(create_app()) as c:
        r = c.get("/", headers={"Authorization": creds})
    assert r.status_code == 200


def test_rate_limit_per_ip() -> None:
    """Rate limit is per IP, not per user."""
    settings = _credentials()
    wrong = _b64_credentials(settings[0], "bad")
    creds = _b64_credentials(settings[0], settings[1])

    # 10 failures from ip1
    for _ in range(10):
        with TestClient(create_app()) as c:
            c.get("/", headers={"Authorization": wrong, "CF-Connecting-IP": "ip1"})

    # 11th failure from ip1 → 429
    with TestClient(create_app()) as c:
        r = c.get("/", headers={"Authorization": wrong, "CF-Connecting-IP": "ip1"})
    assert r.status_code == 429

    # Same wrong credentials from ip2 → 401 (not rate limited)
    with TestClient(create_app()) as c:
        r = c.get("/", headers={"Authorization": wrong, "CF-Connecting-IP": "ip2"})
    assert r.status_code == 401

    # Valid credentials from ip1 → 200
    with TestClient(create_app()) as c:
        r = c.get("/", headers={"Authorization": creds, "CF-Connecting-IP": "ip1"})
    assert r.status_code == 200


def test_success_after_window_with_clock_override() -> None:
    """After the 5-minute window passes, rate limit resets."""
    set_clock(lambda: datetime(2026, 1, 1, 12, 10, tzinfo=UTC))
    reset_login_state()

    settings = _credentials()
    wrong = _b64_credentials(settings[0], "bad")

    # 10 failures at t = 12:10
    for _ in range(10):
        with TestClient(create_app()) as c:
            c.get("/", headers={"Authorization": wrong})

    # 11th → 429
    with TestClient(create_app()) as c:
        r = c.get("/", headers={"Authorization": wrong})
    assert r.status_code == 429

    # Advance past the 5-minute window (to 12:16)
    set_clock(lambda: datetime(2026, 1, 1, 12, 16, tzinfo=UTC))

    # Now it should work again (11th failure, but window expired)
    with TestClient(create_app()) as c:
        r = c.get("/", headers={"Authorization": wrong})
    assert r.status_code == 401  # window expired, not 429


def test_healthz_stays_open() -> None:
    """/healthz does not require auth, even after many failures."""
    settings = _credentials()
    wrong = _b64_credentials(settings[0], "bad")

    # 15 failures
    for _ in range(15):
        with TestClient(create_app()) as c:
            c.get("/", headers={"Authorization": wrong})

    # /healthz is still accessible
    with TestClient(create_app()) as c:
        r = c.get("/healthz")
    assert r.status_code == 200


def test_cf_connecting_ip_keys_the_limit() -> None:
    """CF-Connecting-IP header is used for rate limiting."""
    settings = _credentials()
    wrong = _b64_credentials(settings[0], "bad")

    # 10 failures with CF-Connecting-IP
    for _ in range(10):
        with TestClient(create_app()) as c:
            c.get("/", headers={"Authorization": wrong, "CF-Connecting-IP": "10.0.0.1"})

    # 11th → 429
    with TestClient(create_app()) as c:
        r = c.get("/", headers={"Authorization": wrong, "CF-Connecting-IP": "10.0.0.1"})
    assert r.status_code == 429


# ------------------------------------------------------------------
# Internal helpers (unit tests)
# ------------------------------------------------------------------
def test_record_failure_increments_count() -> None:
    """_record_failure adds a timestamp to the IP's list."""
    reset_login_state()
    set_clock(lambda: datetime(2026, 1, 1, 12, 0, tzinfo=UTC))
    _record_failure("1.2.3.4")
    assert len(_failed_logins["1.2.3.4"]) == 1
    assert not _is_rate_limited("1.2.3.4")


def test_is_rate_limited_exactly_10_not_limited() -> None:
    """Exactly 10 failures should not be rate limited (need >10)."""
    reset_login_state()
    set_clock(lambda: datetime(2026, 1, 1, 12, 0, tzinfo=UTC))

    for _ in range(10):
        _record_failure("ip1")

    assert _is_rate_limited("ip1") is False


def test_is_rate_limited_after_11() -> None:
    """11 failures → rate limited."""
    reset_login_state()
    set_clock(lambda: datetime(2026, 1, 1, 12, 0, tzinfo=UTC))

    for _ in range(11):
        _record_failure("ip2")

    assert _is_rate_limited("ip2") is True


def test_is_rate_limited_different_ips() -> None:
    """Rate limit is per IP; different IPs are independent."""
    reset_login_state()
    set_clock(lambda: datetime(2026, 1, 1, 12, 0, tzinfo=UTC))

    for _ in range(11):
        _record_failure("ip_a")

    assert _is_rate_limited("ip_a") is True
    assert _is_rate_limited("ip_b") is False


def test_reset_login_state_clears_state() -> None:
    """reset_login_state clears all rate limit state."""
    reset_login_state()
    set_clock(lambda: datetime(2026, 1, 1, 12, 0, tzinfo=UTC))

    for _ in range(11):
        _record_failure("ip_reset")

    assert _is_rate_limited("ip_reset") is True
    reset_login_state()
    assert _is_rate_limited("ip_reset") is False


def test_require_team_records_malformed_base64_failure() -> None:
    """Malformed base64 in Authorization header is counted as a failure."""
    reset_login_state()
    with TestClient(create_app()) as c:
        r = c.get(
            "/",
            headers={"Authorization": "Basic not-valid-base64!!!", "CF-Connecting-IP": "127.0.0.1"},
        )
        assert r.status_code == 401

    assert len(_failed_logins["127.0.0.1"]) == 1


def test_require_team_different_ips_different_limits() -> None:
    """Different IPs each get their own rate limit bucket."""
    reset_login_state()
    settings = _credentials()
    wrong = _b64_credentials(settings[0], "bad")

    # Fill up ip_alpha to 11 failures
    for _ in range(11):
        with TestClient(create_app()) as c:
            c.get("/", headers={"Authorization": wrong, "CF-Connecting-IP": "ip_alpha"})

    assert _is_rate_limited("ip_alpha") is True
    assert _is_rate_limited("ip_beta") is False
