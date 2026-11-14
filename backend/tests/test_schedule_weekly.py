"""Tests for app/schedule.py – weekly overview due_posts (SPEC 6.1, 6.2, 6.5).

Covers the weekly reminder window logic:
- disabled → nothing
- Monday 08:29 not due
- Monday 08:30 due
- 14:29 due (within 6 h)
- 14:31 not due
- Tuesday not due
- other weekday setting
- summer and winter UTC offsets
- ref_key weekly:2026-W47
"""

from __future__ import annotations

import datetime
from datetime import date, time

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


def _dl(due_date, due_time=None, title="Taak", note=None, id=1):
    """Build a deadline dict."""
    return {
        "title": title,
        "due_date": due_date,
        "due_time": due_time,
        "note": note,
        "id": id,
    }


# ── Disable → nothing ───────────────────────────────────────────────


class TestDisabled:
    def test_disabled_returns_empty(self):
        settings = _Settings(weekly_enabled=False)
        now = datetime.datetime(2026, 11, 16, 8, 30, tzinfo=datetime.UTC)
        result = due_posts(now, settings, [])
        assert result == []


# ── Monday 08:29 not due ───────────────────────────────────────────


class TestMondayBeforeWindow:
    def test_not_due_before_scheduled_time(self):
        """Monday 08:29 local (07:29 UTC) is before the 08:30 local scheduled moment.

        Not due because the window has not opened yet.
        """
        settings = _Settings(weekly_enabled=True)
        now = datetime.datetime(2026, 11, 16, 7, 29, tzinfo=datetime.UTC)
        result = due_posts(now, settings, [])
        assert result == []


# ── Monday 08:30 due ───────────────────────────────────────────────


class TestMondayAtWindow:
    def test_due_at_exactly_scheduled_time(self):
        """Monday 08:30 UTC = 09:30 local (winter) or 10:30 local (summer)."""
        # November 16 2026 is a Monday, and Amsterdam is in CET (UTC+1)
        # So 08:30 UTC = 09:30 local — not 08:30 local.
        # We need the UTC time that corresponds to 08:30 local.
        # CET = UTC+1, so 08:30 local = 07:30 UTC.
        settings = _Settings(weekly_enabled=True)
        now = datetime.datetime(2026, 11, 16, 7, 30, tzinfo=datetime.UTC)
        result = due_posts(now, settings, [])
        assert len(result) == 1
        assert isinstance(result[0], DuePost)
        assert result[0].kind == "weekly"
        assert result[0].ref_key == "weekly:2026-W47"

    def test_card_has_correct_week_number(self):
        settings = _Settings(weekly_enabled=True)
        now = datetime.datetime(2026, 11, 16, 7, 30, tzinfo=datetime.UTC)
        result = due_posts(now, settings, [])
        card = result[0].card
        assert card["body"][0]["text"] == "Deadlines deze week (week 47)"


# ── 14:29 due (within 6-hour window) ───────────────────────────────


class TestSixteenTwentyNine:
    def test_still_within_window(self):
        """Monday 14:29 UTC = 15:29 local → 6h1m past 09:30 local.

        Actually 14:29 UTC = 15:29 local, and 08:30 local = 07:30 UTC.
        So 14:29 - 07:30 = 6h59m → still within window? No, 6h59m > 6h.
        Let me recalculate:
        08:30 local (CET=UTC+1) = 07:30 UTC.
        Window ends at 07:30 + 6h = 13:30 UTC.
        14:29 UTC > 13:30 UTC → not due!

        The test should use a time that IS within the window.
        13:29 UTC should be due (within 6h of 07:30 UTC).
        """
        settings = _Settings(weekly_enabled=True)
        now = datetime.datetime(2026, 11, 16, 13, 29, tzinfo=datetime.UTC)
        result = due_posts(now, settings, [])
        assert len(result) == 1

    def test_not_due_after_window(self):
        """Monday 14:31 UTC = well past 13:30 UTC window end."""
        settings = _Settings(weekly_enabled=True)
        now = datetime.datetime(2026, 11, 16, 14, 31, tzinfo=datetime.UTC)
        result = due_posts(now, settings, [])
        assert result == []


# ── Tuesday not due ────────────────────────────────────────────────


class TestTuesdayNotDue:
    def test_wrong_weekday(self):
        """Tuesday should not trigger the weekly reminder."""
        settings = _Settings(weekly_enabled=True)
        now = datetime.datetime(2026, 11, 17, 8, 30, tzinfo=datetime.UTC)
        result = due_posts(now, settings, [])
        assert result == []


# ── Other weekday setting ──────────────────────────────────────────


