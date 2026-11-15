"""SPEC 7.8: /meetings/{id} detail page and POST /meetings/{id}/post.

Status text, 404 handling, detail rendering (summary, decisions, action items, open questions),
and the "Post naar Teams" form with 303 redirect are tested here.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import AppSetting, Job

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


def set_auto_post(db: Any, enabled: bool) -> None:
    """Enable or disable automatic posting."""
    db.add(AppSetting(key="summary_auto_post", value=str(enabled).lower()))
    db.commit()


# --- 404 handling ---------------------------------------------------------------------


def test_meeting_detail_returns_404(auth_client: TestClient) -> None:
    r = auth_client.get("/meetings/99999")
    assert r.status_code == 404


# --- status text ----------------------------------------------------------------------


def test_detail_shows_status(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Wacht-job", "queued")
    html = auth_client.get(f"/meetings/{job.id}").text
    assert "in de wachtrij" in html


def test_detail_shows_posted_when_done(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Gepost", "done", posted_at=NOW)
    html = auth_client.get(f"/meetings/{job.id}").text
    assert "Gepost" in html


def test_detail_shows_not_posted_when_not_yet(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Nog niet", "done")
    html = auth_client.get(f"/meetings/{job.id}").text
    assert "Nog niet gepost" in html


# --- detail rendering -----------------------------------------------------------------


def test_detail_shows_summary(db: Any, auth_client: TestClient) -> None:
    job = add_job(
        db,
        "Met-samenvatting",
        "done",
        result={
            "summary": "Korte samenvatting van de vergadering.",
            "decisions": ["Budget goes green"],
            "action_items": [
                {"owner": "Bob", "task": "maak planning", "due": "2026-12-03"},  # SPEC 7.5
            ],
            "open_questions": ["Waar is het budget?"],
        },
    )
    html = auth_client.get(f"/meetings/{job.id}").text
    assert "Korte samenvatting van de vergadering." in html
    assert "Budget goes green" in html
    assert "maak planning" in html and "Bob" in html
    assert "Waar is het budget?" in html


# --- manual post form -----------------------------------------------------------------


def test_post_form_shown_when_not_posted_no_auto(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Klaar-nog-niet", "done")
    set_auto_post(db, False)
    html = auth_client.get(f"/meetings/{job.id}").text
    assert "Post naar Teams" in html
    assert f'action="/meetings/{job.id}/post"' in html


def test_post_form_hidden_when_already_posted(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Gepost-job", "done", posted_at=NOW)
    html = auth_client.get(f"/meetings/{job.id}").text
    assert "Post naar Teams" not in html


def test_post_form_hidden_when_auto_post(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Auto-job", "done")
    set_auto_post(db, True)
    html = auth_client.get(f"/meetings/{job.id}").text
    assert "Post naar Teams" not in html


def test_post_too_early_for_non_done(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "In-progress", "running")
    r = auth_client.post(f"/meetings/{job.id}/post")
    assert r.status_code == 400


# --- POST /meetings/{id}/post ---------------------------------------------------------


def test_post_updates_posted_at_and_redirects(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Post-me", "done")
    assert job.posted_at is None

    r = auth_client.post(f"/meetings/{job.id}/post", follow_redirects=False)
    assert r.status_code == 303

    db.refresh(job)
    assert job.posted_at is not None


def test_post_sets_posted_at_to_now(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "Post-naa", "done")
    assert job.posted_at is None

    auth_client.post(f"/meetings/{job.id}/post", follow_redirects=False)
    db.refresh(job)
    assert job.posted_at is not None
