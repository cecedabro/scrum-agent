"""Tests for app/schedule.py – sprint nudge due_posts (SPEC 6.4).

Covers:
- end dates from an anchor in the past and in the future
- length 1 and 2 weeks
- days_before 1
- off by default
- the deadlines listed stop at the end date
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

    Uses November (CET, UTC+1) for all tests.
    """
    from zoneinfo import ZoneInfo

    local_tz = ZoneInfo("Europe/Amsterdam")
    local_dt = datetime.datetime(year, month, date_val, hour, minute, tzinfo=local_tz)
    return local_dt.astimezone(datetime.UTC)


# ── Past anchor, 2-week sprint → nudge fires ────────────────────────


class TestPastAnchor:
    def test_past_anchor_2_week_sprint_nudge_fires(self):
        """Stored end date Oct 20 (past), length 2 weeks.

        Sprint ends: Oct 20 + 28 = Nov 17, Nov 30, Dec 13, Dec 27.
        Today is Nov 16, days_before=1, so nudge_date = Nov 17 - 1 = Nov 16 == today.
        One sprint nudge should fire.
        """
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-10-20",
            sprint_length=2,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 17), title="Opdracht")
        result = due_posts(now, settings, [dl])
        assert len(result) == 1
        assert isinstance(result[0], DuePost)
        assert result[0].kind == "sprint"
        assert result[0].ref_key == "sprint:2026-11-17"

    def test_past_anchor_card_header(self):
        """Card header should mention the sprint end date."""
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-10-20",
            sprint_length=2,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 17), title="Opdracht")
        result = due_posts(now, settings, [dl])
        header = result[0].card["body"][0]["text"]
        assert header == "De sprint eindigt dinsdag 17 november"

    def test_past_anchor_no_nudge_wrong_day(self):
        """With anchor Oct 20, the first nudge is Nov 16. Nov 15 should not match."""
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-10-20",
            sprint_length=2,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(15, 9, 0, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 17), title="Opdracht")
        result = due_posts(now, settings, [dl])
        assert result == []


# ── Future anchor, 2-week sprint → nudge fires ──────────────────────


class TestFutureAnchor:
    def test_future_anchor_2_week_sprint_nudge_fires(self):
        """Stored end date Nov 23 (future), length 2 weeks.

        Sprint ends: Nov 23, Dec 7, Dec 21, Jan 4.
        Today is Nov 22, days_before=1, so nudge_date = Nov 23 - 1 = Nov 22 == today.
        One sprint nudge should fire for the first end.
        """
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-11-23",
            sprint_length=2,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(22, 9, 0, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 23), title="Weekopdracht")
        result = due_posts(now, settings, [dl])
        assert len(result) == 1
        assert isinstance(result[0], DuePost)
        assert result[0].kind == "sprint"
        assert result[0].ref_key == "sprint:2026-11-23"

    def test_future_anchor_card_header(self):
        """Card header should mention the sprint end date."""
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-11-23",
            sprint_length=2,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(22, 9, 0, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 23), title="Weekopdracht")
        result = due_posts(now, settings, [dl])
        header = result[0].card["body"][0]["text"]
        assert header == "De sprint eindigt maandag 23 november"

    def test_future_anchor_deadlines_included(self):
        """Deadlines up to the end date should be listed in the card."""
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-11-23",
            sprint_length=2,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(22, 9, 0, month=11)
        dl1 = _dl(id=1, due_date=date(2026, 11, 22), title="Taak 1")
        dl2 = _dl(id=2, due_date=date(2026, 11, 23), title="Taak 2")
        result = due_posts(now, settings, [dl1, dl2])
        facts = result[0].card["body"][1]["facts"]
        titles = [f["factValue"] for f in facts]
        assert "Taak 1" in titles
        assert "Taak 2" in titles


# ── Length 1 week → nudge fires ─────────────────────────────────────


class TestLengthOneWeek:
    def test_length_one_week_nudge_fires(self):
        """Stored end date Nov 24 (future), length 1 week.

        Sprint ends: Nov 24, Dec 1, Dec 8, Dec 15.
        Today is Nov 23, days_before=1, so nudge_date = Nov 24 - 1 = Nov 23 == today.
        One sprint nudge should fire.
        """
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-11-24",
            sprint_length=1,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(23, 9, 0, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 24), title="Week taak")
        result = due_posts(now, settings, [dl])
        assert len(result) == 1
        assert isinstance(result[0], DuePost)
        assert result[0].kind == "sprint"
        assert result[0].ref_key == "sprint:2026-11-24"

    def test_length_one_week_card_header(self):
        """Card header should mention the sprint end date for 1-week sprint."""
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-11-24",
            sprint_length=1,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(23, 9, 0, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 24), title="Week taak")
        result = due_posts(now, settings, [dl])
        header = result[0].card["body"][0]["text"]
        assert header == "De sprint eindigt dinsdag 24 november"

    def test_length_one_week_multiple_ends_no_nudge(self):
        """With 1-week length, not every day triggers a nudge.

        Ends: Nov 24, Dec 1, Dec 8, Dec 15.
        Nov 22 is not a nudge day (Nov 24 - 1 = Nov 23, not Nov 22).
        """
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-11-24",
            sprint_length=1,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(22, 9, 0, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 24), title="Week taak")
        result = due_posts(now, settings, [dl])
        assert result == []