class TestOtherWeekday:
    def test_tuesday_setting(self):
        """With Tuesday as the weekday setting, Tuesday should trigger."""
        settings = _Settings(weekly_enabled=True, weekly_weekday="dinsdag")
        # Tuesday Nov 17 2026, 08:30 local = 07:30 UTC (CET)
        now = datetime.datetime(2026, 11, 17, 7, 30, tzinfo=datetime.UTC)
        result = due_posts(now, settings, [])
        assert len(result) == 1
        assert result[0].kind == "weekly"

    def test_monday_setting_not_triggered_on_tuesday(self):
        settings = _Settings(weekly_enabled=True, weekly_weekday="maandag")
        now = datetime.datetime(2026, 11, 17, 7, 30, tzinfo=datetime.UTC)
        result = due_posts(now, settings, [])
        assert result == []


# ── Summer and winter UTC offsets ──────────────────────────────────


class TestDstOffsets:
    def test_winter_utc_offset(self):
        """November: Amsterdam is CET (UTC+1). 08:30 local = 07:30 UTC."""
        settings = _Settings(weekly_enabled=True, weekly_time="08:30")
        now = datetime.datetime(2026, 11, 16, 7, 30, tzinfo=datetime.UTC)
        result = due_posts(now, settings, [])
        assert len(result) == 1

    def test_summer_utc_offset(self):
        """June: Amsterdam is CEST (UTC+2). 08:30 local = 06:30 UTC."""
        settings = _Settings(weekly_enabled=True, weekly_time="08:30")
        # June 1 2026 is a Monday. Amsterdam is in CEST (UTC+2).
        now = datetime.datetime(2026, 6, 1, 6, 30, tzinfo=datetime.UTC)
        result = due_posts(now, settings, [])
        assert len(result) == 1

    def test_summer_window_end(self):
        """Summer: window ends at 06:30 + 6h = 12:30 UTC."""
        settings = _Settings(weekly_enabled=True, weekly_time="08:30")
        now = datetime.datetime(2026, 6, 1, 12, 29, tzinfo=datetime.UTC)
        result = due_posts(now, settings, [])
        assert len(result) == 1

        now = datetime.datetime(2026, 6, 1, 12, 31, tzinfo=datetime.UTC)
        result = due_posts(now, settings, [])
        assert result == []


# ── ref_key format ─────────────────────────────────────────────────


class TestRefKey:
    def test_ref_key_format_week47(self):
        """November Monday → ref_key weekly:2026-W47."""
        settings = _Settings(weekly_enabled=True)
        now = datetime.datetime(2026, 11, 16, 7, 30, tzinfo=datetime.UTC)
        result = due_posts(now, settings, [])
        assert result[0].ref_key == "weekly:2026-W47"

    def test_ref_key_with_deadlines_filtered(self):
        """ref_key is independent of deadline content."""
        settings = _Settings(weekly_enabled=True)
        now = datetime.datetime(2026, 11, 16, 7, 30, tzinfo=datetime.UTC)
        dl = _dl(date(2026, 11, 17), time(10, 0), title="Opdracht")
        result = due_posts(now, settings, [dl])
        assert result[0].ref_key == "weekly:2026-W47"


# ── Post log filtering ─────────────────────────────────────────────


class TestPostLogFiltering:
    def test_skips_sent_post(self):
        """Already-sent ref_key should not appear again."""
        settings = _Settings(weekly_enabled=True)
        now = datetime.datetime(2026, 11, 16, 7, 30, tzinfo=datetime.UTC)
        post_log = {"weekly:2026-W47": "sent"}
        result = due_posts(now, settings, [], post_log=post_log)
        assert result == []

    def test_allows_repost_if_not_sent(self):
        """Unseen or failed ref_key should be included."""
        settings = _Settings(weekly_enabled=True)
        now = datetime.datetime(2026, 11, 16, 7, 30, tzinfo=datetime.UTC)
        post_log = {"weekly:2026-W47": "failed"}
        result = due_posts(now, settings, [], post_log=post_log)
        assert len(result) == 1


# ── Deadline filtering in card ─────────────────────────────────────


class TestDeadlineFiltering:
    def test_card_lists_only_week_deadlines(self):
        """Only deadlines within the week should appear in the card."""
        settings = _Settings(weekly_enabled=True)
        now = datetime.datetime(2026, 11, 16, 7, 30, tzinfo=datetime.UTC)
        dl_in_week = _dl(date(2026, 11, 17), title="In week")
        dl_next_week = _dl(date(2026, 11, 24), title="Volgende week")
        result = due_posts(now, settings, [dl_in_week, dl_next_week])
        assert len(result) == 1
        facts = result[0].card["body"][1]["facts"]
        assert len(facts) == 1
        assert facts[0]["factValue"] == "In week"
