"""SPEC 7.5: summarize(transcript, client) -> Summary.

Tests a fake ``chat_json`` (via MockTransport) for:
  - 1 call for a short transcript
  - invalid then valid response = success
  - invalid twice = SummaryError
"""

import json

import httpx
import pytest

from app.summarize import Summary, SummaryError, summarize

# ── fixtures ──────────────────────────────────────────────────────────

_SHORT_TRANSCRIPT = "Sanne: We beginnen de meeting.\nBram: Agenda punt 1."

_VALID_RESPONSE = {
    "summary": "Korte meeting over agenda.",
    "decisions": ["Volgende week opnieuw"],
    "action_items": [{"owner": "Bram", "task": "Stuur notulen", "due": None}],
    "open_questions": ["Wanneer sprint eindigt?"],
}


# ── short transcript: 1 call ─────────────────────────────────────────


def test_summarize_short_transcript_makes_one_call() -> None:
    """A short transcript fits in one call."""
    call_count = 0
    received: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        received.update(json.loads(request.content))
        return httpx.Response(
            200,
            content=json.dumps(
                {"choices": [{"message": {"content": json.dumps(_VALID_RESPONSE)}}]}
            ).encode(),
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://127.0.0.1")

    result = summarize(_SHORT_TRANSCRIPT, client=client)

    assert call_count == 1
    assert isinstance(result, Summary)
    assert result.summary == "Korte meeting over agenda."
    assert result.decisions == ["Volgende week opnieuw"]
    assert len(result.action_items) == 1
    assert result.open_questions == ["Wanneer sprint eindigt?"]
    # Verify request structure
    assert received["messages"][0]["role"] == "system"
    assert "studenten-scrumteam" in received["messages"][0]["content"]
    assert received["messages"][1]["content"] == _SHORT_TRANSCRIPT


# ── invalid then valid: retry succeeds ───────────────────────────────


def test_summarize_invalid_then_valid_succeeds() -> None:
    """First call returns bad output; second call succeeds."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Bad output: not valid JSON → LlmError
            return httpx.Response(
                200,
                content=json.dumps(
                    {"choices": [{"message": {"content": "not valid json"}}]}
                ).encode(),
            )
        # Second attempt: valid output
        return httpx.Response(
            200,
            content=json.dumps(
                {"choices": [{"message": {"content": json.dumps(_VALID_RESPONSE)}}]}
            ).encode(),
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://127.0.0.1")

    result = summarize(_SHORT_TRANSCRIPT, client=client)

    assert call_count == 2
    assert isinstance(result, Summary)
    assert result.summary == "Korte meeting over agenda."


# ── invalid twice: SummaryError ──────────────────────────────────────


def test_summarize_invalid_twice_raises_summary_error() -> None:
    """Both attempts fail → SummaryError."""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            content=json.dumps({"choices": [{"message": {"content": "garbage"}}]}).encode(),
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://127.0.0.1")

    with pytest.raises(SummaryError, match="2 attempts"):
        summarize(_SHORT_TRANSCRIPT, client=client)

    assert call_count == 2
