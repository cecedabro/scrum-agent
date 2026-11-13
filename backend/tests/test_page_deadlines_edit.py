"""SPEC 3.4: Deadlines page — list, add, edit, delete, and 404 handling.

Tests use the ``auth_client`` fixture (Basic auth) and ``db`` fixture
(real Postgres, no mocks).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Deadline

# ------------------------------------------------------------------
# GET /deadlines — page renders
# ------------------------------------------------------------------


def test_get_deadlines_page_renders(auth_client: TestClient) -> None:
    """Empty deadlines page renders without error."""
    r = auth_client.get("/deadlines")
    assert r.status_code == 200
    assert b"Deadlines" in r.content
    assert b"Komende deadlines" in r.content
    assert b"Geen komende deadlines" in r.content


def test_get_deadlines_page_shows_upcoming(db, auth_client: TestClient) -> None:
    """Upcoming deadlines are listed on the page."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="Presentie lijst", due_date=date(2026, 11, 20), source="manual")
    create(db, dl, now=now)
    db.commit()

    r = auth_client.get("/deadlines")
    assert r.status_code == 200
    assert b"Presentie lijst" in r.content
    assert b"Komende deadlines" in r.content


def test_get_deadlines_page_shows_past(db, auth_client: TestClient) -> None:
    """Past deadlines are listed in a collapsed section."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="Oude opdracht", due_date=date(2026, 11, 10), source="manual")
    create(db, dl, now=now)
    db.commit()

    r = auth_client.get("/deadlines")
    assert r.status_code == 200
    assert b"Oude opdracht" in r.content
    assert b"Vergane deadlines" in r.content


def test_get_deadlines_page_has_edit_link(db, auth_client: TestClient) -> None:
    """Each deadline row has an edit link pointing to /deadlines/{id}/edit."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="Bewerken test", due_date=date(2026, 11, 20), source="manual")
    create(db, dl, now=now)
    db.commit()

    r = auth_client.get("/deadlines")
    assert r.status_code == 200
    assert b"/deadlines/1/edit" in r.content
    assert b"Bewerken" in r.content


def test_get_deadlines_page_has_delete_button(db, auth_client: TestClient) -> None:
    """Each deadline row has a delete button inside a form."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="Verwijder test", due_date=date(2026, 11, 20), source="manual")
    create(db, dl, now=now)
    db.commit()

    r = auth_client.get("/deadlines")
    assert r.status_code == 200
    assert b"Verwijderen" in r.content
    assert b"/deadlines/1/delete" in r.content


def test_get_deadlines_page_has_add_form(auth_client: TestClient) -> None:
    """The deadlines page includes a form to add a new deadline."""
    r = auth_client.get("/deadlines")
    assert r.status_code == 200
    assert b"Deadline toevoegen" in r.content
    assert b'name="title"' in r.content
    assert b'name="due_date"' in r.content


# ------------------------------------------------------------------
# POST /deadlines — add a deadline
# ------------------------------------------------------------------


def test_post_deadline_adds_to_page(db, auth_client: TestClient) -> None:
    """Valid POST to /deadlines creates a deadline and redirects."""
    payload = {
        "title": "Toegevoegd",
        "due_date": "2026-12-01",
        "due_time": "10:00",
        "note": "Een notitie",
    }
    r = auth_client.post(
        "/deadlines",
        data=payload,
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)

    # Follow the redirect
    r2 = auth_client.get("/deadlines")
    assert r2.status_code == 200
    assert b"Toegevoegd" in r2.content
    assert b"Een notitie" in r2.content


def test_post_deadline_stored_in_db(db, auth_client: TestClient) -> None:
    """POST /deadlines persists the deadline in the database."""
    payload = {
        "title": "Database test",
        "due_date": "2026-11-25",
    }
    auth_client.post("/deadlines", data=payload, follow_redirects=False)

    existing = db.execute(
        select(Deadline).where(Deadline.title == "Database test")
    ).scalar_one_or_none()
    assert existing is not None
    assert existing.title == "Database test"
    assert existing.due_date == date(2026, 11, 25)
    assert existing.note is None


def test_post_deadline_minimal_fields(db, auth_client: TestClient) -> None:
    """POST with only title and due_date works."""
    payload = {
        "title": "Minimaal",
        "due_date": "2026-12-15",
    }
    auth_client.post("/deadlines", data=payload, follow_redirects=False)

    existing = db.execute(select(Deadline).where(Deadline.title == "Minimaal")).scalar_one_or_none()
    assert existing is not None


def test_post_deadline_redirects_back(auth_client: TestClient) -> None:
    """POST /deadlines redirects to /deadlines."""
    payload = {
        "title": "Redirect test",
        "due_date": "2026-11-25",
    }
    r = auth_client.post("/deadlines", data=payload, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers.get("location", "").startswith("/deadlines")


# ------------------------------------------------------------------
# POST /deadlines — form validation errors
# ------------------------------------------------------------------


def test_post_deadline_empty_title_shows_error(auth_client: TestClient) -> None:
    """Empty title shows validation error and re-renders the form."""
    payload = {
        "title": "",
        "due_date": "2026-11-25",
    }
    r = auth_client.post("/deadlines", data=payload)
    assert r.status_code == 200
    assert b"Titel mag niet leeg zijn" in r.content
    assert b'name="title"' in r.content


def test_post_deadline_long_title_shows_error(auth_client: TestClient) -> None:
    """Title longer than 200 chars shows validation error."""
    long_title = "A" * 201
    payload = {
        "title": long_title,
        "due_date": "2026-11-25",
    }
    r = auth_client.post("/deadlines", data=payload)
    assert r.status_code == 200
    assert b"Titel mag maximaal 200 tekens bevatten" in r.content


def test_post_deadline_invalid_date_shows_error(auth_client: TestClient) -> None:
    """Invalid date format shows validation error."""
    payload = {
        "title": "Geldige titel",
        "due_date": "not-a-date",
    }
    r = auth_client.post("/deadlines", data=payload)
    assert r.status_code == 200
    assert b"Ongeldige datum" in r.content


def test_post_deadline_invalid_time_shows_error(auth_client: TestClient) -> None:
    """Invalid time format shows validation error."""
    payload = {
        "title": "Geldige titel",
        "due_date": "2026-11-25",
        "due_time": "25:99",
    }
    r = auth_client.post("/deadlines", data=payload)
    assert r.status_code == 200
    assert b"Ongeldige tijd" in r.content


def test_post_deadline_preserves_input_on_error(db, auth_client: TestClient) -> None:
    """Validation errors re-render the form with user input preserved."""
    payload_err = {
        "title": "",
        "due_date": "2026-11-25",
        "due_time": "10:00",
        "note": "Blijft zichtbaar",
    }
    r = auth_client.post("/deadlines", data=payload_err)
    assert r.status_code == 200
    assert b'value=""' in r.content
    assert b"Blijft zichtbaar" in r.content


# ------------------------------------------------------------------
# GET /deadlines/{id}/edit
# ------------------------------------------------------------------


def test_get_edit_page_renders(db, auth_client: TestClient) -> None:
    """Edit page renders with deadline data pre-filled."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(
        title="Edit test",
        due_date=date(2026, 11, 20),
        due_time=time(14, 30),
        note="Bestaande notitie",
        source="manual",
    )
    create(db, dl, now=now)
    db.commit()

    r = auth_client.get("/deadlines/1/edit")
    assert r.status_code == 200
    assert b"Edit test" in r.content
    assert b"2026-11-20" in r.content
    assert b"14:30" in r.content
    assert b"Bestaande notitie" in r.content


