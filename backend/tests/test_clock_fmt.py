"""Tests for app/clock.py and app/fmt.py."""

from datetime import UTC, date, datetime, time

import pytest

from app.clock import local_moment, now_utc, to_local, today_local
from app.fmt import datum, datum_kort, relatief

# 2026 DST switch dates for Europe/Amsterdam:
#   Spring forward: 29 March 2026  (02:00 → 03:00, UTC+1 → UTC+2)
#   Fall back:      25 October 2026 (03:00 → 02:00, UTC+2 → UTC+1)


# ── clock.py ──────────────────────────────────────────────────────────────────


def test_now_utc_is_aware_utc() -> None:
    dt = now_utc()
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0


def test_now_utc_is_recent() -> None:
    dt = now_utc()
    assert abs((dt - datetime.now(UTC)).total_seconds()) < 5


def test_to_local_winter() -> None:
    # 2026-01-15 12:00 UTC = 13:00 Amsterdam (CET, UTC+1)
    dt = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    local = to_local(dt)
    assert local.hour == 13
    assert local.minute == 0


def test_to_local_summer() -> None:
    # 2026-07-20 12:00 UTC = 14:00 Amsterdam (CEST, UTC+2)
    dt = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)
    local = to_local(dt)
    assert local.hour == 14


def test_today_local_matches_local_date() -> None:
    # Pass a fixed UTC moment whose local date is 2026-03-15
    now = datetime(2026, 3, 15, 10, 0, tzinfo=UTC)
    assert today_local(now) == date(2026, 3, 15)


def test_today_local_crosses_midnight() -> None:
    # 2026-07-20 22:30 UTC = 00:30 next day in Amsterdam (CEST, UTC+2)
    now = datetime(2026, 7, 20, 22, 30, tzinfo=UTC)
    assert today_local(now) == date(2026, 7, 21)


def test_today_local_defaults_to_real_clock() -> None:
    d = today_local()
    assert isinstance(d, date)


def test_local_moment_winter_offset() -> None:
    # 2026-01-15 08:00 Amsterdam (CET, UTC+1) → 07:00 UTC
    result = local_moment(date(2026, 1, 15), time(8, 0))
    assert result.hour == 7
    assert result.minute == 0


def test_local_moment_summer_offset() -> None:
    # 2026-07-20 08:00 Amsterdam (CEST, UTC+2) → 06:00 UTC
    result = local_moment(date(2026, 7, 20), time(8, 0))
    assert result.hour == 6
    assert result.minute == 0


def test_local_moment_spring_forward_before_gap() -> None:
    # 2026-03-29 01:30 exists (CET, UTC+1) → 00:30 UTC
    result = local_moment(date(2026, 3, 29), time(1, 30))
    assert result.hour == 0
    assert result.minute == 30


def test_local_moment_spring_forward_after_gap() -> None:
    # 2026-03-29 04:00 exists (CEST, UTC+2) → 02:00 UTC
    result = local_moment(date(2026, 3, 29), time(4, 0))
    assert result.hour == 2
    assert result.minute == 0


def test_local_moment_spring_forward_in_gap_raises() -> None:
    # 2026-03-29 02:30 does not exist (clocks jump 02:00→03:00)
    with pytest.raises(ValueError, match="spring-forward gap"):
        local_moment(date(2026, 3, 29), time(2, 30))


def test_local_moment_fall_back_first_occurrence() -> None:
    # 2026-10-25 02:30 is ambiguous; fold=0 → first occurrence (CEST, UTC+2)
    # → 00:30 UTC
    result = local_moment(date(2026, 10, 25), time(2, 30))
    assert result.hour == 0
    assert result.minute == 30


def test_local_moment_fall_back_03_00() -> None:
    # 2026-10-25 03:00 is after the fall-back transition
    # (03:00 CEST → 02:00 CET), so 03:00 is CET (UTC+1) = 02:00 UTC
    result = local_moment(date(2026, 10, 25), time(3, 0))
    assert result.hour == 2
    assert result.minute == 0


def test_local_moment_is_aware_utc() -> None:
    result = local_moment(date(2026, 6, 1), time(12, 0))
    assert result.tzinfo is not None
    assert result.utcoffset().total_seconds() == 0


# ── fmt.py ────────────────────────────────────────────────────────────────────


def test_datum_full_weekday_month() -> None:
    # 2026-11-16 is a Monday → "maandag 16 november"
    d = date(2026, 11, 16)
    assert datum(d) == "maandag 16 november"


def test_datum_mid_month() -> None:
    # 2026-06-15 is a Monday
    d = date(2026, 6, 15)
    assert datum(d) == "maandag 15 juni"


def test_datum_end_of_year() -> None:
    # 2026-12-31 is a Thursday
    d = date(2026, 12, 31)
    assert datum(d) == "donderdag 31 december"


def test_datum_accepts_datetime() -> None:
    dt = datetime(2026, 11, 16, 10, 30)
    assert datum(dt) == "maandag 16 november"


def test_datum_all_weekdays() -> None:
    # Check every weekday name appears correctly
    expected = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]
    for i, wd in enumerate(expected):
        d = date(2026, 11, 16 + i)  # Mon–Sun
        assert datum(d).startswith(wd)


def test_datum_kort_short_form() -> None:
    # 2026-11-16 is a Monday → "ma 16 nov"
    d = date(2026, 11, 16)
    assert datum_kort(d) == "ma 16 nov"


def test_datum_kort_accepts_datetime() -> None:
    dt = datetime(2026, 11, 16, 10, 30)
    assert datum_kort(dt) == "ma 16 nov"


def test_datum_kort_all_weekdays() -> None:
    expected = ["ma", "di", "wo", "do", "vr", "za", "zo"]
    for i, wd in enumerate(expected):
        d = date(2026, 11, 16 + i)  # Mon–Sun
        assert datum_kort(d).startswith(wd)


def test_relatief_today() -> None:
    d = date(2026, 11, 16)
    assert relatief(d, today=d) == "vandaag"


def test_relatief_tomorrow() -> None:
    d = date(2026, 11, 17)
    assert relatief(d, today=date(2026, 11, 16)) == "morgen"


def test_relatief_yesterday() -> None:
    d = date(2026, 11, 15)
    assert relatief(d, today=date(2026, 11, 16)) == "gisteren"


def test_relatief_future_n_days() -> None:
    d = date(2026, 11, 19)  # 3 days ahead
    assert relatief(d, today=date(2026, 11, 16)) == "over 3 dagen"


def test_relatief_past_n_days() -> None:
    d = date(2026, 11, 10)  # 6 days ago
    assert relatief(d, today=date(2026, 11, 16)) == "6 dagen geleden"


def test_relatief_tomorrow_from_future() -> None:
    d = date(2026, 12, 25)
    assert relatief(d, today=date(2026, 12, 24)) == "morgen"


def test_relatief_yesterday_from_past() -> None:
    d = date(2026, 1, 1)
    assert relatief(d, today=date(2026, 1, 2)) == "gisteren"


def test_relatief_defaults_to_real_clock() -> None:
    today = today_local()  # Amsterdam's today, not the container's (UTC) date
    assert relatief(today) == "vandaag"
