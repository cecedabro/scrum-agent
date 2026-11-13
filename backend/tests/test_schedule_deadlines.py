"""Tests for app/schedule.py – deadline reminder due_posts (SPEC 6.3).

Covers:
- 2 days out → reminder included
- 1 day out → reminder included
- 0 in days_before → "vandaag"
- a moved deadline gets a new ref_key
- a deadline 3 days out is not due (when days_before only has 2,1,0)
"""

from __future__ import annotations

import datetime
from datetime import date

from app.schedule import DuePost, due_posts

# ── Helper to build ReminderSettings-like objects ────────────────────


class _Settings:
    """Minimal duck-typed ReminderSettings."""

    def __init__(self, **overrides):
        defaults = {
            "weekly_enabled": False,
            "weekly_weekday": "maandag",
            "weekly_time": "08:30",
            "deadline_reminder_enabled": False,
            "deadline_reminder_time": "09:00",
            "weekdays_before": [],
            "sprint_enabled": False,
            "sprint_end_date": "",
            "sprint_length": 2,
            "sprint_days_before": 1,
            "sprint_time": "09:00",
            "summary_auto_post": True,
        }
        defaults.update(overrides)
        for k, v in defaults.items():
            setattr(self, k, v)


def _dl(id=1, due_date=None, due_time=None, title="Taak", note=None):
    """Build a deadline dict."""
    return {
        "id": id,
        "title": title,
        "due_date": due_date,
        "due_time": due_time,
        "note": note,
    }


# ── Helper for window-aware UTC times ────────────────────────────────


def _local_now(date_val, hour, minute, month=11, year=2026):
    """Return a UTC-aware datetime that corresponds to *hour:minute* local time on *date_val*.

    Uses November (CET, UTC+1) or June (CEST, UTC+2) for DST testing.
    """
    from zoneinfo import ZoneInfo

    local_tz = ZoneInfo("Europe/Amsterdam")
    local_dt = datetime.datetime(year, month, date_val, hour, minute, tzinfo=local_tz)
    return local_dt.astimezone(datetime.UTC)


# ── 2 days out → reminder included ─────────────────────────────────


class TestTwoDaysBefore:
    def test_deadline_2_days_out_is_due(self):
        """A deadline due in 2 days should appear when days_before includes 2."""
        settings = _Settings(
            deadline_reminder_enabled=True,
            deadline_reminder_time="09:00",
            weekdays_before=[2, 1],
        )
        # Nov 16 Monday, 09:00 local = 08:00 UTC (CET)
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 18), title="Opdracht inleveren")
        result = due_posts(now, settings, [dl])
        assert len(result) == 1
        assert isinstance(result[0], DuePost)
        assert result[0].kind == "deadline"
        assert result[0].ref_key == "deadline:1:2026-11-18:2"

    def test_card_has_correct_header(self):
        """The card header should mention 'over 2 dagen'."""
        settings = _Settings(
            deadline_reminder_enabled=True,
            deadline_reminder_time="09:00",
            weekdays_before=[2, 1],
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 18), title="Opdracht inleveren")
        result = due_posts(now, settings, [dl])
        header = result[0].card["body"][0]["text"]
        assert "over 2 dagen" in header


# ── 1 day out → reminder included ──────────────────────────────────


class TestOneDayBefore:
    def test_deadline_1_day_out_is_due(self):
        """A deadline due tomorrow should appear when days_before includes 1."""
        settings = _Settings(
            deadline_reminder_enabled=True,
            deadline_reminder_time="09:00",
            weekdays_before=[2, 1],
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=2, due_date=date(2026, 11, 17), title="Samenkomst voorbereiden")
        result = due_posts(now, settings, [dl])
        assert len(result) == 1
        assert isinstance(result[0], DuePost)
        assert result[0].kind == "deadline"
        assert result[0].ref_key == "deadline:2:2026-11-17:1"

    def test_card_has_morgen_label(self):
        """The card header should mention 'morgen'."""
        settings = _Settings(
            deadline_reminder_enabled=True,
            deadline_reminder_time="09:00",
            weekdays_before=[2, 1],
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=2, due_date=date(2026, 11, 17), title="Samenkomst voorbereiden")
        result = due_posts(now, settings, [dl])
        header = result[0].card["body"][0]["text"]
        assert "morgen" in header


