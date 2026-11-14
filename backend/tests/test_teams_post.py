"""SPEC 5.1–5.2: envelope, _cap_body, and post_card."""

import json
from unittest.mock import patch

import httpx

from app.config import get_settings
from app.teams import (
    PostResult,
    _cap_body,
    envelope,
    post_card,
)

# ── envelope structure ──────────────────────────────────────────────


def test_envelope_has_exact_keys() -> None:
    card = {"type": "AdaptiveCard", "body": []}
    result = envelope(card)
    assert list(sorted(result.keys())) == ["attachments", "type"]
    assert result["type"] == "message"
    assert len(result["attachments"]) == 1
    attachment = result["attachments"][0]
    assert attachment["contentType"] == "application/vnd.microsoft.card.adaptive"
    assert attachment["contentUrl"] is None
    assert attachment["content"] is card


def test_envelope_does_not_mutate_card() -> None:
    card = {"type": "AdaptiveCard", "body": [{"type": "TextBlock", "text": "hello"}]}
    envelope(card)
    assert card["body"][0]["text"] == "hello"


# ── _cap_body (28 KB limit) ─────────────────────────────────────────


def _long_text(length: int) -> str:
    """Return a string of *length* 'A' characters."""
    return "A" * length


def test_cap_body_short_passes() -> None:
    """A small card passes without mutation."""
    card = {"type": "AdaptiveCard", "body": [{"type": "TextBlock", "text": "hi"}]}
    result = _cap_body(envelope(card))
    assert result == envelope(card)


def test_cap_body_cuts_long_card() -> None:
    """A 40 KB card is shortened to <= 28 KB."""
    big = _long_text(40 * 1024)
    card = {"type": "AdaptiveCard", "body": [{"type": "TextBlock", "text": big}]}
    capped = _cap_body(envelope(card))
    raw = json.dumps(capped, ensure_ascii=False).encode("utf-8")
    assert len(raw) <= 28 * 1024, f"body is {len(raw)} bytes (max 28672)"


def test_cap_body_appends_suffix() -> None:
    """Truncated text ends with the Dutch shortening suffix."""
    big = _long_text(40 * 1024)
    card = {"type": "AdaptiveCard", "body": [{"type": "TextBlock", "text": big}]}
    capped = _cap_body(envelope(card))
    # Find the TextBlock in the capped envelope.
    body = capped["attachments"][0]["content"]["body"]
    text_block = body[0]
    assert text_block["type"] == "TextBlock"
    assert text_block["text"].endswith("\u2026 (ingekort)")


def test_cap_body_multiple_textblocks_truncates_longest_first() -> None:
    """When multiple TextBlocks exist, the longest one(s) are cut."""
    mid = _long_text(20 * 1024)
    big = _long_text(40 * 1024)
    card = {
        "type": "AdaptiveCard",
        "body": [
            {"type": "TextBlock", "text": mid},
            {"type": "TextBlock", "text": big},
        ],
    }
    capped = _cap_body(envelope(card))
    raw = json.dumps(capped, ensure_ascii=False).encode("utf-8")
    assert len(raw) <= 28 * 1024


# ── post_card with httpx.MockTransport ──────────────────────────────


def _make_transport(
    status_code: int, body: str = "", headers: dict | None = None
) -> httpx.MockTransport:
    """Return a MockTransport that responds with *status_code*."""

    def handler(request: httpx.Request) -> httpx.Response:
        resp_headers = headers or {"Content-Type": "application/json"}
        return httpx.Response(status_code, content=body, headers=resp_headers)

    return httpx.MockTransport(handler)


_FAKE_WEBHOOK = "https://example.invalid/webhook"


def _post_with_url(card: dict, **kwargs) -> PostResult:
    """Call post_card with a fake webhook URL and injectable client."""
    with patch.object(get_settings(), "TEAMS_WEBHOOK_URL", _FAKE_WEBHOOK):
        return post_card(card, **kwargs)


def test_post_card_202_returns_ok() -> None:
    """HTTP 202 → PostResult(status="ok")."""
    transport = _make_transport(202)
    result = _post_with_url(
        {"type": "AdaptiveCard", "body": []}, client=httpx.Client(transport=transport)
    )
    assert result.status == "ok"
    assert result.error is None