def test_get_edit_page_404_unknown_id(auth_client: TestClient) -> None:
    """GET /deadlines/{id}/edit returns 404 for unknown deadline."""
    r = auth_client.get("/deadlines/99999/edit")
    assert r.status_code == 404
    assert b"Deadline niet gevonden" in r.content


def test_get_edit_page_with_no_time(db, auth_client: TestClient) -> None:
    """Edit page renders correctly when no due_time is set."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="Geen tijd", due_date=date(2026, 11, 20), source="manual")
    create(db, dl, now=now)
    db.commit()

    r = auth_client.get("/deadlines/1/edit")
    assert r.status_code == 200
    assert b"Geen tijd" in r.content


# ------------------------------------------------------------------
# POST /deadlines/{id}/edit
# ------------------------------------------------------------------


def test_post_edit_saves_changes(db, auth_client: TestClient) -> None:
    """POST to edit page updates the deadline."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="Oude naam", due_date=date(2026, 11, 20), source="manual")
    create(db, dl, now=now)
    db.commit()

    payload = {
        "title": "Nieuwe naam",
        "due_date": "2026-12-01",
        "due_time": "09:00",
        "note": "Bijgewerkte notitie",
    }
    auth_client.post("/deadlines/1/edit", data=payload, follow_redirects=False)

    updated = db.execute(select(Deadline).where(Deadline.id == 1)).scalar_one_or_none()
    assert updated is not None
    assert updated.title == "Nieuwe naam"
    assert updated.due_date == date(2026, 12, 1)
    assert updated.due_time == time(9, 0)
    assert updated.note == "Bijgewerkte notitie"


