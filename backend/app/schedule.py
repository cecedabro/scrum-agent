"""Reminder schedule – pure functions for due-post detection (SPEC 6.1-6.5).

``due_posts(now, settings, deadlines, *, post_log=None) -> list[DuePost]``

For each enabled reminder type it computes the local scheduled moment
``datetime.combine(local_date, time, tzinfo=Europe/Amsterdam)`` and checks
whether ``now`` falls within the 6-hour window:
``scheduled <= now < scheduled + 6h``.

Yesterday's scheduled moment is also checked (for a window that crosses
midnight).  Whether a post was already sent is the post-log's job, not
this function's.

Sprint end dates: from stored end date ``E`` and length ``L`` weeks the
ends are ``E + k * L * 7`` days for any integer ``k``; the next end is
the smallest one >= today.
"""

from __future__ import annotations

import datetime
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, time
from typing import TYPE_CHECKING, Any

from app.cards import deadline_reminder, sprint_nudge, weekly_overview
from app.clock import local_moment, to_local
from app.config import TIMEZONE

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[import-not-found,no-redef]

if TYPE_CHECKING:
    from app.settings import ReminderSettings

_LOCAL_TZ = ZoneInfo(TIMEZONE)


def _parse_time(hhmm: str) -> time:
    """Parse a time string (e.g. ``08:30``) into a ``datetime.time``."""
    return time.fromisoformat(hhmm)


def _safe_local_moment(day: date, hhmm: str) -> datetime.datetime | None:
    """Build a local moment from a string, returning None on ValueError."""
    try:
        return local_moment(day, _parse_time(hhmm))
    except ValueError:
        return None


@dataclass
class DuePost:
    """One reminder that is due right now."""

    kind: str
    ref_key: str
    card: dict[str, Any]


def _in_window(now: datetime.datetime, scheduled: datetime.datetime) -> bool:
    """Return True when *now* is in the 6-hour window after *scheduled*."""
    return scheduled <= now < scheduled + datetime.timedelta(hours=6)


def _next_sprint_ends(
    end_date: datetime.date, length_weeks: int, as_of: datetime.date
) -> list[datetime.date]:
    """All sprint end dates >= *as_of* given a repeating sprint.

    The stored *end_date* is the end of the current sprint.  Every
    sprint is *length_weeks* weeks long.  The full sequence of ends is
    ``end_date + k * length_weeks * 7`` days for any integer ``k``.
    """
    delta_days = length_weeks * 7
    d = end_date
    while d < as_of:
        d = d + datetime.timedelta(days=delta_days)
    ends: list[datetime.date] = []
    while len(ends) < 4:  # cap at a reasonable number for window checks
        ends.append(d)
        d = d + datetime.timedelta(days=delta_days)
    return ends


