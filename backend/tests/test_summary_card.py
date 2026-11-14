"""Tests for cards.summary_card — pure function, no I/O.

Tests: title+date format, sections present/absent, action items with and
without owner/due, empty lists left out, closing footer line, JSON
serialisability.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from app.cards import summary_card


@dataclass
class _SummaryJob:
    """Lightweight Job-like object for testing."""

    id: int
    title: str
    meeting_date: date | None
    result: dict | None = None


def _job(
    title: str = "Team stand-up",
    meeting_date: date | None = None,
    result: dict | None = None,
) -> _SummaryJob:
    return _SummaryJob(
        id=1,
        title=title,
        meeting_date=meeting_date or date(2026, 11, 16),
        result=result,
    )


# ------------------------------------------------------------------
# Title and date
# ------------------------------------------------------------------


class TestTitleDate:
    def test_card_is_adaptive_card(self) -> None:
        card = summary_card(_job())
        assert card["type"] == "AdaptiveCard"
        assert card["version"] == "1.4"

    def test_title_in_first_textblock(self) -> None:
        card = summary_card(_job())
        assert card["body"][0]["text"] == "Samenvatting: Team stand-up (ma 16 nov)"

    def test_title_without_date(self) -> None:
        job = _SummaryJob(id=1, title="Team stand-up", meeting_date=None)  # type: ignore[arg-type]
        card = summary_card(job)
        assert card["body"][0]["text"] == "Samenvatting: Team stand-up"

    def test_title_custom(self) -> None:
        card = summary_card(_job(title="Sprint planning"))
        assert card["body"][0]["text"] == "Samenvatting: Sprint planning (ma 16 nov)"

    def test_wrap_true_on_title(self) -> None:
        card = summary_card(_job())
        assert card["body"][0]["wrap"] is True

    def test_is_json_serializable(self) -> None:
        card = summary_card(_job())
        json.dumps(card)


# ------------------------------------------------------------------
# Summary section
# ------------------------------------------------------------------


class TestSummarySection:
    def test_summary_text_shown(self) -> None:
        j = _job(result={
            "summary": "Iets besproken.",
            "decisions": [],
            "action_items": [],
            "open_questions": [],
        })
        card = summary_card(j)
        assert card["body"][1]["text"] == "Iets besproken."

    def test_summary_wrap_true(self) -> None:
        j = _job(result={
            "summary": "Foo",
            "decisions": [],
            "action_items": [],
            "open_questions": [],
        })
        card = summary_card(j)
        assert card["body"][1]["wrap"] is True


# ------------------------------------------------------------------
# Decisions
# ------------------------------------------------------------------


class TestDecisions:
    def test_decisions_shown_as_bullets(self) -> None:
        j = _job(
            result={
                "summary": "Foo",
                "decisions": ["Besluit A", "Besluit B"],
                "action_items": [],
                "open_questions": [],
            }
        )
        card = summary_card(j)
        # Title (0), Summary (1), Decisions heading (2), bullets (3,4)
        assert card["body"][2]["text"] == "Besluiten"
        assert card["body"][3]["text"] == "- Besluit A"
        assert card["body"][4]["text"] == "- Besluit B"

    def test_decisions_heading_bold_small(self) -> None:
        j = _job(
            result={
                "summary": "Foo",
                "decisions": ["X"],
                "action_items": [],
                "open_questions": [],
            }
        )
        card = summary_card(j)
        assert card["body"][2]["weight"] == "Bolder"
        assert card["body"][2]["size"] == "Small"

    def test_empty_decisions_left_out(self) -> None:
        j = _job(
            result={
                "summary": "Foo",
                "decisions": [],
                "action_items": [],
                "open_questions": [],
            }
        )
        card = summary_card(j)
        text_blocks = [b["text"] for b in card["body"]]
        assert "Besluiten" not in text_blocks

    def test_no_summary_no_decisions(self) -> None:
        j = _job(
            result={
                "summary": "",
                "decisions": [],
                "action_items": [],
                "open_questions": [],
            }
        )
        card = summary_card(j)
        # Only title (0) then footer
        assert card["body"][0]["text"] == "Samenvatting: Team stand-up (ma 16 nov)"
        assert "Besluiten" not in [b["text"] for b in card["body"]]


# ------------------------------------------------------------------
# Action items
# ------------------------------------------------------------------


class TestActionItems:
    def test_with_owner_and_due(self) -> None:
        j = _job(
            result={
                "summary": "Foo",
                "decisions": [],
                "action_items": [{"owner": "Jan", "task": "Notulen", "due": "2026-11-18"}],
                "open_questions": [],
            }
        )
        card = summary_card(j)
        # Title(0), Summary(1), Actiepunten(2), bullet(3)
        assert card["body"][2]["text"] == "Actiepunten"
        assert card["body"][3]["text"] == "- Jan: Notulen (2026-11-18)"

    def test_with_owner_no_due(self) -> None:
        j = _job(
            result={
                "summary": "Foo",
                "decisions": [],
                "action_items": [{"owner": "Jan", "task": "Notulen"}],
                "open_questions": [],
            }
        )
        card = summary_card(j)
        assert card["body"][3]["text"] == "- Jan: Notulen"

    def test_no_owner_with_due(self) -> None:
        j = _job(
            result={
                "summary": "Foo",
                "decisions": [],
                "action_items": [{"task": "Notulen", "due": "2026-11-18"}],
                "open_questions": [],
            }
        )
        card = summary_card(j)
        assert card["body"][3]["text"] == "- —: Notulen (2026-11-18)"

    def test_no_owner_no_due(self) -> None:
        j = _job(
            result={
                "summary": "Foo",
                "decisions": [],
                "action_items": [{"task": "Notulen"}],
                "open_questions": [],
            }
        )
        card = summary_card(j)
        assert card["body"][3]["text"] == "- —: Notulen"

    def test_multiple_action_items(self) -> None:
        j = _job(
            result={
                "summary": "Foo",
                "decisions": [],
                "action_items": [
                    {"owner": "A", "task": "X"},
                    {"owner": "B", "task": "Y", "due": "vrijdag"},
                ],
                "open_questions": [],
            }
        )
        card = summary_card(j)
        assert card["body"][3]["text"] == "- A: X"
        assert card["body"][4]["text"] == "- B: Y (vrijdag)"

    def test_empty_action_items_left_out(self) -> None:
        j = _job(
            result={
                "summary": "Foo",
                "decisions": [],
                "action_items": [],
                "open_questions": [],
            }
        )
        card = summary_card(j)
        text_blocks = [b["text"] for b in card["body"]]
        assert "Actiepunten" not in text_blocks

    def test_action_items_heading_bold_small(self) -> None:
        j = _job(
            result={
                "summary": "Foo",
                "decisions": [],
                "action_items": [{"task": "X"}],
                "open_questions": [],
            }
        )
        card = summary_card(j)
        assert card["body"][2]["weight"] == "Bolder"
        assert card["body"][2]["size"] == "Small"


# ------------------------------------------------------------------
# Open questions
# ------------------------------------------------------------------


class TestOpenQuestions:
    def test_open_questions_shown(self) -> None:
        j = _job(
            result={
                "summary": "Foo",
                "decisions": [],
                "action_items": [],
                "open_questions": ["Wat met sprint 5?"],
            }
        )
        card = summary_card(j)
        # Title(0), Summary(1), Open vragen(2), bullet(3)
        assert card["body"][2]["text"] == "Open vragen"
        assert card["body"][3]["text"] == "- Wat met sprint 5?"

    def test_empty_open_questions_left_out(self) -> None:
        j = _job(
            result={
                "summary": "Foo",
                "decisions": [],
                "action_items": [],
                "open_questions": [],
            }
        )
        card = summary_card(j)
        text_blocks = [b["text"] for b in card["body"]]
        assert "Open vragen" not in text_blocks


# ------------------------------------------------------------------
# Footer
# ------------------------------------------------------------------


class TestFooter:
    def test_closing_line_present(self) -> None:
        card = summary_card(_job())
        last = card["body"][-1]
        assert last["text"] == "Gemaakt door het lokale taalmodel; controleer de actiepunten."

    def test_footer_is_subtle(self) -> None:
        card = summary_card(_job())
        last = card["body"][-1]
        assert last["isSubtle"] is True
        assert last["size"] == "Small"

    def test_footer_wrap(self) -> None:
        card = summary_card(_job())
        last = card["body"][-1]
        assert last["wrap"] is True


# ------------------------------------------------------------------
# JSON serialisability
# ------------------------------------------------------------------


class TestJsonSerializable:
    def test_full_card_serializable(self) -> None:
        j = _job(
            result={
                "summary": "Een korte samenvatting van de vergadering.",
                "decisions": ["We kiezen voor optie B"],
                "action_items": [
                    {"owner": "Jan", "task": "Notulen maken", "due": "2026-11-18"},
                    {"task": "Bijlagen delen"},
                ],
                "open_questions": ["Wat met sprint 5?"],
            }
        )
        card = summary_card(j)
        json.dumps(card)  # raises if not serializable

    def test_empty_card_serializable(self) -> None:
        card = summary_card(_job())
        json.dumps(card)