# ── 0 in days_before → "vandaag" ───────────────────────────────────


class TestZeroDaysBefore:
    def test_deadline_today_is_due_with_zero(self):
        """A deadline due today should appear when days_before includes 0."""
        settings = _Settings(
            deadline_reminder_enabled=True,
            deadline_reminder_time="09:00",
            weekdays_before=[0, 2, 1],
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=3, due_date=date(2026, 11, 16), title="Vandaag inleveren")
        result = due_posts(now, settings, [dl])
        assert len(result) == 1
        assert isinstance(result[0], DuePost)
        assert result[0].kind == "deadline"
        assert result[0].ref_key == "deadline:3:2026-11-16:0"

    def test_card_has_vandaag_label(self):
        """The card header should mention 'vandaag'."""
        settings = _Settings(
            deadline_reminder_enabled=True,
            deadline_reminder_time="09:00",
            weekdays_before=[0, 2, 1],
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=3, due_date=date(2026, 11, 16), title="Vandaag inleveren")
        result = due_posts(now, settings, [dl])
        header = result[0].card["body"][0]["text"]
        assert "vandaag" in header


# ── Moved deadline gets a new ref_key ──────────────────────────────


class TestMovedDeadline:
    def test_moving_deadline_creates_new_ref_key(self):
        """When a deadline's due_date changes, the old ref_key no longer matches.

        Example: deadline moved from Nov 17 to Nov 18.
        The old ref_key 'deadline:4:2026-11-17:1' (1-day reminder for old date)
        is in post_log but does not block the new ref_key
        'deadline:4:2026-11-18:2' (2-day reminder for new date).
        """
        settings = _Settings(
            deadline_reminder_enabled=True,
            deadline_reminder_time="09:00",
            weekdays_before=[2],
        )
        now = _local_now(16, 9, 0, month=11)
        # Deadline was originally Nov 17 (1 day out), now moved to Nov 18 (2 days out)
        dl = _dl(id=4, due_date=date(2026, 11, 18), title="Verplaatste deadline")

        # Old ref_key for the old date (Nov 17 was 1 day from Nov 16)
        old_ref_key = "deadline:4:2026-11-17:1"
        post_log = {old_ref_key: "sent"}

        result = due_posts(now, settings, [dl], post_log=post_log)
        assert len(result) == 1
        assert result[0].ref_key == "deadline:4:2026-11-18:2"
        # The new ref_key is not the same as the old sent ref_key
        assert result[0].ref_key != old_ref_key

    def test_old_ref_key_sent_does_not_block_new_ref_key(self):
        """Even if the old ref_key is in post_log as 'sent', the new one is fresh."""
        settings = _Settings(
            deadline_reminder_enabled=True,
            deadline_reminder_time="09:00",
            weekdays_before=[2],
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=5, due_date=date(2026, 11, 18), title="Verplaatst")
        post_log = {"deadline:5:2026-11-17:1": "sent"}

        result = due_posts(now, settings, [dl], post_log=post_log)
        assert len(result) == 1
        assert result[0].ref_key == "deadline:5:2026-11-18:2"


# ── Deadline 3 days out is not due ─────────────────────────────────


