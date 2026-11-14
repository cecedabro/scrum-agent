"""SPEC 10.1-10.4: POST /teams/outgoing (the Teams outgoing webhook)."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Job

KEY = b"k" * 32
SECRET = base64.b64encode(KEY).decode()
NOW = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)  # Monday 16 November, 09:00 Amsterdam


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.clock.now_utc", lambda: NOW)


@pytest.fixture()
def secret(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from app.config import get_settings

    monkeypatch.setenv("TEAMS_HMAC_SECRET", SECRET)
    get_settings.cache_clear()
    yield
    monkeypatch.delenv("TEAMS_HMAC_SECRET")
    get_settings.cache_clear()


def body_for(text: str) -> bytes:
    return json.dumps({"type": "message", "text": f"<at>Agent</at> {text}"}).encode()


def sign(body: bytes, key: bytes = KEY) -> str:
    return "HMAC " + base64.b64encode(hmac.new(key, body, hashlib.sha256).digest()).decode()


def post(client: TestClient, text: str, **headers: str) -> Any:
    body = body_for(text)
    h = {"Content-Type": "application/json", "Authorization": sign(body), **headers}
    return client.post("/teams/outgoing", content=body, headers=h)


def add_deadline(db: Any, title: str, day: date, at: time | None = None) -> None:
    from app.deadlines import DeadlineIn, create

    create(db, DeadlineIn(title=title, due_date=day, due_time=at), now=NOW)
    db.commit()


def test_help_without_basic_auth(client: TestClient, secret: None) -> None:
    r = post(client, "help")
    assert r.status_code == 200
    assert r.json()["type"] == "message"
    assert "deadlines" in r.json()["text"]


def test_deadlines_from_the_db_with_real_labels(db: Any, client: TestClient, secret: None) -> None:
    add_deadline(db, "Demo", date(2026, 11, 16), time(14, 0))
    add_deadline(db, "Verslag", date(2026, 11, 19))
    text = post(client, "Wat zijn de deadlines?").json()["text"]
    assert "- ma 16 nov 14:00 — Demo (vandaag)" in text
    assert "- do 19 nov — Verslag (over 3 dagen)" in text


def test_unknown_question_is_queued(db: Any, client: TestClient, secret: None) -> None:
    r = post(client, "Wat is een burndown chart?")
    assert r.status_code == 200
    assert "wachtrij" in r.json()["text"]
    db.expire_all()
    [job] = db.scalars(select(Job)).all()
    assert (job.kind, job.status, job.title) == ("question", "queued", "Wat is een burndown chart?")


def test_unsigned_is_401(client: TestClient, secret: None) -> None:
    body = body_for("help")
    r = client.post("/teams/outgoing", content=body)
    assert r.status_code == 401
    assert r.content == b""


def test_wrong_signature_is_401(client: TestClient, secret: None) -> None:
    body = body_for("help")
    r = client.post(
        "/teams/outgoing", content=body, headers={"Authorization": sign(body, b"x" * 32)}
    )
    assert r.status_code == 401


def test_no_secret_is_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("TEAMS_HMAC_SECRET", "")
    get_settings.cache_clear()
    try:
        assert post(client, "help").status_code == 503
    finally:
        get_settings.cache_clear()


def test_large_body_is_413(client: TestClient, secret: None) -> None:
    body = json.dumps({"text": "a" * 70_000}).encode()
    r = client.post("/teams/outgoing", content=body, headers={"Authorization": sign(body)})
    assert r.status_code == 413


def test_cross_site_headers_are_fine(client: TestClient, secret: None) -> None:
    r = post(
        client, "help", **{"Sec-Fetch-Site": "cross-site", "Origin": "https://teams.microsoft.com"}
    )
    assert r.status_code == 200


def test_other_routes_still_need_auth_and_csrf(auth_client: TestClient) -> None:
    from fastapi.testclient import TestClient as TC

    anon = TC(auth_client.app)
    assert anon.get("/deadlines").status_code == 401
    r = auth_client.post(
        "/deadlines",
        data={"title": "x", "due_date": "2026-11-20"},
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert r.status_code == 403
