"""Teams incoming webhook utilities and route (SPEC 10.1–10.6).

``verify_hmac`` checks the HMAC-SHA256 signature that Microsoft Teams sends
with every outgoing-webhook POST.  ``clean_text`` sanitises the HTML message
body before matching or further processing.

``handle_teams_message`` is a FastAPI endpoint that processes incoming Teams
messages: quick-answer known patterns, or queue unknown questions as ``job``
rows with a 5-job limit.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from datetime import date
from html import unescape
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.answers import quick_answer
from app.clock import today_local
from app.config import get_settings
from app.db import get_db
from app.deadlines import upcoming
from app.fmt import relatief
from app.models import AppState, Job
from app.settings import load

__all__ = ["verify_hmac", "clean_text", "router"]

router = APIRouter()

# Reply texts (SPEC 10.4)
_REPLY_UP = "Ik denk even na; het antwoord komt zo in dit kanaal."
_REPLY_DOWN = (
    "De pc met het taalmodel slaapt. Je vraag staat in de wachtrij; "
    "het antwoord komt in dit kanaal zodra hij aan is."
)
_REPLY_FULL = "Er staan al 5 vragen in de wachtrij; probeer het later nog eens."


def verify_hmac(body: bytes, header: str | None, secret_b64: str) -> bool:
    """Verify the HMAC-SHA256 signature of *body* against *header*.

    *header* is the raw ``Authorization`` header value from the request
    (for example ``"HMAC dGhlIHNlY3JldA=="``).

    Returns ``True`` only when the header is present, *secret_b64* is valid
    base64, and the computed HMAC matches the signature after stripping the
    optional ``HMAC `` prefix.
    """
    if not header or not header.startswith("HMAC "):
        return False

    try:
        secret_bytes = base64.b64decode(secret_b64, validate=True)
    except Exception:
        return False

    value = header[5:]

    expected = base64.b64encode(hmac.new(secret_bytes, body, hashlib.sha256).digest())

    return hmac.compare_digest(expected, value.encode())


def clean_text(text: str) -> str:
    """Clean a Teams message body for matching / storage.

    Strips every ``<at>...</at>`` mention tag and all other HTML tags,
    decodes HTML entities, collapses whitespace runs to a single space, and
    trims the result.
    """
    text = re.sub(r"<at>[^<]*</at>", "", text)
    text = re.sub(r"<[^>]*>", "", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _get_model_up(session: Any) -> bool:
    """Return ``True`` when the model is currently available."""
    row = session.query(AppState).filter(AppState.key == "model_status").first()
    return bool(row and row.value and row.value.get("up"))


def _count_queued_questions(session: Any) -> int:
    """Return the number of queued ``question`` jobs."""
    return int(session.query(Job).filter(Job.kind == "question", Job.status == "queued").count())


MAX_BODY_BYTES = 64 * 1024  # SPEC 10.1


@router.post("/teams/outgoing")
async def handle_teams_message(request: Request, session: Session = Depends(get_db)) -> Response:
    """Teams outgoing webhook (SPEC 10.1-10.4): quick answer or queue a question job."""
    secret = get_settings().TEAMS_HMAC_SECRET
    if not secret:
        return Response(status_code=503)

    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        return Response(status_code=413)
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        return Response(status_code=413)

    if not verify_hmac(body, request.headers.get("Authorization"), secret):
        return Response(status_code=401)

    try:
        payload = json.loads(body.decode("utf-8"))
        raw_text = payload.get("text", "") if isinstance(payload, dict) else ""
    except (UnicodeDecodeError, json.JSONDecodeError):
        return Response(status_code=400)
    cleaned = clean_text(raw_text if isinstance(raw_text, str) else "")
    today = today_local()

    deadlines = [
        {
            "title": d.title,
            "due_date": d.due_date,
            "due_time": d.due_time.strftime("%H:%M") if d.due_time else None,
            "relatief": relatief(d.due_date, today=today),
        }
        for d in upcoming(session, today=today)
    ]
    sprint_end = None
    end_raw = load(session).sprint_end_date
    if end_raw:
        try:
            sprint_end = date.fromisoformat(str(end_raw))
        except ValueError:
            sprint_end = None

    reply = quick_answer(cleaned, today, deadlines, sprint_end)
    if reply is None:
        if _count_queued_questions(session) >= 5:
            reply = _REPLY_FULL
        else:
            reply = _REPLY_UP if _get_model_up(session) else _REPLY_DOWN
            # The sender's name is not stored (SPEC 10.4).
            session.add(
                Job(kind="question", status="queued", title=cleaned[:500], meeting_date=today)
            )
            session.commit()
    return JSONResponse(content={"type": "message", "text": reply})
