"""Teams Adaptive Cards – pure functions, no I/O.

Each function returns the card ``content`` dict (version 1.4);
``teams.envelope()`` wraps it in the Teams message shape.
"""

from __future__ import annotations

import datetime
from datetime import date
from typing import TYPE_CHECKING, cast

from app.fmt import datum, datum_kort

if TYPE_CHECKING:
    from app.models import Job

_Dict = dict[str, object]


def _time_str(value: datetime.time | None, default: str = "23:59") -> str:
    """Return ``HH:MM`` from a time value, or *default*."""
    if value is None:
        return default
    return value.strftime("%H:%M")


def test_card() -> _Dict:
    """A simple test card."""
    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": "Testbericht van de scrum agent",
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            }
        ],
    }


def weekly_overview(week_start: date, deadlines: list[dict[str, object]]) -> _Dict:
    """Weekly overview card.

    *deadlines* is a list of dicts with keys ``title``, ``due_date`` and
    optionally ``due_time``.
    """
    week_number = week_start.isocalendar()[1]

    facts: list[dict[str, str]] = []
    if not deadlines:
        facts.append(
            {
                "factTitle": "Status",
                "factValue": "Geen deadlines deze week",
            }
        )
    else:
        for dl in deadlines:
            due = cast(date, dl["due_date"])
            label = f"{datum_kort(due)} {_time_str(cast(datetime.time | None, dl.get('due_time')))}"
            facts.append({"factTitle": label, "factValue": str(dl["title"])})

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": [
            {
                "type": "TextBlock",
                "text": f"Deadlines deze week (week {week_number})",
                "weight": "Bolder",
                "size": "Medium",
                "wrap": True,
            },
            {"type": "FactSet", "facts": facts, "wrap": True},
        ],
    }


def deadline_reminder(deadline: dict[str, object], days: int) -> _Dict:
    """Reminder card for a single deadline.

    *days* is the number of days after today (0 = today, 1 = tomorrow).
    """
    title = deadline["title"]

    if days == 0:
        rel = "vandaag"
    elif days == 1:
        rel = "morgen"
    else:
        rel = f"over {days} dagen"

    header = f"Herinnering: {title} is {rel}"

    due_date = cast(date, deadline["due_date"])
    due_time = cast(datetime.time | None, deadline.get("due_time"))

    date_time = f"Datum: {datum_kort(due_date)}"
    if due_time is not None:
        date_time += f", Tijd: {_time_str(due_time)}"

    note = deadline.get("note")

    body: list[_Dict] = [
        {
            "type": "TextBlock",
            "text": header,
            "weight": "Bolder",
            "size": "Medium",
            "wrap": True,
        },
        {"type": "TextBlock", "text": date_time, "wrap": True},
    ]
    if note:
        body.append({"type": "TextBlock", "text": note, "wrap": True})

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
    }


def summary_card(job: Job) -> _Dict:
    """Summary card for a finished meeting job (SPEC 7.8).

    Pure function — no I/O.  Takes a ``Job`` object and returns the
    card content dict (AdaptiveCard 1.4).
    """
    result = job.result or {}
    title = job.title
    meeting_date = job.meeting_date
    date_str = datum_kort(meeting_date) if meeting_date else ""
    date_part = f" ({date_str})" if date_str else ""
    title_text = f"Samenvatting: {title}{date_part}"

    summary_text = result.get("summary", "") or ""
    decisions = result.get("decisions", []) or []
    action_items = result.get("action_items", []) or []
    open_questions = result.get("open_questions", []) or []

    body: list[_Dict] = [
        {
            "type": "TextBlock",
            "text": title_text,
            "weight": "Bolder",
            "size": "Medium",
            "wrap": True,
        },
    ]

    if summary_text:
        body.append(
            {
                "type": "TextBlock",
                "text": summary_text,
                "wrap": True,
            }
        )

    if decisions:
        body.append(
            {
                "type": "TextBlock",
                "text": "Besluiten",
                "weight": "Bolder",
                "size": "Small",
                "wrap": True,
            }
        )
        for d in decisions:
            body.append(
                {
                    "type": "TextBlock",
                    "text": f"- {d}",
                    "wrap": True,
                }
            )

    if action_items:
        body.append(
            {
                "type": "TextBlock",
                "text": "Actiepunten",
                "weight": "Bolder",
                "size": "Small",
                "wrap": True,
            }
        )
        for item in action_items:
            owner = item.get("owner") or "—"
            task = item.get("task", "")
            due = item.get("due")
            if due:
                body.append(
                    {
                        "type": "TextBlock",
                        "text": f"- {owner}: {task} ({due})",
                        "wrap": True,
                    }
                )
            else:
                body.append(
                    {
                        "type": "TextBlock",
                        "text": f"- {owner}: {task}",
                        "wrap": True,
                    }
                )

    if open_questions:
        body.append(
            {
                "type": "TextBlock",
                "text": "Open vragen",
                "weight": "Bolder",
                "size": "Small",
                "wrap": True,
            }
        )
        for q in open_questions:
            body.append(
                {
                    "type": "TextBlock",
                    "text": f"- {q}",
                    "wrap": True,
                }
            )

    body.append(
        {
            "type": "TextBlock",
            "text": "Gemaakt door het lokale taalmodel; controleer de actiepunten.",
            "size": "Small",
            "isSubtle": True,
            "wrap": True,
        }
    )

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
    }


def sprint_nudge(end_date: date, deadlines: list[dict[str, object]]) -> _Dict:
    """Sprint end nudge card.

    Lists open deadlines until *end_date*.
    """
    header = f"De sprint eindigt {datum(end_date)}"

    body: list[_Dict] = [
        {
            "type": "TextBlock",
            "text": header,
            "weight": "Bolder",
            "size": "Medium",
            "wrap": True,
        }
    ]

    if deadlines:
        facts: list[dict[str, str]] = []
        for dl in deadlines:
            due = cast(date, dl["due_date"])
            label = f"{datum_kort(due)} {_time_str(cast(datetime.time | None, dl.get('due_time')))}"
            facts.append({"factTitle": label, "factValue": str(dl["title"])})
        body.append({"type": "FactSet", "facts": facts, "wrap": True})
    else:
        body.append({"type": "TextBlock", "text": "Geen open deadlines.", "wrap": True})

    body.append(
        {
            "type": "TextBlock",
            "text": "Update het sprintboard en controleer je taken.",
            "wrap": True,
        }
    )

    return {
        "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
        "type": "AdaptiveCard",
        "version": "1.4",
        "body": body,
    }
