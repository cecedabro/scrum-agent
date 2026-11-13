"""Tests for app/transcripts.py – parse_docx (SPEC 7.2).

Coverage targets:
- sample.docx: 11 turns, 4 speakers, first by "Sanne Bakker"
- Non-zip file → TranscriptError
- Zip without ``word/document.xml`` → TranscriptError
- Oversized ``document.xml`` (> 20 MB) → TranscriptError
- Empty data → TranscriptError
- No speaker lines → TranscriptError
"""

from __future__ import annotations

import zipfile
from io import BytesIO
from pathlib import Path

import pytest

from app.transcripts import TranscriptError, parse_docx

SAMPLE_DOCX_PATH = "../tests/fixtures/sample.docx"


def _load_sample() -> bytes:
    """Return the raw content of the sample DOCX fixture."""
    return Path(SAMPLE_DOCX_PATH).read_bytes()


# ------------------------------------------------------------------
# Sample DOCX fixture tests
# ------------------------------------------------------------------


def test_sample_docx_turn_count() -> None:
    turns = parse_docx(_load_sample())
    assert len(turns) == 11


def test_sample_docx_speaker_count() -> None:
    turns = parse_docx(_load_sample())
    speakers = {t.speaker for t in turns}
    assert len(speakers) == 4


def test_sample_docx_first_speaker() -> None:
    turns = parse_docx(_load_sample())
    assert turns[0].speaker == "Sanne Bakker"


def test_sample_docx_first_text() -> None:
    turns = parse_docx(_load_sample())
    assert "sprint review" in turns[0].text.lower()


def test_sample_docx_no_timing_in_output() -> None:
    turns = parse_docx(_load_sample())
    for t in turns:
        assert "0:02" not in t.text
        assert "0:08" not in t.text


def test_sample_docx_all_4_speakers() -> None:
    turns = parse_docx(_load_sample())
    speakers = {t.speaker for t in turns}
    assert "Sanne Bakker" in speakers
    assert "Daan Visser" in speakers
    assert "Noor El Amrani" in speakers
    assert "Lucas de Jong" in speakers


def test_sample_docx_text_content() -> None:
    """Verify specific text matches the VTT fixture."""
    turns = parse_docx(_load_sample())
    # Lucas de Jong has a multi-line cue (two paragraphs joined)
    lucas_turns = [t for t in turns if t.speaker == "Lucas de Jong"]
    assert len(lucas_turns) == 2
    first_lucas = lucas_turns[0]
    assert "Mee eens" in first_lucas.text
    assert "feedback" in first_lucas.text


# ------------------------------------------------------------------
# Edge cases: empty data
# ------------------------------------------------------------------


def test_empty_data() -> None:
    with pytest.raises(TranscriptError, match="leeg"):
        parse_docx(b"")


# ------------------------------------------------------------------
# Edge cases: non-zip file
# ------------------------------------------------------------------


def test_non_zip_file() -> None:
    with pytest.raises(TranscriptError, match="DOCX"):
        parse_docx(b"This is not a zip file at all.")


# ------------------------------------------------------------------
# Edge cases: zip without word/document.xml
# ------------------------------------------------------------------


def _make_minimal_zip(namelist: list[str]) -> bytes:
    """Create a minimal zip file with the given members and empty content."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name in namelist:
            z.writestr(name, b"")
    return buf.getvalue()


def test_zip_without_document_xml() -> None:
    data = _make_minimal_zip(["[Content_Types].xml", "_rels/.rels"])
    with pytest.raises(TranscriptError, match="document.xml"):
        parse_docx(data)


# ------------------------------------------------------------------
# Edge cases: oversized document.xml (built in tmp_path)
# ------------------------------------------------------------------


def test_oversized_document_xml(tmp_path: Path) -> None:
    # Build a DOCX with a document.xml that exceeds 20 MB.
    docx_path = tmp_path / "oversized.docx"
    big_xml = b"<w:dummy>" + b"x" * (21 * 1024 * 1024) + b"</w:dummy>"
    with zipfile.ZipFile(docx_path, "w") as z:
        z.writestr("[Content_Types].xml", b'<?xml version="1.0"?>')
        z.writestr("word/document.xml", big_xml)

    with pytest.raises(TranscriptError, match="te groot"):
        parse_docx(docx_path.read_bytes())


# ------------------------------------------------------------------
# Edge cases: no speaker lines
# ------------------------------------------------------------------


def _make_docx_with_paragraphs(paragraphs: list[str]) -> bytes:
    """Create a DOCX with the given paragraph texts (no speaker lines)."""
    NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    xml_parts = ["<?xml version=\"1.0\"?>", f'<w:document xmlns:w="{NS}">']
    for para in paragraphs:
        xml_parts.append(f'<w:p><w:r><w:t>{para}</w:t></w:r></w:p>')
    xml_parts.append("</w:document>")
    xml = "\n".join(xml_parts)

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", b'<?xml version="1.0"?>')
        z.writestr("word/document.xml", xml.encode("utf-8"))
    return buf.getvalue()


def test_no_speaker_lines() -> None:
    data = _make_docx_with_paragraphs(["Sprint 3 review", "10 november 2026"])
    with pytest.raises(TranscriptError, match="geen herkenbare sprekers"):
        parse_docx(data)


# ------------------------------------------------------------------
# Edge cases: single speaker, single turn
# ------------------------------------------------------------------


def test_single_turn() -> None:
    data = _make_docx_with_paragraphs([
        "Alice   0:01",
        "Hello world.",
    ])
    turns = parse_docx(data)
    assert len(turns) == 1
    assert turns[0].speaker == "Alice"
    assert turns[0].text == "Hello world."
