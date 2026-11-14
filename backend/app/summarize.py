"""Meeting transcript summariser via the local LLM (SPEC 7.5).

``summarize(transcript, client) -> Summary`` sends a Dutch system prompt and
the transcript text to ``chat_json()``.  One retry on bad output (``LlmError``);
raises ``SummaryError`` after the second failure.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel

from app.llm import LlmError, chat_json
from app.llm import MeetingSummary as _MeetingSummary


class SummaryError(Exception):
    """Raised when summarization fails after retry."""


class Summary(BaseModel):
    """Structured summary matching the LLM JSON schema (SPEC 7.5)."""

    summary: str
    decisions: list[str]
    action_items: list[dict[str, Any | None]]
    open_questions: list[str]


SYSTEM_PROMPT = (
    "Je bent de notulist van een studenten-scrumteam. "
    "Vat het volgende meetingtranscript samen in het Nederlands. "
    "Geef alleen besluiten die echt genomen zijn. "
    "Actiepunten alleen met eigenaar en deadline als genoemd. "
    "Open vragen opnemen. Niets verzinnen."
)


def summarize(transcript: str, client: httpx.Client | None = None) -> Summary:
    """Summarise *transcript* via the LLM and return a ``Summary``.

    Retries once when ``chat_json`` raises ``LlmError`` (bad output).
    Raises ``SummaryError`` after the second failure.
    """
    schema = _MeetingSummary.model_json_schema()

    for attempt in range(2):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": transcript},
        ]

        try:
            result = chat_json(messages, schema, client=client)
        except LlmError:
            if attempt == 0:
                continue
            raise SummaryError("Summarization failed after 2 attempts") from None

        return Summary(
            summary=result.get("summary", ""),
            decisions=result.get("decisions", []),
            action_items=result.get("action_items", []),
            open_questions=result.get("open_questions", []),
        )

    # Second attempt also failed — should be caught above, but just in case.
    raise SummaryError("Summarization failed after 2 attempts")
