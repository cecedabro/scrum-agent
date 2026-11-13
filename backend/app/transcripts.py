"""Transcript parsing for meeting summaries (SPEC 7.2, docs/summaries.md).

``parse_vtt()`` reads a WebVTT file and returns a list of ``Turn`` objects.
Consecutive cues from the same speaker are merged into a single turn.
``as_text()`` renders turns as ``"Speaker: text"`` lines.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Turn:
    """One speaker's contribution to the meeting."""

    speaker: str
    text: str


class TranscriptError(Exception):
    """Raised when a transcript file cannot be parsed."""


# Matches ``<v Name>`` anywhere in a line and captures the speaker name.
_SPEAKER_RE = re.compile(r"<v\s+([^>]+?)>")

# Matches a VTT cue ID: UUID-like string, possibly with a suffix after "/".
_CUE_ID_RE = re.compile(r"^[0-9a-fA-F-]+/?[0-9a-zA-Z_-]*$")


def _strip_tags(text: str) -> str:
    """Remove all XML/HTML-style tags from *text*."""
    return re.sub(r"<[^>]+>", "", text)


def parse_vtt(content: str) -> list[Turn]:
    """Parse a WebVTT transcript into a list of turns.

    Rules:
    - Blank lines separate cues (VTT block structure).
    - Skip the ``WEBVTT`` header, cue IDs and timing lines.
    - Speaker is extracted from ``<v Name>`` tags.
    - A cue without a ``<v>`` tag gets speaker ``"Onbekend"``.
    - Consecutive cues from the same speaker are merged into one turn.
    - All markup tags are stripped from the text.

    Raises ``TranscriptError`` on invalid input.
    """
    if not content.strip():
        raise TranscriptError("Het transcriptbestand is leeg")

    # Split into cues: blank lines are cue separators in VTT.
    cues_raw = re.split(r"\n\n+", content.strip())

    # Skip the first cue which is the "WEBVTT" header.
    if cues_raw and cues_raw[0].strip() == "WEBVTT":
        cues_raw = cues_raw[1:]

    if not cues_raw:
        raise TranscriptError("Het transcriptbestand is leeg")

    # Parse each cue block into (speaker, text_lines).
    raw_turns: list[tuple[str, list[str]]] = []
    for cue in cues_raw:
        speaker: str | None = None
        text_lines: list[str] = []
        for line in cue.split("\n"):
            stripped = line.strip()
            # Skip empty lines, timing lines, and cue IDs.
            if not stripped or "-->" in stripped:
                continue
            if _CUE_ID_RE.match(stripped):
                continue
            # Check for <v> speaker tag.
            m = _SPEAKER_RE.search(stripped)
            if m:
                speaker = m.group(1)
                # Extract any text after the <v Name> tag on the same line.
                after_tag = stripped[m.end() :]
                if after_tag.strip():
                    text_lines.append(after_tag)
            else:
                # This is a text line (or continuation text on another line).
                text_lines.append(stripped)
        if speaker is None:
            speaker = "Onbekend"
        raw_turns.append((speaker, text_lines))

    # Merge consecutive cues from the same speaker.
    turns: list[Turn] = []
    for speaker, text_lines in raw_turns:
        text = _strip_tags(" ".join(text_lines)).strip()
        if turns and turns[-1].speaker == speaker:
            # Append to the last turn.
            turns[-1].text = f"{turns[-1].text} {text}"
        elif text:
            turns.append(Turn(speaker=speaker, text=text))

    return turns


def as_text(turns: list[Turn]) -> str:
    """Render a list of turns as ``"Speaker: text"`` lines.

    This is the format used to store transcripts in the job table.
    """
    return "\n".join(f"{t.speaker}: {t.text}" for t in turns)
