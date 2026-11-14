"""SPEC 7.1: the /meetings upload form. Written by a human; the agent makes it pass.

Upload = `POST /meetings` (multipart) with fields `file`, `title` (optional) and
`meeting_date` (optional, `YYYY-MM-DD`, default today). Success → 303 to `/meetings`.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import Job

FIXTURES = Path(__file__).resolve().parents[2] / "tests" / "fixtures"
VTT = (FIXTURES / "sample.vtt").read_bytes()
DOCX = (FIXTURES / "sample.docx").read_bytes()
NOW = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)  # Monday 16 November, 09:00 Amsterdam


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.clock.now_utc", lambda: NOW)


@pytest.fixture()
def small_limit(monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    from app.config import get_settings

    monkeypatch.setenv("MAX_UPLOAD_BYTES", "2000")
    get_settings.cache_clear()
    yield 2000
    monkeypatch.delenv("MAX_UPLOAD_BYTES")
    get_settings.cache_clear()


def upload(client: TestClient, name: str, data: bytes, **fields: str) -> Any:
    return client.post(
        "/meetings", files={"file": (name, data)}, data=fields, follow_redirects=False
    )


def jobs(db: Any) -> list[Job]:
    db.expire_all()
    return list(db.scalars(select(Job).order_by(Job.id)))


def count(db: Any) -> int:
    db.expire_all()
    return int(db.scalar(select(func.count()).select_from(Job)))


def test_form_is_shown(auth_client: TestClient) -> None:
    r = auth_client.get("/meetings")
    assert r.status_code == 200
    assert 'enctype="multipart/form-data"' in r.text
    assert 'type="file"' in r.text and 'name="file"' in r.text
    assert 'accept=".vtt,.docx"' in r.text
    assert 'name="title"' in r.text
    assert 'name="meeting_date"' in r.text
    assert 'aria-current="page"' in r.text


def test_requires_login(client: TestClient) -> None:
    assert client.get("/meetings").status_code == 401
    assert upload(client, "a.vtt", VTT).status_code == 401


def test_vtt_upload_creates_queued_job(db: Any, auth_client: TestClient) -> None:
    r = upload(auth_client, "standup.vtt", VTT, title="Sprint review", meeting_date="2026-11-13")
    assert r.status_code == 303
    assert r.headers["location"] == "/meetings"
    [job] = jobs(db)
    assert job.kind == "summary"
    assert job.status == "queued"
    assert job.attempts == 0
    assert job.title == "Sprint review"
    assert job.meeting_date == date(2026, 11, 13)
    assert job.transcript is not None
    assert job.transcript.startswith("Sanne Bakker")
    assert "<v" not in job.transcript and "-->" not in job.transcript


def test_docx_gives_the_same_transcript_as_vtt(db: Any, auth_client: TestClient) -> None:
    assert upload(auth_client, "a.vtt", VTT, title="A").status_code == 303
    assert upload(auth_client, "b.docx", DOCX, title="B").status_code == 303
    a, b = jobs(db)
    assert a.transcript == b.transcript


def test_uppercase_extension_is_fine(db: Any, auth_client: TestClient) -> None:
    assert upload(auth_client, "TEAMS.VTT", VTT).status_code == 303
    assert count(db) == 1


def test_defaults_title_and_date(db: Any, auth_client: TestClient) -> None:
    assert upload(auth_client, "a.vtt", VTT, title="", meeting_date="").status_code == 303
    [job] = jobs(db)
    assert job.meeting_date == date(2026, 11, 16)  # today in Amsterdam
    assert job.title == "Vergadering ma 16 nov"  # "Vergadering " + datum_kort(meeting_date)


def test_title_is_trimmed(db: Any, auth_client: TestClient) -> None:
    upload(auth_client, "a.vtt", VTT, title="  Retro  ")
    assert jobs(db)[0].title == "Retro"


ENGLISH = ("Field required", "Input should", "value_error", "Traceback", '{"detail"')


def assert_refused(r: Any, db: Any) -> None:
    assert r.status_code == 422, r.text[:300]
    assert 'class="error"' in r.text
    assert 'name="file"' in r.text  # the form is shown again, as HTML
    assert not any(word in r.text for word in ENGLISH)
    assert count(db) == 0


def test_txt_refused(db: Any, auth_client: TestClient) -> None:
    assert_refused(upload(auth_client, "notes.txt", b"hallo"), db)


def test_no_extension_refused(db: Any, auth_client: TestClient) -> None:
    assert_refused(upload(auth_client, "transcript", VTT), db)


def test_empty_vtt_refused(db: Any, auth_client: TestClient) -> None:
    assert_refused(upload(auth_client, "leeg.vtt", b"WEBVTT\n\n"), db)


def test_not_utf8_vtt_refused(db: Any, auth_client: TestClient) -> None:
    assert_refused(upload(auth_client, "raar.vtt", b"WEBVTT\n\n\xff\xfe\xfa"), db)


def test_broken_docx_refused(db: Any, auth_client: TestClient) -> None:
    assert_refused(upload(auth_client, "kapot.docx", b"this is not a zip file"), db)


def test_bad_date_refused(db: Any, auth_client: TestClient) -> None:
    assert_refused(upload(auth_client, "a.vtt", VTT, meeting_date="16-11-2026"), db)


def test_too_large_refused(db: Any, auth_client: TestClient, small_limit: int) -> None:
    big = (
        b"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n<v Sanne Bakker>"
        + b"a" * small_limit
        + b"</v>\n"
    )
    assert_refused(upload(auth_client, "groot.vtt", big), db)


def test_exactly_the_limit_is_fine(db: Any, auth_client: TestClient, small_limit: int) -> None:
    head = b"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\n<v Sanne Bakker>"
    tail = b"</v>\n"
    data = head + b"a" * (small_limit - len(head) - len(tail)) + tail
    assert len(data) == small_limit
    assert upload(auth_client, "precies.vtt", data).status_code == 303
