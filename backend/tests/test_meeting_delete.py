"""SPEC 8.3: DELETE a meeting job.

Tests the POST /meetings/{id}/delete route (303 redirect, 404 for unknown ids) and the
delete button on the detail page.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Job

NOW = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.clock.now_utc", lambda: NOW)


def add_job(db: Any, title: str = "Vergadering", status: str = "queued", **extra: Any) -> Job:
    job = Job(
        kind="summary",
        status=status,
        title=title,
        meeting_date=extra.pop("meeting_date", date(2026, 12, 1)),
        created_at=extra.pop("created_at", NOW - timedelta(minutes=30)),
        **extra,
    )
    db.add(job)
    db.commit()
    return job


# --- POST /meetings/{id}/delete ---------------------------------------------------------


def test_delete_redirects_to_meetings(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Te-verwijderen", "done")
    r = auth_client.post(f"/meetings/{job.id}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/meetings"


def test_delete_removes_job_from_db(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Te-verwijderen", "done")
    job_id = job.id
    auth_client.post(f"/meetings/{job_id}/delete", follow_redirects=False)
    assert db.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none() is None


def test_delete_unknown_id_returns_404(auth_client: TestClient) -> None:
    r = auth_client.post("/meetings/99999/delete", follow_redirects=False)
    assert r.status_code == 404


def test_delete_removes_from_list(db: Any, auth_client: TestClient) -> None:
    keep = add_job(db, "Blijven", "done")
    add_job(db, "Te-verwijderen", "done")
    r = auth_client.get("/meetings")
    assert keep.title in r.text
    auth_client.post("/meetings/2/delete", follow_redirects=False)
    db.refresh(keep)
    assert db.execute(select(Job).where(Job.id == 2)).scalar_one_or_none() is None


def test_delete_done_job(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Klaar-job", "done")
    auth_client.post(f"/meetings/{job.id}/delete", follow_redirects=False)
    assert db.execute(select(Job).where(Job.id == job.id)).scalar_one_or_none() is None


def test_delete_queued_job(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Wacht-job", "queued")
    auth_client.post(f"/meetings/{job.id}/delete", follow_redirects=False)
    assert db.execute(select(Job).where(Job.id == job.id)).scalar_one_or_none() is None


def test_delete_failed_job(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Mislukt-job", "failed")
    auth_client.post(f"/meetings/{job.id}/delete", follow_redirects=False)
    assert db.execute(select(Job).where(Job.id == job.id)).scalar_one_or_none() is None


def test_delete_running_job(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Bezig-job", "running")
    auth_client.post(f"/meetings/{job.id}/delete", follow_redirects=False)
    assert db.execute(select(Job).where(Job.id == job.id)).scalar_one_or_none() is None


# --- Delete button on detail page -------------------------------------------------------


def test_delete_button_shown_on_detail(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Detail-job", "done")
    html = auth_client.get(f"/meetings/{job.id}").text
    assert f'action="/meetings/{job.id}/delete"' in html
    assert "Verwijderen" in html


def test_delete_button_works_from_detail(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Detail-verwijder", "done")
    r = auth_client.post(f"/meetings/{job.id}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert db.execute(select(Job).where(Job.id == job.id)).scalar_one_or_none() is None
