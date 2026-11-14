"""Teams incoming webhook utilities (SPEC 10.1–10.2).

``verify_hmac`` checks the HMAC-SHA256 signature that Microsoft Teams sends
with every outgoing-webhook POST.  ``clean_text`` sanitises the HTML message
body before matching or further processing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from html import unescape

__all__ = ["verify_hmac", "clean_text"]


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