# ── Off by default → nothing ────────────────────────────────────────


class TestOffByDefault:
    def test_sprint_disabled_returns_empty(self):
        """When sprint nudges are off (default), no sprint posts appear."""
        settings = _Settings(
            sprint_enabled=False,
            sprint_end_date="2026-11-23",
            sprint_length=2,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(22, 9, 0, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 23), title="Weekopdracht")
        result = due_posts(now, settings, [dl])
        assert result == []

    def test_defaults_have_sprint_enabled_false(self):
        """sprint_enabled defaults to False."""
        settings = _Settings()
        assert settings.sprint_enabled is False


# ── Deadlines stop at end date ──────────────────────────────────────


class TestDeadlinesStopAtEndDate:
    def test_deadlines_after_end_date_excluded(self):
        """Deadlines with due_date after the sprint end should not be listed."""
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-10-20",
            sprint_length=2,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(16, 9, 0, month=11)
        dl_before = _dl(id=1, due_date=date(2026, 11, 17), title="In sprint")
        dl_after = _dl(id=2, due_date=date(2026, 12, 1), title="Volgende sprint")
        result = due_posts(now, settings, [dl_before, dl_after])
        assert len(result) == 1
        facts = result[0].card["body"][1]["facts"]
        titles = [f["factValue"] for f in facts]
        assert "In sprint" in titles
        assert "Volgende sprint" not in titles

    def test_only_deadlines_up_to_end_date_in_card(self):
        """Only deadlines with due_date <= end_date appear in the card."""
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-10-20",
            sprint_length=2,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(16, 9, 0, month=11)
        dl1 = _dl(id=1, due_date=date(2026, 11, 15), title="Dag 15")
        dl2 = _dl(id=2, due_date=date(2026, 11, 17), title="Dag 17")
        dl3 = _dl(id=3, due_date=date(2026, 11, 20), title="Dag 20")
        result = due_posts(now, settings, [dl1, dl2, dl3])
        facts = result[0].card["body"][1]["facts"]
        titles = [f["factValue"] for f in facts]
        assert len(titles) == 2
        assert "Dag 15" in titles
        assert "Dag 17" in titles
        assert "Dag 20" not in titles


# ── Already sent ref_key → skipped ─────────────────────────────────


class TestPostLogFiltering:
    def test_skips_sent_sprint_nudge(self):
        """An already-sent sprint nudge ref_key should be skipped."""
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-10-20",
            sprint_length=2,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 17), title="Opdracht")
        post_log = {"sprint:2026-11-17": "sent"}
        result = due_posts(now, settings, [dl], post_log=post_log)
        assert result == []

    def test_allows_repost_if_failed(self):
        """A failed sprint nudge should be resent."""
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-10-20",
            sprint_length=2,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 17), title="Opdracht")
        post_log = {"sprint:2026-11-17": "failed"}
        result = due_posts(now, settings, [dl], post_log=post_log)
        assert len(result) == 1


# ── Window timing ──────────────────────────────────────────────────


class TestWindowTiming:
    def test_before_window_not_due(self):
        """Before the configured sprint time, no sprint posts are due."""
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-10-20",
            sprint_length=2,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(16, 8, 59, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 17), title="Opdracht")
        result = due_posts(now, settings, [dl])
        assert result == []

    def test_after_window_not_due(self):
        """More than 6 hours after the sprint time, no posts are due."""
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-10-20",
            sprint_length=2,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(16, 15, 1, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 17), title="Opdracht")
        result = due_posts(now, settings, [dl])
        assert result == []


# ── Empty deadlines ────────────────────────────────────────────────


class TestEmptyDeadlines:
    def test_no_deadlines_shows_text(self):
        """When there are no deadlines, the card shows an empty message."""
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-10-20",
            sprint_length=2,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(16, 9, 0, month=11)
        result = due_posts(now, settings, [])
        assert len(result) == 1
        text_block = result[0].card["body"][1]
        assert text_block["type"] == "TextBlock"
        assert text_block["text"] == "Geen open deadlines."


# ── Multiple sprint ends on same day ───────────────────────────────


class TestMultipleEnds:
    def test_only_one_nudge_per_end_date(self):
        """Each sprint end date produces at most one nudge ref_key."""
        settings = _Settings(
            sprint_enabled=True,
            sprint_end_date="2026-10-20",
            sprint_length=2,
            sprint_days_before=1,
            sprint_time="09:00",
        )
        now = _local_now(16, 9, 0, month=11)
        dl = _dl(id=1, due_date=date(2026, 11, 17), title="Opdracht")
        result = due_posts(now, settings, [dl])
        ref_keys = [r.ref_key for r in result]
        # Should have exactly one entry for the Nov 17 end
        assert ref_keys.count("sprint:2026-11-17") == 1