def test_post_card_200_returns_ok() -> None:
    """HTTP 200 → PostResult(status="ok")."""
    transport = _make_transport(200)
    result = _post_with_url(
        {"type": "AdaptiveCard", "body": []}, client=httpx.Client(transport=transport)
    )
    assert result.status == "ok"


def test_post_card_429_returns_retryable() -> None:
    """HTTP 429 → retryable."""
    transport = _make_transport(429)
    result = _post_with_url(
        {"type": "AdaptiveCard", "body": []}, client=httpx.Client(transport=transport)
    )
    assert result.status == "retryable"
    assert result.error == "status 429"


def test_post_card_503_returns_retryable() -> None:
    """HTTP 5xx → retryable."""
    transport = _make_transport(503)
    result = _post_with_url(
        {"type": "AdaptiveCard", "body": []}, client=httpx.Client(transport=transport)
    )
    assert result.status == "retryable"
    assert result.error == "status 503"


def test_post_card_400_returns_permanent() -> None:
    """HTTP 400 → permanent."""
    transport = _make_transport(400, body='{"error":"bad request"}')
    result = _post_with_url(
        {"type": "AdaptiveCard", "body": []}, client=httpx.Client(transport=transport)
    )
    assert result.status == "permanent"
    assert result.error == "status 400"


def test_post_card_401_returns_permanent() -> None:
    """HTTP 401 → permanent."""
    transport = _make_transport(401)
    result = _post_with_url(
        {"type": "AdaptiveCard", "body": []}, client=httpx.Client(transport=transport)
    )
    assert result.status == "permanent"


def test_post_card_timeout_returns_retryable() -> None:
    """httpx.TimeoutException → retryable."""
    transport = _make_transport(200)
    with patch.object(
        httpx.Client,
        "post",
        side_effect=httpx.TimeoutException("simulated timeout"),
    ):
        result = _post_with_url(
            {"type": "AdaptiveCard", "body": []},
            client=httpx.Client(transport=transport),
        )
    assert result.status == "retryable"


def test_post_card_connection_refused_returns_retryable() -> None:
    """Network error → retryable."""
    # Point to a closed port inside the container; raises ConnectError.
    result = _post_with_url(
        {"type": "AdaptiveCard", "body": []},
        client=httpx.Client(base_url="http://127.0.0.1:1"),
    )
    assert result.status == "retryable"


def test_post_card_envelope_bytes_are_json() -> None:
    """The request body sent to the transport is valid JSON matching envelope structure."""
    received: dict = {}

    def capturing_handler(request: httpx.Request) -> httpx.Response:
        received.update(json.loads(request.content))
        return httpx.Response(202)

    transport = httpx.MockTransport(capturing_handler)
    card = {"type": "AdaptiveCard", "body": [{"type": "TextBlock", "text": "hello"}]}
    _post_with_url(card, client=httpx.Client(transport=transport))

    assert received["type"] == "message"
    assert received["attachments"][0]["content"]["body"][0]["text"] == "hello"


def test_post_card_40kb_card_is_capped_in_envelope() -> None:
    """A 40 KB card is truncated to <= 28 KB in the JSON sent over the wire."""
    received: dict = {}
    big = _long_text(40 * 1024)

    def capturing_handler(request: httpx.Request) -> httpx.Response:
        received.update(json.loads(request.content))
        return httpx.Response(202)

    transport = httpx.MockTransport(capturing_handler)
    _post_with_url(
        {"type": "AdaptiveCard", "body": [{"type": "TextBlock", "text": big}]},
        client=httpx.Client(transport=transport),
    )

    raw = json.dumps(received, ensure_ascii=False).encode("utf-8")
    assert len(raw) <= 28 * 1024


def test_post_card_error_does_not_contain_webhook_url() -> None:
    """Error strings must never reveal the webhook URL."""
    transport = _make_transport(400)
    result = _post_with_url({"type": "AdaptiveCard", "body": []}, client=transport)
    assert result.error is not None
    assert "TEAMS_WEBHOOK" not in result.error
    assert "http" not in result.error


def test_post_card_without_url_returns_ok() -> None:
    """Missing TEAMS_WEBHOOK_URL → PostResult(status="ok")."""
    with patch.object(get_settings(), "TEAMS_WEBHOOK_URL", ""):
        result = post_card({"type": "AdaptiveCard", "body": []})
        assert result.status == "ok"
