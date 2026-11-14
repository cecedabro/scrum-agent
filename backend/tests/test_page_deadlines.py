"""SPEC 3.2-3.3: the /deadlines page (list, labels, add form). Written by a human for T09.

"Today" is fixed by patching `app.clock.now_utc`, the only function that reads the real
clock (docs/backend.md §Time). The page must therefore get today's date through
`app.clock` (for example `today_local()` without arguments), not from its own clock.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models import Deadline

# Monday 16 November 2026, 09:00 in Amsterdam.
NOW = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)

PENDING_UNTIL = "T09"  # see backend/conftest.py


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.clock.now_utc", lambda: NOW)


def add(db: Any, title: str, day: date, at: time | None = None, note: str | None = None) -> None:
    from app.deadlines import DeadlineIn, create

    create(db, DeadlineIn(title=title, due_date=day, due_time=at, note=note), now=NOW)
    db.commit()


def count(db: Any) -> int:
    db.expire_all()
    return int(db.scalar(select(func.count()).select_from(Deadline)))


def upcoming_part(html: str) -> str:
    """The page up to the collapsed past section (or the add form)."""
    end = html.find("<details")
    return html if end == -1 else html[:end]


def past_part(html: str) -> str:
    start = html.find("<details")
    assert start != -1, "past deadlines must be in a <details> section"
    return html[start : html.find("</details>", start)]


def test_empty_state(auth_client: TestClient) -> None:
    r = auth_client.get("/deadlines")
    assert r.status_code == 200
    assert "Geen komende deadlines" in r.text
    assert "<details" not in r.text  # no past section when there is nothing past


def test_requires_login(client: TestClient) -> None:
    assert client.get("/deadlines").status_code == 401


def test_dutch_date_and_relative_labels(db: Any, auth_client: TestClient) -> None:
    add(db, "Vandaag-ding", date(2026, 11, 16))
    add(db, "Morgen-ding", date(2026, 11, 17))
    add(db, "Later-ding", date(2026, 11, 19))
    html = auth_client.get("/deadlines").text
    assert "maandag 16 november" in html
    assert "dinsdag 17 november" in html
    assert "donderdag 19 november" in html
    assert "vandaag" in html
    assert "morgen" in html
    assert "over 3 dagen" in html


def test_upcoming_sorted_by_date_then_time(db: Any, auth_client: TestClient) -> None:
    add(db, "Derde", date(2026, 11, 20))
    add(db, "Tweede-zonder-tijd", date(2026, 11, 18))  # no time = end of the day
    add(db, "Eerste-met-tijd", date(2026, 11, 18), time(10, 0))
    add(db, "Nul-vandaag", date(2026, 11, 16), time(23, 0))
    html = upcoming_part(auth_client.get("/deadlines").text)
    order = ["Nul-vandaag", "Eerste-met-tijd", "Tweede-zonder-tijd", "Derde"]
    positions = [html.find(t) for t in order]
    assert all(p != -1 for p in positions), positions
    assert positions == sorted(positions)


def test_time_shown_when_set(db: Any, auth_client: TestClient) -> None:
    add(db, "Met tijd", date(2026, 11, 18), time(14, 30))
    assert "14:30" in auth_client.get("/deadlines").text


def test_past_deadlines_collapsed(db: Any, auth_client: TestClient) -> None:
    add(db, "Oud-ding", date(2026, 11, 13))
    add(db, "Nieuw-ding", date(2026, 11, 18))
    html = auth_client.get("/deadlines").text
    assert "Oud-ding" not in upcoming_part(html)
    assert "Oud-ding" in past_part(html)
    assert "Nieuw-ding" not in past_part(html)
    assert "<details open" not in html  # collapsed by default


def test_today_counts_as_upcoming(db: Any, auth_client: TestClient) -> None:
    add(db, "Vandaag-deadline", date(2026, 11, 16), time(8, 0))  # earlier today: still listed
    html = auth_client.get("/deadlines").text
    assert "Vandaag-deadline" in upcoming_part(html)


def test_add_redirects_and_stores(db: Any, auth_client: TestClient) -> None:
    r = auth_client.post(
        "/deadlines",
        data={
            "title": "Sprint review",
            "due_date": "2026-11-27",
            "due_time": "13:15",
            "note": "Demo voorbereiden",
        },
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/deadlines"
    db.expire_all()
    row = db.scalars(select(Deadline)).one()
    assert (row.title, row.due_date, row.due_time, row.note) == (
        "Sprint review",
        date(2026, 11, 27),
        time(13, 15),
        "Demo voorbereiden",
    )
    assert row.source == "manual"
    assert "Sprint review" in auth_client.get("/deadlines").text


def test_add_without_time_and_note(db: Any, auth_client: TestClient) -> None:
    r = auth_client.post(
        "/deadlines",
        data={"title": "Inleveren", "due_date": "2026-12-01", "due_time": "", "note": ""},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db.expire_all()
    row = db.scalars(select(Deadline)).one()
    assert row.due_time is None
    assert not row.note


ENGLISH = ("String should", "Field required", "Input should", "value_error", "Traceback")


@pytest.mark.parametrize(
    ("form", "field"),
    [
        ({"title": "", "due_date": "2026-11-27"}, "title"),
        ({"title": "   ", "due_date": "2026-11-27"}, "title"),
        ({"title": "x" * 201, "due_date": "2026-11-27"}, "title"),
        ({"title": "Geldig", "due_date": "niet-een-datum"}, "due_date"),
        ({"title": "Geldig", "due_date": ""}, "due_date"),
        ({"title": "Geldig", "due_date": "2026-11-27", "due_time": "25:99"}, "due_time"),
        ({"title": "Geldig", "due_date": "2026-11-27", "note": "n" * 1001}, "note"),
    ],
)
def test_invalid_input_422_and_nothing_stored(
    db: Any, auth_client: TestClient, form: dict[str, str], field: str
) -> None:
    r = auth_client.post("/deadlines", data=form, follow_redirects=False)
    assert r.status_code == 422, r.text[:300]
    assert 'class="error"' in r.text
    assert not any(word in r.text for word in ENGLISH)
    assert f'name="{field}"' in r.text  # the form is shown again
    assert count(db) == 0


def test_invalid_input_keeps_typed_values(auth_client: TestClient) -> None:
    r = auth_client.post(
        "/deadlines", data={"title": "Mijn titel", "due_date": "fout", "note": "Mijn notitie"}
    )
    assert r.status_code == 422
    assert 'value="Mijn titel"' in r.text
    assert "Mijn notitie" in r.text


def test_exactly_200_chars_is_fine(db: Any, auth_client: TestClient) -> None:
    r = auth_client.post(
        "/deadlines", data={"title": "x" * 200, "due_date": "2026-11-27"}, follow_redirects=False
    )
    assert r.status_code == 303
    assert count(db) == 1
