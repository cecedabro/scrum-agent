"""SPEC 10.1–10.2: verify_hmac and clean_text."""

import base64
import hashlib
import hmac as std_hmac
from unittest.mock import patch

from app.config import ConfigError, check_production, get_settings

# ── verify_hmac ────────────────────────────────────────────────────────

PLAIN = b"@Agent Wat zijn de deadlines?"


def _sign(body: bytes, secret: bytes) -> str:
    """Return ``HMAC <base64>`` for *body* keyed with *secret*."""
    digest = std_hmac.new(secret, body, hashlib.sha256).digest()
    return "HMAC " + base64.b64encode(digest).decode()


def test_valid_signature_passes() -> None:
    """A correctly computed signature is accepted."""
    secret = b"test-secret-32-bytes-long........."
    secret_b64 = base64.b64encode(secret).decode()
    header = _sign(PLAIN, secret)
    from app.teams_in import verify_hmac

    assert verify_hmac(PLAIN, header, secret_b64) is True


def test_wrong_signature_fails() -> None:
    """A signature computed with a different secret is rejected."""
    secret = b"test-secret-32-bytes-long........."
    wrong_secret = b"wrong-secret-wrong-secret-wron....."
    secret_b64 = base64.b64encode(secret).decode()
    header = _sign(PLAIN, wrong_secret)
    from app.teams_in import verify_hmac

    assert verify_hmac(PLAIN, header, secret_b64) is False


def test_empty_header_fails() -> None:
    """An empty string header is rejected."""
    secret = b"test-secret-32-bytes-long........."
    secret_b64 = base64.b64encode(secret).decode()
    from app.teams_in import verify_hmac

    assert verify_hmac(PLAIN, "", secret_b64) is False


def test_none_header_fails() -> None:
    """A missing (None) header is rejected."""
    secret = b"test-secret-32-bytes-long........."
    secret_b64 = base64.b64encode(secret).decode()
    from app.teams_in import verify_hmac

    assert verify_hmac(PLAIN, None, secret_b64) is False


def test_missing_hmac_prefix_fails() -> None:
    """A bare base64 value without the ``HMAC `` prefix is rejected."""
    secret = b"test-secret-32-bytes-long........."
    secret_b64 = base64.b64encode(secret).decode()
    digest = std_hmac.new(secret, PLAIN, hashlib.sha256).digest()
    bare = base64.b64encode(digest).decode()
    from app.teams_in import verify_hmac

    assert verify_hmac(PLAIN, bare, secret_b64) is False


def test_bad_base64_secret_fails() -> None:
    """Non-base64 characters in the secret cause rejection."""
    from app.teams_in import verify_hmac

    assert verify_hmac(PLAIN, "HMAC dGVzdA==", "not-base64!!!") is False


def test_no_secret_returns_false() -> None:
    """An empty secret string cannot verify anything."""
    from app.teams_in import verify_hmac

    assert verify_hmac(PLAIN, "HMAC dGVzdA==", "") is False


# ── clean_text ─────────────────────────────────────────────────────────


def test_clean_mentions_and_tags() -> None:
    """<at>…</at> mentions and other HTML tags are removed."""
    from app.teams_in import clean_text

    result = clean_text("<at>Agent</at> Wat zijn de deadlines?")
    assert result == "Wat zijn de deadlines?"


def test_clean_html_entities() -> None:
    """HTML entities such as &nbsp; are decoded."""
    from app.teams_in import clean_text

    result = clean_text("Hello&nbsp;World")
    assert result == "Hello World"


def test_clean_whitespace_collapse() -> None:
    """Multiple whitespace characters collapse to a single space."""
    from app.teams_in import clean_text

    result = clean_text("Wat zijn de    deadlines?")
    assert result == "Wat zijn de deadlines?"


def test_clean_full_input() -> None:
    """Mentions, entities, and extra whitespace are all cleaned."""
    from app.teams_in import clean_text

    result = clean_text("<at>Agent</at> Wat zijn de   deadlines?&nbsp;")
    assert result == "Wat zijn de deadlines?"


def test_clean_only_tags() -> None:
    """Text that is only tags yields an empty string."""
    from app.teams_in import clean_text

    result = clean_text("<at>Agent</at><b></b>")
    assert result == ""


def test_clean_consecutive_entities() -> None:
    """Multiple consecutive entities are decoded and collapsed."""
    from app.teams_in import clean_text

    result = clean_text("A&nbsp;&nbsp;&nbsp;B")
    assert result == "A B"


# ── production check ───────────────────────────────────────────────────


def test_production_refuses_non_base64_secret() -> None:
    """In production a non-base64 TEAMS_HMAC_SECRET raises ConfigError."""
    with (
        patch.object(get_settings(), "APP_ENV", "production"),
        patch.object(get_settings(), "TEAMS_HMAC_SECRET", "not-base64!!!"),
        patch.object(get_settings(), "TEAM_PASSWORD", "x" * 20),
        patch.object(get_settings(), "TEAMS_WEBHOOK_URL", ""),
    ):
        try:
            check_production(get_settings())
        except ConfigError as exc:
            assert "TEAMS_HMAC_SECRET" in str(exc)
        else:
            raise AssertionError("ConfigError expected")
