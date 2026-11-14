"""SPEC 7.3: the job list and model state on /meetings. Written by a human.

Jobs and the `model_status` row are inserted directly, so these tests do not depend on
the upload route. `model_status` is `{"up": bool, "checked_at": iso, "last_up_at": iso|None}`
(docs/summaries.md §Worker).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import AppState, Job

NOW = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)  # Monday 16 November, 09:00 Amsterdam
POLL = 'hx-trigger="every 10s"'

PENDING_UNTIL = "T26"  # see backend/conftest.py


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.clock.now_utc", lambda: NOW)


def add_job(db: Any, title: str, status: str, minutes_ago: int = 0, **extra: Any) -> Job:
    job = Job(
        kind=extra.pop("kind", "summary"),
        status=status,
        title=title,
        meeting_date=extra.pop("meeting_date", date(2026, 12, 1)),
        created_at=NOW - timedelta(minutes=minutes_ago),
        **extra,
    )
    db.add(job)
    db.commit()
    return job


def model_status(db: Any, up: bool, last_up_at: datetime | None) -> None:
    db.add(
        AppState(
            key="model_status",
            value={
                "up": up,
                "checked_at": NOW.isoformat(),
                "last_up_at": last_up_at.isoformat() if last_up_at else None,
            },
        )
    )
    db.commit()


# --- job list (SPEC 7.3) -------------------------------------------------------------


def test_empty_state(auth_client: TestClient) -> None:
    r = auth_client.get("/meetings")
    assert r.status_code == 200
    assert "Nog geen vergaderingen" in r.text


@pytest.mark.parametrize(
    ("status", "label"),
    [("queued", "in de wachtrij"), ("running", "bezig"), ("done", "klaar"), ("failed", "mislukt")],
)
def test_dutch_status_labels(db: Any, auth_client: TestClient, status: str, label: str) -> None:
    add_job(db, f"Vergadering-{status}", status)
    html = auth_client.get("/meetings").text
    assert f"Vergadering-{status}" in html
    assert label in html


def test_meeting_date_shown_short(db: Any, auth_client: TestClient) -> None:
    add_job(db, "Planning", "done", meeting_date=date(2026, 12, 1))
    assert "di 1 dec" in auth_client.get("/meetings").text  # datum_kort


def test_newest_first(db: Any, auth_client: TestClient) -> None:
    add_job(db, "Oudste-job", "done", minutes_ago=300)
    add_job(db, "Middelste-job", "done", minutes_ago=200)
    add_job(db, "Nieuwste-job", "done", minutes_ago=100)
    html = auth_client.get("/meetings").text
    assert html.index("Nieuwste-job") < html.index("Middelste-job") < html.index("Oudste-job")


def test_rows_link_to_detail(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Met link", "done")
    assert f'href="/meetings/{job.id}"' in auth_client.get("/meetings").text


def test_failed_job_shows_its_error(db: Any, auth_client: TestClient) -> None:
    add_job(db, "Kapot", "failed", error="Het model gaf 3 keer geen geldig antwoord.")
    assert "Het model gaf 3 keer geen geldig antwoord." in auth_client.get("/meetings").text


def test_transcript_text_never_shown(db: Any, auth_client: TestClient) -> None:
    add_job(db, "Geheim", "queued", transcript="Sanne Bakker: dit is privé")
    assert "dit is privé" not in auth_client.get("/meetings").text


# --- model state ----------------------------------------------------------------------


def test_model_reachable(db: Any, auth_client: TestClient) -> None:
    model_status(db, True, NOW)
    html = auth_client.get("/meetings").text
    assert "model bereikbaar" in html
    assert "model offline" not in html


def test_model_offline_with_last_seen(db: Any, auth_client: TestClient) -> None:
    model_status(db, False, datetime(2026, 11, 13, 21, 5, tzinfo=UTC))  # 22:05 Amsterdam
    html = auth_client.get("/meetings").text
    assert "model offline (pc slaapt of is gepauzeerd)" in html
    assert "laatst gezien" in html
    assert "vr 13 nov 22:05" in html  # local time, datum_kort + HH:MM


def test_model_never_checked(auth_client: TestClient) -> None:
    html = auth_client.get("/meetings").text
    assert "model offline" in html
    assert "nog nooit gezien" in html


# --- partial and polling (docs/frontend.md §Polling) -----------------------------------


def test_partial_is_a_fragment(db: Any, auth_client: TestClient) -> None:
    add_job(db, "In fragment", "done")
    r = auth_client.get("/meetings/partial")
    assert r.status_code == 200
    assert "In fragment" in r.text
    assert "<html" not in r.text and "<nav" not in r.text


def test_partial_requires_login(client: TestClient) -> None:
    assert client.get("/meetings/partial").status_code == 401


@pytest.mark.parametrize("status", ["queued", "running"])
def test_polls_while_work_is_pending(db: Any, auth_client: TestClient, status: str) -> None:
    add_job(db, "Bezig", status)
    for url in ("/meetings", "/meetings/partial"):
        html = auth_client.get(url).text
        assert POLL in html, url
        assert 'hx-get="/meetings/partial"' in html, url


def test_no_polling_when_all_finished(db: Any, auth_client: TestClient) -> None:
    add_job(db, "Klaar", "done")
    add_job(db, "Mis", "failed")
    for url in ("/meetings", "/meetings/partial"):
        assert POLL not in auth_client.get(url).text, url


def test_no_polling_when_empty(auth_client: TestClient) -> None:
    assert POLL not in auth_client.get("/meetings").text
