"""Teams posting: envelope building, size cap, and the HTTP call.

SPEC 5.1–5.2: POST the envelope to TEAMS_WEBHOOK_URL with a 15 s timeout.
Any 2xx is success.  429 / 5xx / network errors are retryable.
All other 4xx are permanent (not retried).
The JSON body is capped at 28 KB; longer text is cut and ends with "… (ingekort)".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import get_settings

_KB = 1024
_MAX_BODY_KB = 28
_MAX_BODY_BYTES = _MAX_BODY_KB * _KB
_TIMEOUT_S = 15


@dataclass(frozen=True)
class PostResult:
    status: str  # "ok", "retryable", or "permanent"
    error: str | None = None


def envelope(card: dict[str, Any]) -> dict[str, Any]:
    """Wrap a card in the Microsoft Teams message format."""
    return {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": card,
            }
        ],
    }


def _cap_body(body: dict[str, Any]) -> dict[str, Any]:
    """Enforce the 28 KB JSON size cap by shortening TextBlocks.

    When the full JSON exceeds the limit the longest TextBlocks are
    progressively shortened until the body fits.  The final element in
    every TextBlock is replaced with the truncation suffix so the
    reader sees the message was shortened.
    """
    suffix = "\u2026 (ingekort)"
    max_bytes = _MAX_BODY_BYTES - len(suffix.encode())

    def _json_size(d: dict[str, Any]) -> int:
        return len(json.dumps(d, ensure_ascii=False).encode("utf-8"))

    current_size = _json_size(body)
    if current_size <= max_bytes:
        return body

    # Navigate into the card stored in the envelope.
    card = body.get("attachments", [{}])[0].get("content", {})
    card_body = card.get("body", [])

    # Collect all TextBlock texts and sort by length (descending).
    texts: list[str] = []
    for element in card_body:
        if element.get("type") == "TextBlock":
            texts.append(element["text"])

    # Truncate the longest texts first.
    texts.sort(key=len, reverse=True)
    for i, original in enumerate(texts):
        if _json_size(body) <= max_bytes:
            break
        # Keep cutting the text down to the suffix.
        while len(original.encode("utf-8")) > len(suffix.encode("utf-8")):
            original = original[:-1]
        texts[i] = original + suffix

    # Walk the card body again and replace texts.
    text_idx = 0
    for element in card_body:
        if element.get("type") == "TextBlock":
            element["text"] = texts[text_idx]
            text_idx += 1

    return body


def _envelope_bytes(envelope_body: dict[str, Any]) -> bytes:
    """Serialise the envelope dict to UTF-8 JSON bytes."""
    return json.dumps(envelope_body, ensure_ascii=False).encode("utf-8")


def post_card(
    card: dict[str, Any],
    *,
    client: httpx.Client | None = None,
) -> PostResult:
    """POST a card to the Teams webhook.

    *client* is injectable for tests (``httpx.MockTransport``).
    Returns a ``PostResult`` with status ``ok``, ``retryable``, or
    ``permanent``.
    """
    settings = get_settings()
    webhook_url = settings.TEAMS_WEBHOOK_URL

    if not webhook_url:
        return PostResult(status="ok")

    wrapped = _cap_body(envelope(card))

    local_client = client or httpx.Client()
    try:
        resp = local_client.post(
            webhook_url,
            content=_envelope_bytes(wrapped),
            headers={"Content-Type": "application/json"},
            timeout=_TIMEOUT_S,
        )

        if 200 <= resp.status_code < 300:
            return PostResult(status="ok")

        if resp.status_code == 429 or resp.status_code >= 500:
            return PostResult(status="retryable", error=f"status {resp.status_code}")

        # Other 4xx: permanent failure.
        return PostResult(status="permanent", error=f"status {resp.status_code}")

    except httpx.TimeoutException:
        return PostResult(status="retryable", error="timeout")
    except httpx.ConnectError:
        return PostResult(status="retryable", error="connection refused")
    except httpx.NetworkError:
        return PostResult(status="retryable", error="network error")
    except Exception as exc:
        return PostResult(status="permanent", error=str(type(exc).__name__))
    finally:
        if client is None:
            local_client.close()
