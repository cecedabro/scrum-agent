"""Tests for app/cards.py – card shape, Dutch text, JSON serialisability."""

from __future__ import annotations

import json
from datetime import date, time

from app.cards import (
    deadline_reminder,
    sprint_nudge,
    test_card,
    weekly_overview,
)


def _mk_dl(
    due_date: date,
    due_time: time | None = None,
    title: str = "Taak",
    note: str | None = None,
) -> dict:
    return {
        "title": title,
        "due_date": due_date,
        "due_time": due_time,
        "note": note,
    }


# ------------------------------------------------------------------
# test_card
# ------------------------------------------------------------------


class TestTestCard:
    def test_has_version_1_4(self) -> None:
        card = test_card()
        assert card["version"] == "1.4"
        assert card["type"] == "AdaptiveCard"

    def test_has_textblock_body(self) -> None:
        card = test_card()
        body = card["body"]
        assert len(body) == 1
        assert body[0]["type"] == "TextBlock"

    def test_text_is_dutch(self) -> None:
        card = test_card()
        assert card["body"][0]["text"] == "Testbericht van de scrum agent"

    def test_wrap_true(self) -> None:
        card = test_card()
        assert card["body"][0]["wrap"] is True

    def test_is_json_serializable(self) -> None:
        card = test_card()
        json.dumps(card)  # raises if not serializable


# ------------------------------------------------------------------
# weekly_overview
# ------------------------------------------------------------------


class TestWeeklyOverview:
    def test_no_deadlines_shorthand(self) -> None:
        week_start = date(2026, 11, 16)
        card = weekly_overview(week_start, [])
        facts = card["body"][1]["facts"]
        assert facts[0]["factValue"] == "Geen deadlines deze week"

    def test_fact_date_format(self) -> None:
        week_start = date(2026, 11, 16)
        dl = _mk_dl(date(2026, 11, 16), time(23, 59), title="Verslag")
        card = weekly_overview(week_start, [dl])
        facts = card["body"][1]["facts"]
        assert facts[0]["factTitle"] == "ma 16 nov 23:59"
        assert facts[0]["factValue"] == "Verslag"

    def test_fact_no_time_defaults_to_23_59(self) -> None:
        week_start = date(2026, 11, 16)
        dl = _mk_dl(date(2026, 11, 17), title="Opdracht")
        card = weekly_overview(week_start, [dl])
        facts = card["body"][1]["facts"]
        assert facts[0]["factTitle"] == "di 17 nov 23:59"

    def test_week_number_in_title(self) -> None:
        # Monday 2026-11-16 is ISO week 47
        week_start = date(2026, 11, 16)
        card = weekly_overview(week_start, [])
        assert card["body"][0]["text"] == "Deadlines deze week (week 47)"

    def test_multiple_deadlines(self) -> None:
        week_start = date(2026, 11, 16)
        dls = [
            _mk_dl(date(2026, 11, 16), time(9, 0), title="Eerste"),
            _mk_dl(date(2026, 11, 17), time(14, 30), title="Tweede"),
        ]
        card = weekly_overview(week_start, dls)
        facts = card["body"][1]["facts"]
        assert len(facts) == 2
        assert facts[0]["factTitle"] == "ma 16 nov 09:00"
        assert facts[1]["factTitle"] == "di 17 nov 14:30"

    def test_wrap_on_all_elements(self) -> None:
        week_start = date(2026, 11, 16)
        card = weekly_overview(week_start, [])
        assert card["body"][0]["wrap"] is True
        assert card["body"][1]["wrap"] is True

    def test_is_json_serializable(self) -> None:
        week_start = date(2026, 11, 16)
        card = weekly_overview(week_start, [_mk_dl(date(2026, 11, 16), title="X")])
        json.dumps(card)


# ------------------------------------------------------------------
# deadline_reminder
# ------------------------------------------------------------------


