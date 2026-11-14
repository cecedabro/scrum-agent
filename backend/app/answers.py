"""Quick (no-LLM) answers for Teams questions.

Implements SPEC 10.3: pattern-match cleaned Teams messages and return
a Dutch reply without consulting the language model.  Returns ``None``
when the question should be forwarded to the model (SPEC 10.4).

``quick_answer(text, today, deadlines, sprint_end) -> str | None``

*text* — cleaned, lowercased question body.
*today* — ``date`` representing the current local day.
*deadlines* — list of dicts with ``title`` (str), ``due_date`` (date),
    ``due_time`` (str or None), ``relatief`` (str).
*sprint_end* — ``date`` of the sprint end or ``None``.
"""

from datetime import date, timedelta
from typing import Any

from app.fmt import datum_kort, relatief


def quick_answer(
    text: str,
    today: date,
    deadlines: list[dict[str, Any]],
    sprint_end: date | None,
) -> str | None:
    """Return a Dutch reply for recognised question patterns.

    Returns ``None`` when the question is not recognised and should be
    forwarded to the language model (SPEC 10.4).
    """
    low = text.strip().lower()

    # Help — SPEC 10.3 (empty / help / hulp)
    if not low or low in ("help", "hulp"):
        return (
            "Ik kan helpen met:\n\n"
            "- **help** / **hulp**: deze lijst\n"
            "- **deadlines** / **wat zijn de deadlines?**: aankomende deadlines\n"
            "- **deadlines deze week**: deadlines van deze maandag t/m zondag\n"
            "- **sprint**: einde huidige sprint\n\n"
            "Stel je vraag en ik denk er even over na."
        )

    # Sprint — SPEC 10.3 (contains "sprint")
    if "sprint" in low:
        if sprint_end:
            rel = relatief(sprint_end, today=today)
            return f"De sprint eindigt {sprint_end} ({rel})."
        return "Er is geen sprint ingesteld."

    # Deadlines — SPEC 10.3 (contains "deadline")
    if "deadline" in low:
        if "week" in low:
            # Deadlines today → Sunday of this week
            monday = today - timedelta(days=today.weekday())
            sunday = monday + timedelta(days=6)
            shown = [d for d in deadlines if monday <= d["due_date"] <= sunday]
        else:
            # Upcoming deadlines (today and later)
            shown = [d for d in deadlines if d["due_date"] >= today]

        if not shown:
            if "week" in low:
                return "Geen deadlines meer deze week."
            return "Er staan geen deadlines gepland."

        cap = 10
        lines = []
        for d in shown[:cap]:
            time_str = d.get("due_time") or ""
            parts = [datum_kort(d["due_date"])]
            if time_str:
                parts.append(time_str)
            parts.append("—")
            parts.append(d["title"])
            parts.append(f"({d['relatief']})")
            lines.append(f"- {' '.join(parts)}")

        if len(shown) > cap:
            lines.append(f"- … en {len(shown) - cap} meer")

        return "\n".join(lines)

    # Not recognised — forward to model (SPEC 10.4)
    return None
