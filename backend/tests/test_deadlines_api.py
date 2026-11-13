"""SPEC 3.5: JSON API for deadlines (GET /api/v1/deadlines, POST, DELETE).

Tests use the ``auth_client`` fixture (Basic auth) and ``db`` fixture
(real Postgres, no mocks).
"""

from __future__ import annotations

import base64
from datetime import UTC, date, datetime, time

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.config import get_settings
from app.main import create_app
from app.models import Deadline


def _auth_headers() -> dict[str, str]:
    settings = get_settings()
    encoded = base64.b64encode(f"{settings.TEAM_USER}:{settings.TEAM_PASSWORD}".encode()).decode()
    return {"Authorization": f"Basic {encoded}"}


# ------------------------------------------------------------------
# GET /api/v1/deadlines — field names and formats
# ------------------------------------------------------------------


def test_get_deadlines_empty(auth_client: TestClient) -> None:
    """Empty list when no deadlines exist."""
    r = auth_client.get("/api/v1/deadlines")
    assert r.status_code == 200
    assert r.json() == []


def test_get_deadlines_field_names_and_formats(db, auth_client: TestClient) -> None:
    """Response contains correct fields with ISO date and HH:MM time."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    data = DeadlineIn(
        title="Test deadline",
        due_date=date(2026, 11, 20),
        due_time=time(14, 30),
        note="A note",
        source="manual",
    )
    create(db, data, now=now)
    db.commit()

    r = auth_client.get("/api/v1/deadlines")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    entry = body[0]
    assert "id" in entry
    assert "title" in entry
    assert "due_date" in entry
    assert "due_time" in entry
    assert "note" in entry
    assert "source" in entry
    assert entry["title"] == "Test deadline"
    assert entry["due_date"] == "2026-11-20"
    assert entry["due_time"] == "14:30:00"
    assert entry["note"] == "A note"
    assert entry["source"] == "manual"
    assert isinstance(entry["id"], int)


def test_get_deadlines_null_due_time(db, auth_client: TestClient) -> None:
    """due_time is null when no time is set."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    data = DeadlineIn(
        title="Date only",
        due_date=date(2026, 11, 18),
        due_time=None,
        source="manual",
    )
    create(db, data, now=now)
    db.commit()

    r = auth_client.get("/api/v1/deadlines")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["due_time"] is None


# ------------------------------------------------------------------
# include_past
# ------------------------------------------------------------------


def test_include_past_false_excludes_past(db, auth_client: TestClient) -> None:
    """Without include_past, past deadlines are not returned."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    future = DeadlineIn(
        title="Future",
        due_date=date(2026, 12, 1),
        source="manual",
    )
    past_deadline = DeadlineIn(
        title="Past",
        due_date=date(2026, 11, 10),
        source="manual",
    )
    create(db, future, now=now)
    create(db, past_deadline, now=now)
    db.commit()

    r = auth_client.get("/api/v1/deadlines")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["title"] == "Future"


def test_include_past_true_returns_all(db, auth_client: TestClient) -> None:
    """With include_past=true, both past and upcoming deadlines are returned."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    future = DeadlineIn(
        title="Future",
        due_date=date(2026, 12, 1),
        source="manual",
    )
    past_deadline = DeadlineIn(
        title="Past",
        due_date=date(2026, 11, 10),
        source="manual",
    )
    create(db, future, now=now)
    create(db, past_deadline, now=now)
    db.commit()

    r = auth_client.get("/api/v1/deadlines", params={"include_past": "true"})
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 2
    titles = {e["title"] for e in body}
    assert "Future" in titles
    assert "Past" in titles


