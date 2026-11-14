"""SPEC 7.6: chunking in ``summarize`` for transcripts longer than ``SUMMARY_CHUNK_CHARS``.

Tests a fake ``chat_json`` (via ``MockTransport``) for:
  - transcript ~2.5× chunk size → 3 chunks + 1 merge call = 4 total
  - no part exceeds the chunk limit
  - no turn is split across chunks (split at ``\\n`` boundaries only)
  - the merge call receives the partial results
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.summarize import Summary, summarize

# ── fixtures ──────────────────────────────────────────────────────────

_VALID_RESPONSE = {
    "summary": "Korte meeting over agenda.",
    "decisions": ["Volgende week opnieuw"],
    "action_items": [{"owner": "Bram", "task": "Stuur notulen", "due": None}],
    "open_questions": ["Wanneer sprint eindigt?"],
}


@pytest.fixture(autouse=True)
def set_chunk_size(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force a small ``SUMMARY_CHUNK_CHARS`` for all tests in this file."""
    monkeypatch.setenv("SUMMARY_CHUNK_CHARS", "100")
    from app.config import get_settings
    get_settings.cache_clear()


# ── helpers ───────────────────────────────────────────────────────────


def _build_transcript(turns: list[tuple[str, str]]) -> str:
    """Build a transcript string from ``(speaker, text)`` pairs."""
    return "\n".join(f"{s}: {t}" for s, t in turns)


# ── 3× chunk size → 3 parts + 1 merge = 4 calls ─────────────────────


def test_chunking_three_times_chunk_size_four_calls() -> None:
    """Transcript ~2.5× chunk size produces 3 chunks + 1 merge call = 4 total."""
    # Each turn is ~35-42 chars; 6 turns ≈ 232 chars → 3 chunks (100-char limit) + merge
    turns = [
        ("Sanne", "We beginnen en bespreken de agenda."),
        ("Bram", "Bram geeft een korte update."),
        ("Daan", "Het sprint board is up-to-date."),
        ("Fennek", "Fennek meldt geen blokkades."),
        ("Gijs", "De demo vereist de login pagina."),
        ("Hanne", "Hanne wijst de taak toe en sluit."),
    ]
    transcript = _build_transcript(turns)

    call_count = 0
    responses: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        body = json.loads(request.content)
        user_text = body["messages"][1]["content"]
        responses.append({"chunk": user_text, "call_num": call_count})

        if call_count <= 3:
            return httpx.Response(
                200,
                content=json.dumps(
                    {"choices": [{"message": {"content": json.dumps(_VALID_RESPONSE)}}]}
                ).encode(),
            )
        # Merge call (4th)
        return httpx.Response(
            200,
            content=json.dumps(
                {"choices": [{"message": {"content": json.dumps(_VALID_RESPONSE)}}]}
            ).encode(),
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://127.0.0.1")

    result = summarize(transcript, client=client)

    assert call_count == 4
    assert isinstance(result, Summary)
    assert result.summary == "Korte meeting over agenda."


# ── no part over the limit ───────────────────────────────────────────


def test_no_part_over_chunk_limit() -> None:
    """Every chunk stays strictly under ``SUMMARY_CHUNK_CHARS``."""
    turns = [
        ("Sanne", "We beginnen en bespreken de agenda."),
        ("Bram", "Bram geeft een korte update."),
        ("Daan", "Het sprint board is up-to-date."),
        ("Fennek", "Fennek meldt geen blokkades."),
        ("Gijs", "De demo vereist de login pagina."),
        ("Hanne", "Hanne wijst de taak toe en sluit."),
    ]
    transcript = _build_transcript(turns)

    from app.config import get_settings
    max_chars = get_settings().SUMMARY_CHUNK_CHARS
    call_num = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_num
        call_num += 1
        body = json.loads(request.content)
        user_text = body["messages"][1]["content"]
        # Only the first 3 calls are chunk summaries (not the merge call)
        if call_num <= 3:
            assert len(user_text) <= max_chars, (
                f"Part {call_num} is {len(user_text)} "
                f"chars, limit is {max_chars}"
            )
        return httpx.Response(
            200,
            content=json.dumps(
                {"choices": [{"message": {"content": json.dumps(_VALID_RESPONSE)}}]}
            ).encode(),
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://127.0.0.1")

    result = summarize(transcript, client=client)
    assert isinstance(result, Summary)


# ── no turn split across chunks ─────────────────────────────────────


def test_no_turn_split_across_chunks() -> None:
    """Chunks are split only at ``\\n`` turn boundaries, never mid-turn."""
    turns = [
        ("Sanne", "We beginnen en bespreken de agenda."),
        ("Bram", "Bram geeft een korte update."),
        ("Daan", "Het sprint board is up-to-date."),
        ("Fennek", "Fennek meldt geen blokkades."),
        ("Gijs", "De demo vereist de login pagina."),
        ("Hanne", "Hanne wijst de taak toe en sluit."),
    ]
    transcript = _build_transcript(turns)

    seen_chunks: list[str] = []
    call_num = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_num
        call_num += 1
        body = json.loads(request.content)
        user_text = body["messages"][1]["content"]
        if call_num <= 3:
            seen_chunks.append(user_text)

        return httpx.Response(
            200,
            content=json.dumps(
                {"choices": [{"message": {"content": json.dumps(_VALID_RESPONSE)}}]}
            ).encode(),
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://127.0.0.1")

    summarize(transcript, client=client)

    # Each chunk should start with a complete "Speaker: text" line
    for i, chunk in enumerate(seen_chunks):
        lines = chunk.split("\n")
        assert len(lines) >= 1, f"Chunk {i} has no lines"
        for line in lines:
            assert ": " in line, (
                f"Chunk {i} has a line without 'Speaker: text' pattern: {line!r}"
            )


# ── merge call receives partial results ──────────────────────────────


def test_merge_call_receives_partial_results() -> None:
    """The merge call (last call) has the partial summaries in its user message."""
    turns = [
        ("Sanne", "We beginnen en bespreken de agenda."),
        ("Bram", "Bram geeft een korte update."),
        ("Daan", "Het sprint board is up-to-date."),
        ("Fennek", "Fennek meldt geen blokkades."),
        ("Gijs", "De demo vereist de login pagina."),
        ("Hanne", "Hanne wijst de taak toe en sluit."),
    ]
    transcript = _build_transcript(turns)

    merge_contents: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        user_text = body["messages"][1]["content"]
        if "Deelsamenvatting" in user_text:
            merge_contents.append(user_text)

        return httpx.Response(
            200,
            content=json.dumps(
                {"choices": [{"message": {"content": json.dumps(_VALID_RESPONSE)}}]}
            ).encode(),
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport, base_url="http://127.0.0.1")

    result = summarize(transcript, client=client)

    assert len(merge_contents) == 1, "Expected exactly one merge call"
    merge_text = merge_contents[0]
    assert "Deelsamenvatting 1:" in merge_text, "Merge should contain 'Deelsamenvatting 1:'"
    assert "Deelsamenvatting 2:" in merge_text, "Merge should contain 'Deelsamenvatting 2:'"
    assert "Deelsamenvatting 3:" in merge_text, "Merge should contain 'Deelsamenvatting 3:'"
    assert result.summary == "Korte meeting over agenda."
