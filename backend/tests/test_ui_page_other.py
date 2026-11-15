"""T57: the overview, settings and privacy pages use the components. Written by a human."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import Job
from tests._ui_helpers import template_source

PENDING_UNTIL = "T57"  # see backend/conftest.py

NOW = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.clock.now_utc", lambda: NOW)


def test_overview_cards(db: Any, auth_client: TestClient) -> None:
    from app.deadlines import DeadlineIn, create

    create(db, DeadlineIn(title="Demo", due_date=date(2026, 11, 18)), now=NOW)
    db.add(Job(kind="summary", status="done", title="Retro", meeting_date=date(2026, 11, 13)))
    db.commit()
    html = auth_client.get("/").text
    assert html.count('<section class="card">') >= 2
    assert '<time datetime="2026-11-18">' in html
    assert 'class="badge badge-done"' in html
    assert 'class="model-state model-state-' in html
    assert "<table" not in html


def test_overview_empty(auth_client: TestClient) -> None:
    html = auth_client.get("/").text
    assert html.count('class="empty-state"') >= 2


def test_settings_form_uses_fields(auth_client: TestClient) -> None:
    html = auth_client.get("/settings").text
    assert html.count('<div class="field field-check">') == 4  # weekly, deadline, sprint, auto-post
    assert '<select id="weekly_weekday" name="weekly_weekday"' in html
    assert 'class="btn btn-primary"' in html
    assert '<form method="post" action="/settings/test" class="inline-form">' in html


def test_settings_errors_as_alert(auth_client: TestClient) -> None:
    payload = {
        "weekly_enabled": "on",
        "weekly_weekday": "zontdag",
        "weekly_time": "08:30",
        "deadline_reminder_time": "09:00",
        "deadline_reminder_days_before": "2,1",
        "sprint_length": "2",
        "sprint_days_before": "1",
        "sprint_time": "09:00",
    }
    r = auth_client.post("/settings", data=payload)
    assert "Ongeldige dag" in r.text
    assert 'class="alert alert-danger"' in r.text


@pytest.mark.parametrize("name", ["index.html", "settings.html", "privacy.html"])
def test_templates_use_components(name: str) -> None:
    src = template_source(name)
    assert '{% import "_ui.html" as ui with context %}' in src
    for raw in ("<input", "<textarea", "<select", "style="):
        assert raw not in src, f"{name} contains {raw}"