def test_include_past_returns_today(db, auth_client: TestClient) -> None:
    """Today's deadlines are included without include_past."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    today = DeadlineIn(
        title="Today",
        due_date=date(2026, 11, 16),
        source="manual",
    )
    create(db, today, now=now)
    db.commit()

    r = auth_client.get("/api/v1/deadlines")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["title"] == "Today"


# ------------------------------------------------------------------
# POST /api/v1/deadlines — 201
# ------------------------------------------------------------------


def test_post_deadline_returns_201(db, auth_client: TestClient) -> None:
    """Valid POST returns 201 with the created object."""
    payload = {
        "title": "New deadline",
        "due_date": "2026-11-25",
        "due_time": "10:00:00",
        "note": "Test note",
        "source": "manual",
    }
    r = auth_client.post("/api/v1/deadlines", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "New deadline"
    assert body["due_date"] == "2026-11-25"
    assert body["due_time"] == "10:00:00"
    assert body["note"] == "Test note"
    assert body["source"] == "manual"
    assert isinstance(body["id"], int)


def test_post_deadline_stored_in_db(db, auth_client: TestClient) -> None:
    """POST 201 means the deadline is persisted in the database."""
    payload = {
        "title": "Stored deadline",
        "due_date": "2026-11-30",
        "source": "manual",
    }
    auth_client.post("/api/v1/deadlines", json=payload)

    count = db.execute(
        select(Deadline).where(Deadline.title == "Stored deadline")
    ).scalar_one_or_none()
    assert count is not None
    assert count.title == "Stored deadline"
    assert count.due_date == date(2026, 11, 30)


def test_post_deadline_minimal_fields(db, auth_client: TestClient) -> None:
    """POST with only title and due_date works (note/due_time optional)."""
    payload = {"title": "Minimal", "due_date": "2026-12-15", "source": "manual"}
    r = auth_client.post("/api/v1/deadlines", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Minimal"
    assert body["due_time"] is None
    assert body["note"] is None


# ------------------------------------------------------------------
# POST /api/v1/deadlines — 422 stores nothing
# ------------------------------------------------------------------


def test_post_deadline_422_stores_nothing(db, auth_client: TestClient) -> None:
    """Invalid POST returns 422 and stores nothing."""
    before_count = db.execute(select(Deadline)).scalars().all()
    count_before = len(before_count)

    payload = {"title": "", "due_date": "2026-11-25", "source": "manual"}
    r = auth_client.post("/api/v1/deadlines", json=payload)
    assert r.status_code == 422

    after_count = db.execute(select(Deadline)).scalars().all()
    assert len(after_count) == count_before


def test_post_deadline_422_invalid_source(db, auth_client: TestClient) -> None:
    """Invalid source field returns 422."""
    payload = {
        "title": "Bad source",
        "due_date": "2026-11-25",
        "source": "unknown",
    }
    r = auth_client.post("/api/v1/deadlines", json=payload)
    assert r.status_code == 422
    body = r.json()
    assert "detail" in body


def test_post_deadline_422_missing_title(db, auth_client: TestClient) -> None:
    """Missing title returns 422."""
    before_count = db.execute(select(Deadline)).scalars().all()

    payload = {"due_date": "2026-11-25", "source": "manual"}
    r = auth_client.post("/api/v1/deadlines", json=payload)
    assert r.status_code == 422

    after_count = db.execute(select(Deadline)).scalars().all()
    assert len(after_count) == len(before_count)


# ------------------------------------------------------------------
# DELETE /api/v1/deadlines/{id} — 204
# ------------------------------------------------------------------


def test_delete_deadline_returns_204(db, auth_client: TestClient) -> None:
    """Existing deadline deleted returns 204."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="To delete", due_date=date(2026, 12, 1), source="manual")
    created = create(db, dl, now=now)
    db.commit()

    r = auth_client.delete(f"/api/v1/deadlines/{created.id}")
    assert r.status_code == 204
    assert r.text == ""


def test_delete_deadline_removed_from_db(db, auth_client: TestClient) -> None:
    """Deleted deadline no longer exists in the database."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl = DeadlineIn(title="Delete me", due_date=date(2026, 12, 1), source="manual")
    created = create(db, dl, now=now)
    db.commit()

    auth_client.delete(f"/api/v1/deadlines/{created.id}")

    remaining = db.execute(select(Deadline).where(Deadline.id == created.id)).scalar_one_or_none()
    assert remaining is None


def test_delete_deadline_reduces_list(db, auth_client: TestClient) -> None:
    """Deleting a deadline removes it from the GET list."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    dl1 = DeadlineIn(title="Keep", due_date=date(2026, 12, 1), source="manual")
    dl2 = DeadlineIn(title="Remove", due_date=date(2026, 12, 2), source="manual")
    create(db, dl1, now=now)
    created = create(db, dl2, now=now)
    db.commit()

    auth_client.delete(f"/api/v1/deadlines/{created.id}")

    r = auth_client.get("/api/v1/deadlines")
    body = r.json()
    assert len(body) == 1
    assert body[0]["title"] == "Keep"


# ------------------------------------------------------------------
# DELETE /api/v1/deadlines/{id} — 404
# ------------------------------------------------------------------


def test_delete_nonexistent_returns_404(auth_client: TestClient) -> None:
    """Deleting an unknown id returns 404."""
    r = auth_client.delete("/api/v1/deadlines/99999")
    assert r.status_code == 404
    body = r.json()
    assert "detail" in body


# ------------------------------------------------------------------
# Auth required
# ------------------------------------------------------------------


def test_get_deadlines_requires_auth(db: object) -> None:
    """Unauthenticated GET returns 401."""
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/api/v1/deadlines")
    assert r.status_code == 401
    assert "WWW-Authenticate" in r.headers


def test_post_deadlines_requires_auth(db: object) -> None:
    """Unauthenticated POST returns 401."""
    app = create_app()
    with TestClient(app) as c:
        r = c.post(
            "/api/v1/deadlines",
            json={"title": "Hacked", "due_date": "2026-11-25", "source": "manual"},
        )
    assert r.status_code == 401


def test_delete_deadlines_requires_auth(db: object) -> None:
    """Unauthenticated DELETE returns 401."""
    app = create_app()
    with TestClient(app) as c:
        r = c.delete("/api/v1/deadlines/1")
    assert r.status_code == 401


# ------------------------------------------------------------------
# Sorting — upcoming returns sorted by date/time
# ------------------------------------------------------------------


def test_get_deadlines_sorted_by_date_time(db, auth_client: TestClient) -> None:
    """Upcoming deadlines are returned sorted by date then time."""
    from app.deadlines import DeadlineIn, create

    now = datetime(2026, 11, 16, 7, 30, tzinfo=UTC)
    d1 = DeadlineIn(
        title="Later same day", due_date=date(2026, 11, 20), due_time=time(18, 0), source="manual"
    )
    d2 = DeadlineIn(
        title="Earlier same day", due_date=date(2026, 11, 20), due_time=time(9, 0), source="manual"
    )
    d3 = DeadlineIn(
        title="Next day", due_date=date(2026, 11, 21), due_time=time(12, 0), source="manual"
    )
    create(db, d1, now=now)
    create(db, d2, now=now)
    create(db, d3, now=now)
    db.commit()

    r = auth_client.get("/api/v1/deadlines")
    assert r.status_code == 200
    titles = [e["title"] for e in r.json()]
    assert titles == ["Earlier same day", "Later same day", "Next day"]
