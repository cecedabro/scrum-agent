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
import re
from datetime import date
from html import unescape
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.answers import quick_answer
from app.clock import today_local
from app.config import get_settings
from app.db import get_db
from app.models import AppState, Job

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


@router.post("/teams/outgoing")
async def handle_teams_message(request: Request) -> JSONResponse:
    """Handle incoming Teams webhook message (SPEC 10.1–10.6)."""
    settings = get_settings()
    secret = settings.TEAMS_HMAC_SECRET

    body = await request.body()
    header = request.headers.get("Authorization")

    if not verify_hmac(body, header, secret):
        return JSONResponse(status_code=401, content={"text": "Ongeldige HMAC-signatuur"})

    try:
        data = body.decode("utf-8")
        import json

        payload = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JSONResponse(status_code=400, content={"text": "Ongeldige payload"})

    raw_text = payload.get("text", "")
    cleaned = clean_text(raw_text)
    today = today_local()

    with next(get_db()) as session:
        # Load deadlines and sprint_end for quick_answer
        from app.deadlines import upcoming
        from app.settings import load

        deadlines_list = upcoming(session, today=today)
        deadlines = [
            {
                "title": d.title,
                "due_date": d.due_date,
                "due_time": d.due_time.strftime("%H:%M") if d.due_time else None,
                "relatief": "vandaag",  # simplified; quick_answer uses it
            }
            for d in deadlines_list
        ]

        app_settings = load(session)
        sprint_end = None
        if app_settings.sprint_end_date:
            try:
                sprint_end = date.fromisoformat(app_settings.sprint_end_date)
            except ValueError:
                sprint_end = None

        # Try quick answer
        reply = quick_answer(cleaned.lower(), today, deadlines, sprint_end)

        if reply is not None:
            # Recognised pattern → return quick answer
            return JSONResponse(content={"type": "message", "text": reply})

        # Unknown question → queue it
        if _count_queued_questions(session) >= 5:
            return JSONResponse(content={"type": "message", "text": _REPLY_FULL})

        # Determine model status for reply
        model_up = _get_model_up(session)
        reply_text = _REPLY_UP if model_up else _REPLY_DOWN

        # Create question job (no sender name stored per SPEC 10.4)
        job = Job(
            kind="question",
            status="queued",
            title=cleaned[:500],
            meeting_date=today,
        )
        session.add(job)
        session.commit()

        return JSONResponse(content={"type": "message", "text": reply_text})