class TestDeadlineReminder:
    def test_day_0_is_vandaag(self) -> None:
        dl = _mk_dl(date(2026, 11, 16), title="Taak")
        card = deadline_reminder(dl, 0)
        assert card["body"][0]["text"] == "Herinnering: Taak is vandaag"

    def test_day_1_is_morgen(self) -> None:
        dl = _mk_dl(date(2026, 11, 17), title="Opdracht")
        card = deadline_reminder(dl, 1)
        assert card["body"][0]["text"] == "Herinnering: Opdracht is morgen"

    def test_day_2_is_over_n_dagen(self) -> None:
        dl = _mk_dl(date(2026, 11, 18), title="Verslag")
        card = deadline_reminder(dl, 2)
        assert card["body"][0]["text"] == "Herinnering: Verslag is over 2 dagen"

    def test_day_5_is_over_5_dagen(self) -> None:
        dl = _mk_dl(date(2026, 11, 21), title="Laatste")
        card = deadline_reminder(dl, 5)
        assert card["body"][0]["text"] == "Herinnering: Laatste is over 5 dagen"

    def test_shows_date_and_time(self) -> None:
        dl = _mk_dl(date(2026, 11, 16), time(23, 59), title="X")
        card = deadline_reminder(dl, 0)
        assert "Datum: ma 16 nov, Tijd: 23:59" in card["body"][1]["text"]

    def test_shows_date_without_time(self) -> None:
        dl = _mk_dl(date(2026, 11, 17), title="X")
        card = deadline_reminder(dl, 1)
        assert "Datum: di 17 nov" in card["body"][1]["text"]
        assert "Tijd" not in card["body"][1]["text"]

    def test_shows_note(self) -> None:
        dl = _mk_dl(date(2026, 11, 16), title="X", note="Belangrijk!")
        card = deadline_reminder(dl, 0)
        assert card["body"][2]["text"] == "Belangrijk!"

    def test_no_note_skips_note_block(self) -> None:
        dl = _mk_dl(date(2026, 11, 16), title="X")
        card = deadline_reminder(dl, 0)
        assert len(card["body"]) == 2

    def test_wrap_on_all_elements(self) -> None:
        dl = _mk_dl(date(2026, 11, 16), title="X")
        card = deadline_reminder(dl, 0)
        for el in card["body"]:
            assert el["wrap"] is True

    def test_is_json_serializable(self) -> None:
        dl = _mk_dl(date(2026, 11, 16), time(9, 0), title="X", note="Notitie")
        card = deadline_reminder(dl, 2)
        json.dumps(card)


# ------------------------------------------------------------------
# sprint_nudge
# ------------------------------------------------------------------


class TestSprintNudge:
    def test_title_with_weekday_and_date(self) -> None:
        end = date(2026, 11, 20)  # Friday
        card = sprint_nudge(end, [])
        assert card["body"][0]["text"] == "De sprint eindigt vrijdag 20 november"

    def test_lists_deadlines_in_facts(self) -> None:
        end = date(2026, 11, 20)
        dl = _mk_dl(date(2026, 11, 18), time(17, 0), title="Taak")
        card = sprint_nudge(end, [dl])
        facts = card["body"][1]["facts"]
        assert facts[0]["factTitle"] == "wo 18 nov 17:00"
        assert facts[0]["factValue"] == "Taak"

    def test_no_deadlines_message(self) -> None:
        end = date(2026, 11, 20)
        card = sprint_nudge(end, [])
        assert card["body"][1]["text"] == "Geen open deadlines."

    def test_nudge_text(self) -> None:
        end = date(2026, 11, 20)
        card = sprint_nudge(end, [])
        assert card["body"][2]["text"] == "Update het sprintboard en controleer je taken."

    def test_wrap_on_all_elements(self) -> None:
        end = date(2026, 11, 20)
        card = sprint_nudge(end, [])
        for el in card["body"]:
            assert el["wrap"] is True

    def test_is_json_serializable(self) -> None:
        end = date(2026, 11, 20)
        card = sprint_nudge(end, [_mk_dl(date(2026, 11, 18), title="X")])
        json.dumps(card)
