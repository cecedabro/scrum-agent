"""T55: /deadlines and the edit page use the components (docs/frontend.md). Written by a human."""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests._ui_helpers import template_source

PENDING_UNTIL = "T55"  # see backend/conftest.py

NOW = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.clock.now_utc", lambda: NOW)


def add(db: Any, title: str, day: date, at: time | None = None) -> int:
    from app.deadlines import DeadlineIn, create

    row = create(db, DeadlineIn(title=title, due_date=day, due_time=at), now=NOW)
    db.commit()
    return int(row.id)


def test_list_is_a_list_with_time_tags(db: Any, auth_client: TestClient) -> None:
    add(db, "Demo", date(2026, 11, 18), time(14, 30))
    add(db, "Oud", date(2026, 11, 10))
    html = auth_client.get("/deadlines").text
    assert "<table" not in html
    assert '<ul class="list">' in html
    assert html.count('<li class="list-item">') == 2
    assert '<time datetime="2026-11-18T14:30">woensdag 18 november om 14:30</time>' in html
    assert '<span class="relative">(over 2 dagen)</span>' in html


def test_row_actions(db: Any, auth_client: TestClient) -> None:
    i = add(db, "Demo", date(2026, 11, 18))
    html = auth_client.get("/deadlines").text
    assert f'href="/deadlines/{i}/edit"' in html
    assert f'<form method="post" action="/deadlines/{i}/delete" class="inline-form">' in html
    assert 'class="btn btn-danger"' in html


def test_add_form_uses_fields(auth_client: TestClient) -> None:
    html = auth_client.get("/deadlines").text
    assert html.count('<div class="field">') >= 4
    assert '<textarea id="note" name="note"' in html
    assert 'class="btn btn-primary"' in html


def test_invalid_input_marks_the_field(auth_client: TestClient) -> None:
    r = auth_client.post("/deadlines", data={"title": "", "due_date": "2026-11-20"})
    assert r.status_code == 422
    assert '<div class="field field-invalid">' in r.text
    assert 'aria-describedby="title-error"' in r.text
    assert 'id="title-error"' in r.text


def test_edit_page_uses_fields(db: Any, auth_client: TestClient) -> None:
    i = add(db, "Demo", date(2026, 11, 18))
    html = auth_client.get(f"/deadlines/{i}/edit").text
    assert html.count('class="field') >= 4
    assert 'value="Demo"' in html


@pytest.mark.parametrize("name", ["deadlines.html", "edit.html"])
def test_templates_use_components(name: str) -> None:
    src = template_source(name)
    assert '{% import "_ui.html" as ui with context %}' in src
    for raw in ("<input", "<textarea", "<select", "<table", "style="):
        assert raw not in src, f"{name} contains {raw}"


def test_one_row_markup_for_upcoming_and_past() -> None:
    src = template_source("deadlines.html")
    assert src.count("Bewerken") <= 1, "upcoming and past rows share one macro or include"
