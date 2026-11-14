"""Tests for quick_answer (SPEC 10.3)."""

from datetime import date, timedelta

from app.answers import quick_answer

Mon = date(2026, 11, 9)  # Monday 9 Nov 2026
Tue = date(2026, 11, 10)
Wed = date(2026, 11, 11)
Thu = date(2026, 11, 12)
Fri = date(2026, 11, 13)
Sun = date(2026, 11, 15)  # Sunday 15 Nov 2026
NextMon = date(2026, 11, 16)


def _d(title, due_date, due_time=None, today=Mon):
    """Build a deadline dict like the app would."""
    delta = (due_date - today).days
    if delta < 0:
        label = "verlopen"
    elif delta == 0:
        label = "vandaag"
    elif delta == 1:
        label = "morgen"
    elif delta <= 7:
        label = f"over {delta} dagen"
    else:
        label = f"over {delta} dagen"

    d = {"title": title, "due_date": due_date, "relatief": label}
    if due_time is not None:
        d["due_time"] = due_time
    return d


# ── Help ────────────────────────────────────────────────────────────────


def test_empty_text_returns_help():
    result = quick_answer("", Mon, [], None)
    assert result is not None
    assert "help" in result
    assert "hulp" in result
    assert "sprint" in result


def test_help_keyword():
    result = quick_answer("help", Mon, [], None)
    assert result is not None
    assert "help" in result


def test_hulp_keyword():
    result = quick_answer("hulp", Mon, [], None)
    assert result is not None
    assert "help" in result


def test_hulp_uppercase():
    result = quick_answer("HULP", Mon, [], None)
    assert result is not None
    assert "help" in result


# ── Deadlines (generic) ────────────────────────────────────────────────


def test_deadline_upcoming():
    dl1 = _d("Opdracht 1", Tue, "23:59")
    dl2 = _d("Opdracht 2", Thu, "17:00")
    result = quick_answer("wat zijn de deadlines?", Mon, [dl1, dl2], None)
    assert result is not None
    assert "Opdracht 1" in result
    assert "Opdracht 2" in result


def test_deadline_no_time():
    dl1 = _d("Opdracht 1", Tue)
    result = quick_answer("wat zijn de deadlines?", Mon, [dl1], None)
    assert result is not None
    assert "Opdracht 1" in result


def test_deadline_past_not_shown():
    past = _d("Verlopen", Mon - timedelta(days=1))
    result = quick_answer("wat zijn de deadlines?", Mon, [past], None)
    assert result is not None
    assert "Er staan geen deadlines gepland" in result


def test_deadline_empty_list():
    result = quick_answer("wat zijn de deadlines?", Mon, [], None)
    assert result is not None
    assert "Er staan geen deadlines gepland" in result


# ── Deadlines this week ────────────────────────────────────────────────


def test_deadline_week_monday():
    # Monday 9 Nov, week runs 9–15 Nov
    dl1 = _d("Opdracht 1", Wed, "23:59")
    dl2 = _d("Opdracht 2", Sun)
    result = quick_answer("deadlines deze week", Mon, [dl1, dl2], None)
    assert result is not None
    assert "Opdracht 1" in result
    assert "Opdracht 2" in result


def test_deadline_week_sunday():
    # Sunday 15 Nov, week runs 9–15 Nov
    dl1 = _d("Opdracht 1", NextMon, "23:59")  # next Monday, outside week
    dl2 = _d("Opdracht 2", Fri)
    result = quick_answer("deadlines deze week", Sun, [dl1, dl2], None)
    assert result is not None
    assert "Opdracht 1" not in result
    assert "Opdracht 2" in result


def test_deadline_week_no_deadlines():
    result = quick_answer("deadlines deze week", Mon, [_d("Verlopen", NextMon)], None)
    assert result is not None
    assert "Geen deadlines meer deze week" in result


# ── 10-line cap ────────────────────────────────────────────────────────


def test_deadline_cap():
    deadlines = [_d(f"Opdracht {i}", Mon + timedelta(days=i), "23:59")
                 for i in range(1, 16)]  # 15 deadlines
    result = quick_answer("wat zijn de deadlines?", Mon, deadlines, None)
    assert result is not None
    lines = result.split("\n")
    # 10 deadline lines + 1 "… en N meer" = 11
    assert len(lines) == 11
    assert "… en 5 meer" in result


# ── Sprint ─────────────────────────────────────────────────────────────


def test_sprint_on():
    sprint_end = Fri
    result = quick_answer("sprint", Mon, [], sprint_end)
    assert result is not None
    assert sprint_end.isoformat() in result
    assert "over" in result or "morgen" in result or "vandaag" in result


def test_sprint_off():
    result = quick_answer("sprint", Mon, [], None)
    assert result is not None
    assert "geen sprint" in result


def test_sprint_keyword_case_insensitive():
    result = quick_answer("SPRINT EINDE", Mon, [], Fri)
    assert result is not None
    assert Fri.isoformat() in result


# ── Fallback to model ─────────────────────────────────────────────────


def test_unrecognised_returns_none():
    result = quick_answer("waarom is de hemel blauw?", Mon, [], None)
    assert result is None


def test_unrecognised_with_deadlines_returns_none():
    dl = _d("Opdracht 1", Tue)
    result = quick_answer("hoe laat begint de les?", Mon, [dl], None)
    assert result is None


# ── Format checks ──────────────────────────────────────────────────────


def test_deadline_format_has_date_short():
    dl = _d("Opdracht 1", Tue, "23:59")
    result = quick_answer("wat zijn de deadlines?", Mon, [dl], None)
    assert result is not None
    # datum_kort for 2026-11-10 (Tuesday) = "di 10 nov"
    assert "di 10 nov" in result


def test_deadline_format_has_time():
    dl = _d("Opdracht 1", Tue, "23:59")
    result = quick_answer("wat zijn de deadlines?", Mon, [dl], None)
    assert "23:59" in result


def test_deadline_format_has_relief():
    dl = _d("Opdracht 1", Tue, "23:59")
    result = quick_answer("wat zijn de deadlines?", Mon, [dl], None)
    assert "(morgen)" in result