def test_post_edit_redirects_to_deadlines(db, auth_client: TestClient) -> None:
    """POST to edit page redirects to /deadlines."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="Redirect edit", due_date=date(2026, 11, 20), source="manual")
    create(db, dl, now=now)
    db.commit()

    payload = {
        "title": "Redirect edit",
        "due_date": "2026-11-20",
    }
    r = auth_client.post("/deadlines/1/edit", data=payload, follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers.get("location", "").startswith("/deadlines")


def test_post_edit_404_unknown_id(auth_client: TestClient) -> None:
    """POST to edit page returns 404 for unknown deadline."""
    payload = {
        "title": "Niet bestaan",
        "due_date": "2026-11-25",
    }
    r = auth_client.post("/deadlines/99999/edit", data=payload)
    assert r.status_code == 404
    assert b"Deadline niet gevonden" in r.content


def test_post_edit_validation_empty_title(db, auth_client: TestClient) -> None:
    """Empty title on edit shows validation error and does not save."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="Oorspronkelijk", due_date=date(2026, 11, 20), source="manual")
    create(db, dl, now=now)
    db.commit()

    payload = {
        "title": "",
        "due_date": "2026-11-20",
    }
    r = auth_client.post("/deadlines/1/edit", data=payload)
    assert r.status_code == 200
    assert b"Titel mag niet leeg zijn" in r.content

    original = db.execute(
        select(Deadline).where(Deadline.title == "Oorspronkelijk")
    ).scalar_one_or_none()
    assert original is not None


def test_post_edit_validation_long_title(db, auth_client: TestClient) -> None:
    """Title > 200 chars on edit shows validation error."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="Lang", due_date=date(2026, 11, 20), source="manual")
    create(db, dl, now=now)
    db.commit()

    long_title = "B" * 201
    payload = {
        "title": long_title,
        "due_date": "2026-11-20",
    }
    r = auth_client.post("/deadlines/1/edit", data=payload)
    assert r.status_code == 200
    assert b"Titel mag maximaal 200 tekens bevatten" in r.content


def test_post_edit_validation_invalid_date(db, auth_client: TestClient) -> None:
    """Invalid date on edit shows validation error."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="Datum", due_date=date(2026, 11, 20), source="manual")
    create(db, dl, now=now)
    db.commit()

    payload = {
        "title": "Datum",
        "due_date": "bad-date",
    }
    r = auth_client.post("/deadlines/1/edit", data=payload)
    assert r.status_code == 200
    assert b"Ongeldige datum" in r.content


def test_post_edit_validation_invalid_time(db, auth_client: TestClient) -> None:
    """Invalid time on edit shows validation error."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="Tijd", due_date=date(2026, 11, 20), source="manual")
    create(db, dl, now=now)
    db.commit()

    payload = {
        "title": "Tijd",
        "due_date": "2026-11-20",
        "due_time": "invalid",
    }
    r = auth_client.post("/deadlines/1/edit", data=payload)
    assert r.status_code == 200
    assert b"Ongeldige tijd" in r.content


# ------------------------------------------------------------------
# POST /deadlines/{id}/delete
# ------------------------------------------------------------------


def test_post_delete_removes_deadline(db, auth_client: TestClient) -> None:
    """POST to delete endpoint removes the deadline from the database."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="Te verwijderen", due_date=date(2026, 12, 1), source="manual")
    create(db, dl, now=now)
    db.commit()

    auth_client.post("/deadlines/1/delete", follow_redirects=False)

    remaining = db.execute(select(Deadline).where(Deadline.id == 1)).scalar_one_or_none()
    assert remaining is None


def test_post_delete_redirects_to_deadlines(db, auth_client: TestClient) -> None:
    """POST to delete endpoint redirects to /deadlines."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="Delete redirect", due_date=date(2026, 12, 1), source="manual")
    create(db, dl, now=now)
    db.commit()

    r = auth_client.post("/deadlines/1/delete", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers.get("location", "").startswith("/deadlines")


def test_post_delete_404_unknown_id(auth_client: TestClient) -> None:
    """POST to delete endpoint returns 404 for unknown deadline."""
    r = auth_client.post("/deadlines/99999/delete")
    assert r.status_code == 404
    assert b"Deadline niet gevonden" in r.content


def test_post_delete_removes_from_page(db, auth_client: TestClient) -> None:
    """After deleting, the deadline no longer appears on the page."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="Verdwijn", due_date=date(2026, 12, 1), source="manual")
    create(db, dl, now=now)
    db.commit()

    auth_client.post("/deadlines/1/delete", follow_redirects=False)

    r = auth_client.get("/deadlines")
    assert r.status_code == 200
    assert b"Verdwijn" not in r.content


def test_post_delete_multiple_deadlines_keeps_others(db, auth_client: TestClient) -> None:
    """Deleting one deadline does not affect others."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    keep = DeadlineIn(title="Blijven", due_date=date(2026, 12, 1), source="manual")
    remove = DeadlineIn(title="Verdwijn", due_date=date(2026, 12, 2), source="manual")
    create(db, keep, now=now)
    create(db, remove, now=now)
    db.commit()

    auth_client.post("/deadlines/2/delete", follow_redirects=False)

    r = auth_client.get("/deadlines")
    assert r.status_code == 200
    assert b"Blijven" in r.content
    assert b"Verdwijn" not in r.content
