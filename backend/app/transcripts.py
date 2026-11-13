"""Transcript parsing for meeting summaries (SPEC 7.2, docs/summaries.md).

``parse_vtt()`` reads a WebVTT file and returns a list of ``Turn`` objects.
Consecutive cues from the same speaker are merged into a single turn.
``parse_docx()`` reads a DOCX (Teams download) and returns the same.
``as_text()`` renders turns as ``"Speaker: text"`` lines.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass

from defusedxml import ElementTree  # type: ignore[import-untyped]

# Maximum allowed size for word/document.xml inside the DOCX (20 MB).
_MAX_DOCX_SIZE = 20 * 1024 * 1024

# Matches a speaker line like "Sanne Bakker   0:02" or "Daan Visser  10:30".
# The time part is optional in the pattern (``(\d+:)?``) but present in Teams exports.
_SPEAKER_RE = re.compile(
    r"^(?P<speaker>.+?)\s+(\d+:)?\d{1,2}:\d{2}$"
)

# DOCX Word processing main namespace.
_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


@dataclass
class Turn:
    """One speaker's contribution to the meeting."""

    speaker: str
    text: str


class TranscriptError(Exception):
    """Raised when a transcript file cannot be parsed."""


# Matches ``<v Name>`` anywhere in a line and captures the speaker name (VTT).
_VTT_SPEAKER_RE = re.compile(r"<v\s+([^>]+?)>")

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
            m = _VTT_SPEAKER_RE.search(stripped)
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


def parse_docx(data: bytes) -> list[Turn]:
    """Parse a DOCX transcript into a list of turns.

    The DOCX is opened as a zipfile; only ``word/document.xml`` is read and
    parsed with ``defusedxml.ElementTree``.  Paragraphs matching the speaker
    pattern ``^(?P<speaker>.+?)\\s+(\\d+:)?\\d{1,2}:\\d{2}$`` start a new turn.
    Following non-empty paragraphs become the text of that turn.  Paragraphs
    before the first speaker line (title, date, duration) are skipped.

    Refuses zips whose ``document.xml`` exceeds 20 MB (zip-bomb guard).

    Raises ``TranscriptError`` on invalid input.
    """
    if not data:
        raise TranscriptError("Het transcriptbestand is leeg")

    try:
        with zipfile.ZipFile(__import__("io").BytesIO(data), "r") as z:
            if "word/document.xml" not in z.namelist():
                raise TranscriptError("Het bestand bevat geen document.xml")
            info = z.getinfo("word/document.xml")
            if info.file_size > _MAX_DOCX_SIZE:
                raise TranscriptError(
                    "Het transcriptbestand is te groot (max 20 MB)"
                )
            xml_bytes = z.read("word/document.xml")

        # Parse with defusedxml to avoid XXE and billion-laughs attacks.
        root = ElementTree.fromstring(xml_bytes)

        # Extract paragraph text in order.
        paragraphs: list[str] = []
        for p in root.iter(f"{{{ _NS['w'] }}}p"):
            text_parts: list[str] = []
            for t_elem in p.iter(f"{{{ _NS['w'] }}}t"):
                if t_elem.text:
                    text_parts.append(t_elem.text)
            text = "".join(text_parts).strip()
            if text:
                paragraphs.append(text)

    except zipfile.BadZipFile as err:
        raise TranscriptError("Het bestand is geen geldig DOCX-bestand") from err

    # Walk paragraphs looking for speaker lines.
    turns: list[Turn] = []
    current_speaker: str | None = None
    current_text_parts: list[str] = []

    for para in paragraphs:
        m = _SPEAKER_RE.match(para)
        if m:
            # Skip lines that look like dates (speaker name starts with a digit).
            # E.g. "10 november 2026, 09:00" should not be treated as a speaker.
            if m.group("speaker")[0].isdigit():
                continue
            # Save the previous turn if we have one.
            if current_speaker and current_text_parts:
                turns.append(
                    Turn(
                        speaker=current_speaker,
                        text=" ".join(current_text_parts),
                    )
                )
            current_speaker = m.group("speaker")
            current_text_parts = []
        elif current_speaker:
            # Append to current turn's text.
            current_text_parts.append(para)

    # Don't forget the last turn.
    if current_speaker and current_text_parts:
        turns.append(
            Turn(
                speaker=current_speaker,
                text=" ".join(current_text_parts),
            )
        )

    if not turns:
        raise TranscriptError(
            "Het transcriptbestand bevat geen herkenbare sprekers"
        )

    return turns