class TestThreeDaysOut:
    def test_deadline_3_days_out_not_included(self):
        """A deadline 3 days out should NOT appear when days_before is [2,1,0]."""
        settings = _Settings(
            deadline_reminder_enabled=True,
            deadline_reminder_time="09:00",
            weekdays_before=[2, 1, 0],
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=6, due_date=date(2026, 11, 19), title="Over 3 dagen")
        result = due_posts(now, settings, [dl])
        assert result == []

    def test_deadline_3_days_out_not_included_without_3_in_days_before(self):
        """With only [2,1] in days_before, a 3-day-out deadline should not appear."""
        settings = _Settings(
            deadline_reminder_enabled=True,
            deadline_reminder_time="09:00",
            weekdays_before=[2, 1],
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=7, due_date=date(2026, 11, 19), title="Niet te vroeg")
        result = due_posts(now, settings, [dl])
        assert result == []


# ── Multiple deadlines at the same time ────────────────────────────


class TestMultipleDeadlines:
    def test_two_deadlines_same_day_both_appear(self):
        """Two deadlines due on the same day should both be included."""
        settings = _Settings(
            deadline_reminder_enabled=True,
            deadline_reminder_time="09:00",
            weekdays_before=[1],
        )
        now = _local_now(16, 9, 0, month=11)
        dl1 = _dl(id=8, due_date=date(2026, 11, 17), title="Deadline A")
        dl2 = _dl(id=9, due_date=date(2026, 11, 17), title="Deadline B")
        result = due_posts(now, settings, [dl1, dl2])
        assert len(result) == 2
        ref_keys = {r.ref_key for r in result}
        assert "deadline:8:2026-11-17:1" in ref_keys
        assert "deadline:9:2026-11-17:1" in ref_keys


# ── Disabled deadline reminders → nothing ──────────────────────────


class TestDisabled:
    def test_deadline_reminders_disabled_returns_empty(self):
        """When deadline reminders are off, no deadline posts appear."""
        settings = _Settings(
            deadline_reminder_enabled=False,
            weekdays_before=[2, 1, 0],
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=10, due_date=date(2026, 11, 17), title="Taak")
        result = due_posts(now, settings, [dl])
        assert result == []


# ── Window timing ──────────────────────────────────────────────────


class TestWindowTiming:
    def test_before_window_not_due(self):
        """Before the configured reminder time, no deadline posts are due."""
        settings = _Settings(
            deadline_reminder_enabled=True,
            deadline_reminder_time="09:00",
            weekdays_before=[1],
        )
        # 08:59 local = 07:59 UTC (CET)
        now = _local_now(16, 8, 59, month=11)
        dl = _dl(id=11, due_date=date(2026, 11, 17), title="Taak")
        result = due_posts(now, settings, [dl])
        assert result == []

    def test_after_window_not_due(self):
        """More than 6 hours after the reminder time, no posts are due."""
        settings = _Settings(
            deadline_reminder_enabled=True,
            deadline_reminder_time="09:00",
            weekdays_before=[1],
        )
        # 15:01 local = 14:01 UTC (CET), which is 6h1m past 09:00 local
        now = _local_now(16, 15, 1, month=11)
        dl = _dl(id=12, due_date=date(2026, 11, 17), title="Taak")
        result = due_posts(now, settings, [dl])
        assert result == []


# ── Already sent ref_key → skipped ─────────────────────────────────


class TestPostLogFiltering:
    def test_skips_already_sent_deadline_reminder(self):
        """An already-sent deadline reminder ref_key should be skipped."""
        settings = _Settings(
            deadline_reminder_enabled=True,
            deadline_reminder_time="09:00",
            weekdays_before=[1],
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=13, due_date=date(2026, 11, 17), title="Taak")
        post_log = {"deadline:13:2026-11-17:1": "sent"}
        result = due_posts(now, settings, [dl], post_log=post_log)
        assert result == []

    def test_allows_failed_deadline_reminder(self):
        """A failed deadline reminder should be resent."""
        settings = _Settings(
            deadline_reminder_enabled=True,
            deadline_reminder_time="09:00",
            weekdays_before=[1],
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=14, due_date=date(2026, 11, 17), title="Taak")
        post_log = {"deadline:14:2026-11-17:1": "failed"}
        result = due_posts(now, settings, [dl], post_log=post_log)
        assert len(result) == 1
