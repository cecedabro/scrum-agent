"""T39: the / overview page (next 5 deadlines, last 3 jobs, model state)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import Job

# Monday 16 November 2026, 09:00 in Amsterdam.
NOW = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.clock.now_utc", lambda: NOW)


def add_deadline(db: Any, title: str, day: date, at: time | None = None) -> None:
    from app.deadlines import DeadlineIn, create

    create(db, DeadlineIn(title=title, due_date=day, due_time=at, note=None), now=NOW)
    db.commit()


def add_job(db: Any, title: str, meeting_date: date, status: str = "queued") -> int:
    job = Job(
        kind="summary",
        status=status,
        title=title,
        meeting_date=meeting_date,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job.id


def test_requires_login(client: TestClient) -> None:
    assert client.get("/").status_code == 401


def test_empty_home(db: Any, auth_client: TestClient) -> None:
    r = auth_client.get("/")
    assert r.status_code == 200
    assert "Overzicht" in r.text
    assert "Geen deadlines om te bekijken." in r.text
    assert "Nog geen vergaderingen." in r.text
    assert "Geen deadlines om te bekijken." not in (
        auth_client.get("/deadlines").text
    )  # base.html no longer has empty-state


def test_shows_next_5_deadlines(db: Any, auth_client: TestClient) -> None:
    for i in range(7):
        add_deadline(db, f"Deadline {i}", date(2026, 11, 16 + i))
    html = auth_client.get("/").text
    # Only 5 should appear
    for i in range(5):
        assert f"Deadline {i}" in html
    # Deadline 5 and 6 should NOT appear (beyond the 5 shown)
    for i in range(5, 7):
        assert f"Deadline {i}" not in html


def test_shows_last_3_jobs(db: Any, auth_client: TestClient) -> None:
    for i in range(5):
        add_job(db, f"Vergadering {i}", date(2026, 11, 10 + i))
    html = auth_client.get("/").text
    # Only 3 should appear (last 3: 2, 3, 4)
    for i in range(3, 5):
        assert f"Vergadering {i}" in html
    assert "Vergadering 2" in html
    # First 2 should NOT appear (older than last 3)
    for i in range(2):
        assert f"Vergadering {i}" not in html


def test_job_status_labels(db: Any, auth_client: TestClient) -> None:
    add_job(db, "Klaar-vergadering", date(2026, 11, 14), status="done")
    add_job(db, "Wachtrij-vergadering", date(2026, 11, 15), status="queued")
    add_job(db, "Bezig-vergadering", date(2026, 11, 16), status="running")
    html = auth_client.get("/").text
    assert "klaar" in html
    assert "in de wachtrij" in html
    assert "bezig" in html


def test_model_state_shown(db: Any, auth_client: TestClient) -> None:
    from app.db import session_factory
    from app.models import AppState

    with session_factory()() as session:
        row = session.query(AppState).filter(AppState.key == "model_status").first()
        if row is None:
            session.add(AppState(key="model_status", value={"up": False}))
        session.commit()

    html = auth_client.get("/").text
    assert "model offline" in html


def test_model_state_hidden_when_up(db: Any, auth_client: TestClient) -> None:
    from app.db import session_factory
    from app.models import AppState

    with session_factory()() as session:
        row = session.query(AppState).filter(AppState.key == "model_status").first()
        if row is None:
            session.add(AppState(key="model_status", value={"up": True}))
        else:
            row.value = {"up": True}
        session.commit()

    html = auth_client.get("/").text
    # When model is up, no "model offline" message
    assert "model offline" not in html


def test_deadline_links_in_home(db: Any, auth_client: TestClient) -> None:
    add_deadline(db, "Test-deadline", date(2026, 11, 18))
    html = auth_client.get("/").text
    assert 'href="/deadlines/' in html
    assert "Bewerken" in html


def test_job_links_in_home(db: Any, auth_client: TestClient) -> None:
    job_id = add_job(db, "Test-vergadering", date(2026, 11, 14))
    html = auth_client.get("/").text
    assert f"/meetings/{job_id}" in html


def test_nav_shows_overview_as_current(auth_client: TestClient) -> None:
    r = auth_client.get("/")
    assert r.status_code == 200
    assert 'aria-current="page"' in r.text
    assert 'href="/"' in r.text
    assert "Overzicht" in r.text


def test_dutch_date_in_home(db: Any, auth_client: TestClient) -> None:
    add_deadline(db, "Vandaag", date(2026, 11, 16))
    html = auth_client.get("/").text
    assert "maandag 16 november" in html
    assert "vandaag" in html


def test_no_empty_state_in_base_other_pages(db: Any, auth_client: TestClient) -> None:
    """The empty-state moved from base.html is only in index.html."""
    # Deadlines page should have its own empty state
    r = auth_client.get("/deadlines")
    assert r.status_code == 200
    assert "Geen komende deadlines" in r.text
    # But NOT the base.html message (which was removed)
    assert r.text.count("Geen deadlines om te bekijken") == 0