def due_posts(
    now: datetime.datetime,
    settings: ReminderSettings,
    deadlines: list[dict[str, Any]],
    *,
    post_log: Mapping[str, str] | None = None,
) -> list[DuePost]:
    """Return the list of reminders that are due at *now*.

    Parameters
    ----------
    now:
        Aware UTC datetime (the current moment).
    settings:
        ``ReminderSettings`` datainstance (duck-typed: must have
        ``weekly_enabled``, ``weekly_weekday``, ``weekly_time``,
        ``deadline_reminder_enabled``, ``deadline_reminder_time``,
        ``weekdays_before``, ``sprint_enabled``, ``sprint_end_date``,
        ``sprint_length``, ``sprint_days_before``, ``sprint_time``).
    deadlines:
        List of dicts with ``title``, ``due_date``, optional
        ``due_time`` and optional ``note``.
    post_log:
        Optional mapping of ``ref_key`` -> status string.  Used to
        skip already-sent posts.
    """
    post_log = post_log or {}
    result: list[DuePost] = []

    local_now = to_local(now)
    today = local_now.date()

    # ------------------------------------------------------------------
    # Weekly overview (SPEC 6.2)
    # ------------------------------------------------------------------
    if getattr(settings, "weekly_enabled", False):
        wd_name = settings.weekly_weekday
        wd_index = [
            "maandag",
            "dinsdag",
            "woensdag",
            "donderdag",
            "vrijdag",
            "zaterdag",
            "zondag",
        ].index(wd_name)

        # Today's Monday
        today_monday = today - datetime.timedelta(days=today.weekday())

        # Today's scheduled moment (the configured weekday at the configured time)
        try:
            sched_today = _safe_local_moment(
                today_monday + datetime.timedelta(days=wd_index), settings.weekly_time
            )
        except ValueError:
            sched_today = None  # spring-forward gap

        if sched_today is not None and _in_window(now, sched_today):
            if today_monday.weekday() != 0:
                # Not Monday: check yesterday's scheduled moment
                yesterday_monday = today_monday - datetime.timedelta(days=1)
                try:
                    sched_yesterday = _safe_local_moment(
                        yesterday_monday + datetime.timedelta(days=wd_index), settings.weekly_time
                    )
                except ValueError:
                    sched_yesterday = None
                if sched_yesterday and _in_window(now, sched_yesterday):
                    week_start = yesterday_monday
                else:
                    week_start = today_monday
            else:
                week_start = today_monday

            week_number = week_start.isocalendar()[1]
            iso_year = week_start.isocalendar()[0]
            ref_key = f"weekly:{iso_year}-W{week_number}"

            if ref_key not in post_log or post_log[ref_key] != "sent":
                week_deadlines = [
                    dl
                    for dl in deadlines
                    if dl["due_date"] >= week_start
                    and dl["due_date"] < week_start + datetime.timedelta(days=7)
                ]
                card = weekly_overview(week_start, week_deadlines)
                result.append(DuePost(kind="weekly", ref_key=ref_key, card=card))

    # ------------------------------------------------------------------
    # Deadline reminders (SPEC 6.3)
    # ------------------------------------------------------------------
    if getattr(settings, "deadline_reminder_enabled", False):
        try:
            sched = _safe_local_moment(today, settings.deadline_reminder_time)
        except ValueError:
            sched = None

        if sched is not None and _in_window(now, sched):
            for days_before in getattr(settings, "weekdays_before", []):
                target = today + datetime.timedelta(days=days_before)
                for dl in deadlines:
                    if dl["due_date"] == target:
                        ref_key = f"deadline:{dl['id']}:{dl['due_date'].isoformat()}:{days_before}"
                        if ref_key not in post_log or post_log[ref_key] != "sent":
                            card = deadline_reminder(dl, days_before)
                            result.append(DuePost(kind="deadline", ref_key=ref_key, card=card))

    # ------------------------------------------------------------------
    # Sprint nudges (SPEC 6.4)
    # ------------------------------------------------------------------
    if getattr(settings, "sprint_enabled", False):
        sprint_end_str = getattr(settings, "sprint_end_date", "")
        if sprint_end_str:
            try:
                sprint_end = datetime.date.fromisoformat(sprint_end_str)
                length = settings.sprint_length
            except (ValueError, TypeError):
                sprint_end = None
                length = 2
        else:
            sprint_end = None
            length = 2

        if sprint_end is not None:
            try:
                sched = _safe_local_moment(today, settings.sprint_time)
            except ValueError:
                sched = None

            if sched is not None and _in_window(now, sched):
                for end_date in _next_sprint_ends(sprint_end, length, today):
                    nudge_date = end_date - datetime.timedelta(days=settings.sprint_days_before)
                    if nudge_date == today:
                        ref_key = f"sprint:{end_date.isoformat()}"
                        if ref_key not in post_log or post_log[ref_key] != "sent":
                            end_deadlines = [dl for dl in deadlines if dl["due_date"] <= end_date]
                            card = sprint_nudge(end_date, end_deadlines)
                            result.append(DuePost(kind="sprint", ref_key=ref_key, card=card))

    return result
