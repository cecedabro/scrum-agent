"""Tests for app/transcripts.py – parse_vtt and as_text (SPEC 7.2).

Coverage targets:
- sample.vtt: 11 turns, 4 speakers, first by "Sanne Bakker"
- Multi-line cue joined into one turn
- No ``<v`` or ``-->`` in resulting text
- Edge cases: cue without ``<v>``, empty file → TranscriptError
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.transcripts import TranscriptError, Turn, as_text, parse_vtt

SAMPLE_VTT_PATH = "../tests/fixtures/sample.vtt"


def _load_sample() -> str:
    """Return the raw content of the sample VTT fixture."""
    return Path(SAMPLE_VTT_PATH).read_text(encoding="utf-8")


# ------------------------------------------------------------------
# Sample VTT fixture tests
# ------------------------------------------------------------------


def test_sample_vtt_turn_count() -> None:
    turns = parse_vtt(_load_sample())
    assert len(turns) == 11


def test_sample_vtt_speaker_count() -> None:
    turns = parse_vtt(_load_sample())
    speakers = {t.speaker for t in turns}
    assert len(speakers) == 4


def test_sample_vtt_first_speaker() -> None:
    turns = parse_vtt(_load_sample())
    assert turns[0].speaker == "Sanne Bakker"


def test_sample_vtt_first_text() -> None:
    turns = parse_vtt(_load_sample())
    assert "sprint review" in turns[0].text.lower()


def test_sample_vtt_no_v_tags_in_output() -> None:
    turns = parse_vtt(_load_sample())
    for t in turns:
        assert "<v" not in t.speaker
        assert "<v" not in t.text


def test_sample_vtt_no_timing_in_output() -> None:
    turns = parse_vtt(_load_sample())
    for t in turns:
        assert "-->" not in t.text


def test_sample_vtt_all_4_speakers() -> None:
    turns = parse_vtt(_load_sample())
    speakers = {t.speaker for t in turns}
    assert "Sanne Bakker" in speakers
    assert "Daan Visser" in speakers
    assert "Noor El Amrani" in speakers
    assert "Lucas de Jong" in speakers


def test_sample_vtt_multiline_cue_joined() -> None:
    """Lucas de Jong's cue spans two lines (turn 4)."""
    turns = parse_vtt(_load_sample())
    lucas_turns = [t for t in turns if t.speaker == "Lucas de Jong"]
    assert len(lucas_turns) == 2  # two separate cues from Lucas
    # The first cue has both lines joined
    first_lucas = lucas_turns[0]
    assert "Mee eens" in first_lucas.text
    assert "feedback" in first_lucas.text


def test_sample_vtt_as_text_format() -> None:
    turns = parse_vtt(_load_sample())
    text = as_text(turns)
    lines = text.split("\n")
    assert len(lines) == 11
    assert lines[0].startswith("Sanne Bakker: ")


# ------------------------------------------------------------------
# Edge cases: cue without <v> tag
# ------------------------------------------------------------------


def test_cue_without_v_tag() -> None:
    vtt = """WEBVTT

1
00:00:01.000 --> 00:00:03.000
This text has no speaker tag.

2
00:00:04.000 --> 00:00:06.000
<v Hans>Now with a speaker.</v>
"""
    turns = parse_vtt(vtt)
    assert len(turns) == 2
    assert turns[0].speaker == "Onbekend"
    assert turns[0].text == "This text has no speaker tag."
    assert turns[1].speaker == "Hans"


def test_only_cues_without_v_tag() -> None:
    vtt = """WEBVTT

1
00:00:01.000 --> 00:00:03.000
First unknown speaker.

2
00:00:04.000 --> 00:00:06.000
Second unknown speaker.
"""
    turns = parse_vtt(vtt)
    # Two consecutive cues from "Onbekend" should merge into one turn
    assert len(turns) == 1
    assert turns[0].speaker == "Onbekend"


# ------------------------------------------------------------------
# Edge cases: empty file
# ------------------------------------------------------------------


def test_empty_file() -> None:
    with pytest.raises(TranscriptError, match="leeg"):
        parse_vtt("")


def test_whitespace_only() -> None:
    with pytest.raises(TranscriptError, match="leeg"):
        parse_vtt("   \n\n  \n")


def test_only_header() -> None:
    with pytest.raises(TranscriptError):
        parse_vtt("WEBVTT\n")


# ------------------------------------------------------------------
# Edge cases: inline text after <v> tag
# ------------------------------------------------------------------


def test_inline_text_after_v_tag() -> None:
    vtt = """WEBVTT

1
00:00:01.000 --> 00:00:03.000
<v Alice>Hello world</v>
"""
    turns = parse_vtt(vtt)
    assert len(turns) == 1
    assert turns[0].speaker == "Alice"
    assert turns[0].text == "Hello world"


# ------------------------------------------------------------------
# Edge cases: consecutive cues same speaker
# ------------------------------------------------------------------


def test_consecutive_same_speaker_merged() -> None:
    """Multiple cues from the same speaker should be merged."""
    vtt = """WEBVTT

1
00:00:01.000 --> 00:00:02.000
<v Bob>Part one.</v>

2
00:00:03.000 --> 00:00:04.000
<v Bob>Part two.</v>
"""
    turns = parse_vtt(vtt)
    assert len(turns) == 1
    assert turns[0].speaker == "Bob"
    assert "Part one" in turns[0].text
    assert "Part two" in turns[0].text


# ------------------------------------------------------------------
# Edge cases: alternating speakers
# ------------------------------------------------------------------


def test_alternating_speakers_not_merged() -> None:
    """Different speakers should produce separate turns."""
    vtt = """WEBVTT

1
00:00:01.000 --> 00:00:02.000
<v A>First.</v>

2
00:00:03.000 --> 00:00:04.000
<v B>Second.</v>

3
00:00:05.000 --> 00:00:06.000
<v A>Third.</v>
"""
    turns = parse_vtt(vtt)
    assert len(turns) == 3
    assert turns[0].speaker == "A"
    assert turns[1].speaker == "B"
    assert turns[2].speaker == "A"


# ------------------------------------------------------------------
# Edge cases: as_text
# ------------------------------------------------------------------


def test_as_text_empty() -> None:
    assert as_text([]) == ""


def test_as_text_single_turn() -> None:
    turns = [Turn(speaker="Alice", text="Hello")]
    assert as_text(turns) == "Alice: Hello"


def test_as_text_multiple_turns() -> None:
    turns = [
        Turn(speaker="Alice", text="Hi"),
        Turn(speaker="Bob", text="Bye"),
    ]
    text = as_text(turns)
    lines = text.split("\n")
    assert lines == ["Alice: Hi", "Bob: Bye"]
