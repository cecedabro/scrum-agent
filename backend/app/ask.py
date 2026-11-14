"""Ask a question via the local LLM (TASK T49).

Builds a Dutch prompt from the question, deadline title, and last summary,
then calls ``llm.chat_json()`` with schema ``{"answer": str}``.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.llm import LlmError, chat_json

SYSTEM_PROMPT = (
    "Je bent een assistent voor een studenten-scrumteam. "
    "Beantwoord de volgende vraag in het Nederlands. "
    "Wees kort en krachtig. "
    "Gebruik de context hieronder."
)


class QuestionError(Exception):
    """Raised when the LLM cannot answer a question."""


def ask(
    question: str,
    *,
    deadline_title: str = "",
    last_summary: str = "",
    client: httpx.Client | None = None,
) -> str:
    """Ask the LLM a question and return the answer.

    *question* is the user's question.
    *deadline_title* is optional context about a related deadline.
    *last_summary* is the last meeting summary (at most one; not 4th older).

    Returns the answer as a string.
    Raises ``QuestionError`` after retries fail.
    """
    context_parts: list[str] = []
    if deadline_title:
        context_parts.append(f"Deadline: {deadline_title}")
    if last_summary:
        context_parts.append(f"Laatste samenvatting: {last_summary}")

    context = "\n".join(context_parts) if context_parts else "Geen extra context."

    user_content = f"Vraag: {question}\n\nContext:\n{context}"

    schema: dict[str, Any] = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    for attempt in range(2):
        try:
            result = chat_json(messages, schema, client=client)
            answer: str = result.get("answer", "") or ""
            if answer:
                return answer
            if attempt == 0:
                continue
            raise QuestionError("LLM returned empty answer") from None
        except LlmError:
            if attempt == 0:
                continue
            raise QuestionError("Vraag beantwoording mislukt na 2 pogingen") from None

    raise QuestionError("Vraag beantwoording mislukt na 2 pogingen")
