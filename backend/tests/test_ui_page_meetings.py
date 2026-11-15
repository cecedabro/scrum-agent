"""T56: /meetings, the job list and the detail page use the components. Written by a human."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import AppState, Job
from tests._ui_helpers import template_source

PENDING_UNTIL = "T56"  # see backend/conftest.py

NOW = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.clock.now_utc", lambda: NOW)


def add_job(db: Any, status: str, **extra: Any) -> Job:
    job = Job(
        kind="summary",
        status=status,
        title=f"Overleg-{status}",
        meeting_date=date(2026, 11, 13),
        **extra,
    )
    db.add(job)
    db.commit()
    return job


RESULT = {
    "summary": "We hebben de demo besproken.",
    "decisions": ["Demo op vrijdag"],
    "action_items": [
        {"owner": "Sanne Bakker", "task": "Demo voorbereiden", "due": "2026-11-20"},
        {"owner": None, "task": "Zaal reserveren", "due": None},
    ],
    "open_questions": ["Wie presenteert?"],
}


def test_upload_form_uses_fields(auth_client: TestClient) -> None:
    html = auth_client.get("/meetings").text
    assert html.count('<div class="field">') >= 3
    assert 'type="file"' in html and 'accept=".vtt,.docx"' in html
    assert 'class="btn btn-primary"' in html


@pytest.mark.parametrize("status", ["queued", "running", "done", "failed"])
def test_job_list_shows_badges(db: Any, auth_client: TestClient, status: str) -> None:
    add_job(db, status)
    html = auth_client.get("/meetings").text
    assert '<ul class="list">' in html and '<li class="list-item">' in html
    assert f'class="badge badge-{status}"' in html
    assert "<table" not in html


def test_model_state_component(db: Any, auth_client: TestClient) -> None:
    db.add(
        AppState(
            key="model_status",
            value={"up": True, "checked_at": NOW.isoformat(), "last_up_at": NOW.isoformat()},
        )
    )
    db.commit()
    assert 'class="model-state model-state-up"' in auth_client.get("/meetings").text


def test_model_down_component(auth_client: TestClient) -> None:
    assert 'class="model-state model-state-down"' in auth_client.get("/meetings").text


def test_detail_page(db: Any, auth_client: TestClient) -> None:
    job = add_job(db, "done", result=RESULT)
    html = auth_client.get(f"/meetings/{job.id}").text
    assert 'class="badge badge-done"' in html
    assert html.count('<section class="card">') >= 3
    assert "Demo voorbereiden" in html and "Sanne Bakker" in html and "Zaal reserveren" in html
    assert "owner" not in html and "&#39;task&#39;" not in html and "{'" not in html
    assert f'<form method="post" action="/meetings/{job.id}/delete" class="inline-form">' in html
    assert 'class="btn btn-danger"' in html
    assert "<table" not in html


@pytest.mark.parametrize("name", ["meetings.html", "_jobs.html", "meeting_detail.html"])
def test_templates_use_components(name: str) -> None:
    src = template_source(name)
    assert '{% import "_ui.html" as ui with context %}' in src
    for raw in ("<input", "<textarea", "<select", "<table", "style="):
        assert raw not in src, f"{name} contains {raw}"
