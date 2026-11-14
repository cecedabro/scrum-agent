"""Authentication and failed-login limiter (SPEC 2.1, 2.2).

The `require_team` dependency checks HTTP Basic auth on every request
to a protected route.  Failed attempts are tracked per-client IP; after
more than 10 failures in a 5-minute window the client receives 429.

The injectable ``_clock`` (set via ``set_clock`` in tests) lets tests
run rate-limit logic without sleeping or depending on the real clock.
State is module-level so it survives across ``create_app()`` calls in
tests.  Call ``reset_login_state()`` between tests.
"""

from __future__ import annotations

import base64
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache
from hmac import compare_digest as hmac_compare_digest

from fastapi import Header, HTTPException, Request, status

from app.config import get_settings

# ------------------------------------------------------------------
# Injectable clock  (tests override via set_clock())
# ------------------------------------------------------------------
_clock: Callable[[], datetime] | None = None


def _now_utc() -> datetime:
    if _clock is not None:
        return _clock()
    return datetime.now(UTC)


def set_clock(clock_fn: Callable[[], datetime] | None) -> None:
    """Override the clock used by auth for testing."""
    global _clock  # noqa: PLW0603
    _clock = clock_fn


def _default_clock() -> datetime:
    return _now_utc()


# ------------------------------------------------------------------
# Rate-limit state  (module-level, shared across app instances)
# ------------------------------------------------------------------
_FAILED_LIMIT = 10
_WINDOW_SECONDS = 300  # 5 minutes

_failed_logins: dict[str, list[float]] = defaultdict(list)
_rate_limit_window: dict[str, float] = {}


def reset_login_state() -> None:
    """Clear failed-login and rate-limit state.  Call between tests."""
    _failed_logins.clear()
    _rate_limit_window.clear()


def _is_rate_limited(ip: str) -> bool:
    now = _now_utc().timestamp()
    window_start = now - _WINDOW_SECONDS

    # Prune entries older than the window
    _failed_logins[ip] = [t for t in _failed_logins[ip] if t > window_start]

    # Check if we should start a new window
    if ip not in _rate_limit_window:
        return False

    window_start_check = _rate_limit_window[ip]
    if now - window_start_check > _WINDOW_SECONDS:
        # Window expired
        _rate_limit_window.pop(ip, None)
        _failed_logins[ip] = []
        return False

    return len(_failed_logins[ip]) > _FAILED_LIMIT


def _record_failure(ip: str) -> None:
    now = _now_utc().timestamp()
    _failed_logins[ip].append(now)

    if len(_failed_logins[ip]) > _FAILED_LIMIT and ip not in _rate_limit_window:
        _rate_limit_window[ip] = now


def _get_client_ip(request: Request, cf_connecting_ip: str | None) -> str:
    if cf_connecting_ip:
        return cf_connecting_ip
    if request.client:
        return request.client.host
    return "127.0.0.1"


# ------------------------------------------------------------------
# Dependency
# ------------------------------------------------------------------
@lru_cache(maxsize=1)
def _credentials() -> tuple[str, str]:
    settings = get_settings()
    return settings.TEAM_USER, settings.TEAM_PASSWORD


def require_team(
    request: Request,
    cf_connecting_ip: str | None = Header(default=None),
) -> None:
    """SPEC 2.1 / 2.2: HTTP Basic auth + failed-login limiter."""
    ip = _get_client_ip(request, cf_connecting_ip)

    auth_header = request.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Basic "):
        _record_failure(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": 'Basic realm="scrum-agent"'},
        )

    try:
        decoded = base64.b64decode(auth_header[6:])
        decoded_str = decoded.decode("utf-8")
        if ":" not in decoded_str:
            raise ValueError("invalid format")
        provided_user, provided_pass = decoded_str.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        _record_failure(ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": 'Basic realm="scrum-agent"'},
        ) from None

    valid_user, valid_pass = _credentials()
    if not hmac_compare_digest(provided_user, valid_user) or not hmac_compare_digest(
        provided_pass, valid_pass
    ):
        _record_failure(ip)
        if _is_rate_limited(ip):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many failed login attempts",
            )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": 'Basic realm="scrum-agent"'},
        )
