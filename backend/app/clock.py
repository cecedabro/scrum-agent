"""Clock helpers – the only place that reads the real clock.

UTC in storage; Europe/Amsterdam for display.  See docs/backend.md §Time.
"""

from datetime import UTC, date, datetime, time

from app.config import TIMEZONE

_tz = UTC  # alias for readability in this module

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[import-not-found,no-redef]


_LOCAL_TZ = ZoneInfo(TIMEZONE)


def now_utc() -> datetime:
    """Return the current UTC moment as an aware datetime."""
    return datetime.now(_tz)


def to_local(dt: datetime) -> datetime:
    """Convert an aware UTC datetime to local (Europe/Amsterdam) time."""
    return dt.astimezone(_LOCAL_TZ)


def today_local(now: datetime | None = None) -> date:
    """Return today's date in local time."""
    if now is None:
        now = now_utc()
    return to_local(now).date()


def local_moment(day: date, hhmm: time) -> datetime:
    """Build an aware UTC datetime from a local date + local time.

    ``day`` is a naive local date, ``hhmm`` is a naive local time.
    The result is expressed in UTC.

    Raises ``ValueError`` when the local time falls in a spring-forward gap.
    Ambiguous times (fall-back) resolve to the first (CEST) occurrence.
    """
    naive = datetime.combine(day, hhmm)
    aware = naive.replace(tzinfo=_LOCAL_TZ)
    utc = aware.astimezone(_tz)
    # Detect spring-forward gap: the round-trip to local time changes the hour
    round_trip = utc.astimezone(_LOCAL_TZ)
    if round_trip.hour != hhmm.hour or round_trip.minute != hhmm.minute:
        raise ValueError(f"{day}-{hhmm!r} does not exist in {_LOCAL_TZ.key} (spring-forward gap)")
    return utc
