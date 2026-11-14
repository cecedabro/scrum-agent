"""SPEC 10.4–10.6: question job queue and Teams incoming webhook.

Tests cover:
- unknown question -> `question` job stored with cleaned/cut text
- both `model_status` replies (up / down)
- 6th question refused and not stored
- question jobs do not appear on `/meetings`
"""

from __future__ import annotations

import base64
import hashlib
import hmac as hmac_mod
import json
import os
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient

from app.models import AppState, Job

NOW = datetime(2026, 11, 16, 8, 0, tzinfo=UTC)
TEST_SECRET = b"test-secret-32-bytes-long........"


def _sign_body(body: bytes, secret: bytes = TEST_SECRET) -> str:
    """Return HMAC header value for *body*."""
    sig = base64.b64encode(hmac_mod.new(secret, body, hashlib.sha256).digest()).decode()
    return f"HMAC {sig}"


def _model_status(db, up: bool, last_up_at: datetime | None = None) -> None:
    db.add(
        AppState(
            key="model_status",
            value={
                "up": up,
                "checked_at": NOW.isoformat(),
                "last_up_at": last_up_at.isoformat() if last_up_at else None,
            },
        )
    )
    db.commit()


def _make_client(secret: bytes = TEST_SECRET):
    """Create a TestClient with TEAMS_HMAC_SECRET configured."""
    encoded_secret = base64.b64encode(secret).decode()
    os.environ["TEAMS_HMAC_SECRET"] = encoded_secret
    from app.config import get_settings

    get_settings.cache_clear()
    from app.main import create_app

    return TestClient(create_app())


# --- question job storage (cleaned/cut text) -------------------------------------------


def test_question_job_stores_cleaned_cut_text(db, client):
    """Unknown question creates a job with cleaned, truncated text."""
    _model_status(db, True)
    c = _make_client()
    long_text = "a" * 600
    body = json.dumps({"text": long_text}).encode()
    headers = {"Authorization": _sign_body(body), "Content-Type": "application/json"}
    r = c.post("/teams/outgoing", content=body, headers=headers)
    r.raise_for_status()
    reply = r.json()
    assert "Ik denk even" in reply["text"]

    with next(__import__("app.db", fromlist=["get_db"]).get_db()) as session:
        jobs = session.query(Job).filter(Job.kind == "question", Job.title == long_text[:500]).all()
        assert len(jobs) == 1


def test_question_job_has_no_sender_name(db, client):
    """Sender name from Teams is not stored on the job."""
    c = _make_client()
    body = json.dumps({"text": "willekeurige vraag"}).encode()
    headers = {"Authorization": _sign_body(body), "Content-Type": "application/json"}
    c.post("/teams/outgoing", content=body, headers=headers)

    with next(__import__("app.db", fromlist=["get_db"]).get_db()) as session:
        job = session.query(Job).filter(Job.kind == "question").first()
        assert job is not None
        assert job.title == "willekeurige vraag"


# --- model_status replies ---------------------------------------------------------------


def test_reply_up_when_model_status_up(db, client):
    """When model_status is up, reply says 'Ik denk even na'."""
    _model_status(db, True)
    c = _make_client()
    resp = c.post(
        "/teams/outgoing",
        content=json.dumps({"text": "onbekende vraag"}).encode(),
        headers={
            "Authorization": _sign_body(b'{"text": "onbekende vraag"}'),
            "Content-Type": "application/json",
        },
    )
    resp.raise_for_status()
    assert "Ik denk even na" in resp.json()["text"]


def test_reply_down_when_model_status_down(db, client):
    """When model_status is down, reply mentions the PC is sleeping."""
    _model_status(db, False)
    c = _make_client()
    resp = c.post(
        "/teams/outgoing",
        content=json.dumps({"text": "wacht vraag"}).encode(),
        headers={
            "Authorization": _sign_body(b'{"text": "wacht vraag"}'),
            "Content-Type": "application/json",
        },
    )
    resp.raise_for_status()
    text = resp.json()["text"]
    assert "pc" in text.lower() and "slaapt" in text


# --- 5-question limit -------------------------------------------------------------------


def test_sixth_question_refused(db, client):
    """The 6th queued question is refused and not stored."""
    _model_status(db, True)
    c = _make_client()

    for i in range(5):
        payload = json.dumps({"text": f"vraag nummer {i}"}).encode()
        c.post(
            "/teams/outgoing",
            content=payload,
            headers={"Authorization": _sign_body(payload), "Content-Type": "application/json"},
        )

    with next(__import__("app.db", fromlist=["get_db"]).get_db()) as session:
        count = session.query(Job).filter(Job.kind == "question", Job.status == "queued").count()
        assert count == 5

    payload = json.dumps({"text": "zesde vraag"}).encode()
    r = c.post(
        "/teams/outgoing",
        content=payload,
        headers={"Authorization": _sign_body(payload), "Content-Type": "application/json"},
    )
    r.raise_for_status()
    assert "5" in r.json()["text"] or "wachtrij" in r.json()["text"].lower()

    with next(__import__("app.db", fromlist=["get_db"]).get_db()) as session:
        count = session.query(Job).filter(Job.kind == "question", Job.status == "queued").count()
        assert count == 5


# --- /meetings excludes question jobs ---------------------------------------------------


def test_question_jobs_not_on_meetings(auth_client, db):
    """Question jobs do not appear on the /meetings page."""
    job = Job(
        kind="question",
        status="queued",
        title="Een vraag",
        meeting_date=date(2026, 11, 16),
    )
    db.add(job)
    db.commit()

    html = auth_client.get("/meetings").text
    assert "Een vraag" not in html


def test_summary_jobs_still_on_meetings(auth_client, db):
    """Summary jobs still appear on /meetings."""
    job = Job(
        kind="summary",
        status="done",
        title="Planning samenvatting",
        meeting_date=date(2026, 11, 16),
    )
    db.add(job)
    db.commit()

    html = auth_client.get("/meetings").text
    assert "Planning samenvatting" in html
