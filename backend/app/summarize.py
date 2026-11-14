"""Meeting transcript summariser via the local LLM (SPEC 7.5).

``summarize(transcript, client) -> Summary`` sends a Dutch system prompt and
the transcript text to ``chat_json()``.  One retry on bad output (``LlmError``);
raises ``SummaryError`` after the second failure.

Long transcripts (SPEC 7.6): when the transcript exceeds ``SUMMARY_CHUNK_CHARS``
it is split at turn boundaries (one ``\n``-separated line per turn from
``as_text``), each part is summarised, then a merge call combines all partial
JSON results into one ``Summary``.
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel

from app.config import get_settings
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

MERGE_SYSTEM_PROMPT = (
    "Je bent de notulist van een studenten-scrumteam. "
    "Hieronder staan deelsamenvattingen van verschillende delen van een meeting. "
    "Voeg ze samen tot een enkele, coherente samenvatting in het Nederlands. "
    "Gebruik alleen informatie uit de deelsamenvattingen. "
    "Geen duplicaten, geen contradicties. "
    "Hetzelfde JSON-schema als de originele samenvatting."
)


def summarize(transcript: str, client: httpx.Client | None = None) -> Summary:
    """Summarise *transcript* via the LLM and return a ``Summary``.

    Retries once when ``chat_json`` raises ``LlmError`` (bad output).
    Raises ``SummaryError`` after the second failure.

    When *transcript* exceeds ``SUMMARY_CHUNK_CHARS`` (SPEC 7.6):
    the text is split at turn boundaries (``\\n`` lines), each part is
    summarised independently, then a merge call combines the partial
    JSON results.
    """
    settings = get_settings()
    max_chars = settings.SUMMARY_CHUNK_CHARS

    # Short transcript — single call
    if len(transcript) <= max_chars:
        return _single_call(transcript, client)

    # Long transcript — chunk at turn boundaries (SPEC 7.6)
    lines = transcript.split("\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1  # +1 for the newline
        if current and current_len + line_len > max_chars:
            # Flush current chunk
            chunks.append("\n".join(current))
            current = []
            current_len = 0
        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))

    # Summarise each chunk
    partial_results: list[dict[str, Any]] = []
    for chunk in chunks:
        partial_results.append(_summarise_chunk(chunk, client))

    # Merge partial results
    return _merge_results(partial_results, client)


def _single_call(
    transcript: str, client: httpx.Client | None
) -> Summary:
    """One LLM call for a transcript that fits within the chunk limit."""
    schema = _MeetingSummary.model_json_schema()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": transcript},
    ]

    for attempt in range(2):
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

    raise SummaryError("Summarization failed after 2 attempts")


def _summarise_chunk(
    chunk: str, client: httpx.Client | None
) -> dict[str, Any]:
    """Summarise one chunk of the transcript. Returns raw dict from LLM."""
    schema = _MeetingSummary.model_json_schema()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": chunk},
    ]

    for attempt in range(2):
        try:
            result = chat_json(messages, schema, client=client)
        except LlmError:
            if attempt == 0:
                continue
            raise SummaryError("Summarization failed after 2 attempts") from None

        return result

    raise SummaryError("Summarization failed after 2 attempts")


def _merge_results(
    partial_results: list[dict[str, Any]], client: httpx.Client | None
) -> Summary:
    """Merge partial JSON summaries into one ``Summary`` (SPEC 7.6)."""
    schema = _MeetingSummary.model_json_schema()
    combined = "\n\n".join(
        f"Deelsamenvatting {i+1}:\n{_partial_to_text(p)}"
        for i, p in enumerate(partial_results)
    )
    messages = [
        {"role": "system", "content": MERGE_SYSTEM_PROMPT},
        {"role": "user", "content": combined},
    ]

    for attempt in range(2):
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

    raise SummaryError("Summarization failed after 2 attempts")


def _partial_to_text(partial: dict[str, Any]) -> str:
    """Convert a partial result dict to a readable text for the merge prompt."""
    parts: list[str] = []
    if partial.get("summary"):
        parts.append(f"- Samenvatting: {partial['summary']}")
    for d in partial.get("decisions", []):
        parts.append(f"- Besluit: {d}")
    for item in partial.get("action_items", []):
        owner = item.get("owner") or "—"
        task = item.get("task", "")
        due = item.get("due") or "—"
        parts.append(f"- Actiepunt: {owner} → {task} ({due})")
    for q in partial.get("open_questions", []):
        parts.append(f"- Open vraag: {q}")
    return "\n".join(parts)
