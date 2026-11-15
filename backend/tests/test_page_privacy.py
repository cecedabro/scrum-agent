"""SPEC 8.4: Privacy page — renders with Dutch content from docs/privacy.md.

Tests use the ``auth_client`` fixture (Basic auth) and verify:
- GET /privacy returns 200 behind auth
- each row of the data table is present
- nav link has aria-current="page"
- unauthenticated access returns 401
"""

from __future__ import annotations

from fastapi.testclient import TestClient

# ------------------------------------------------------------------
# GET /privacy — page renders behind auth
# ------------------------------------------------------------------


def test_get_privacy_page_200(auth_client: TestClient) -> None:
    """/privacy returns 200 with valid auth."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200


def test_get_privacy_requires_auth(client: TestClient) -> None:
    """/privacy returns 401 without auth."""
    r = client.get("/privacy")
    assert r.status_code == 401


def test_get_privacy_has_title(auth_client: TestClient) -> None:
    """/privacy page includes the title."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert b"Privacy" in r.content


def test_get_privacy_has_main_and_footer(auth_client: TestClient) -> None:
    """/privacy extends base.html with main and footer."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert b"<main" in r.content
    assert b"<footer" in r.content


# ------------------------------------------------------------------
# Nav aria-current on /privacy
# ------------------------------------------------------------------


def test_nav_aria_current_on_privacy(auth_client: TestClient) -> None:
    """/privacy nav link has aria-current=\"page\"."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert 'aria-current="page"' in r.text
    assert r.text.count('aria-current="page"') == 1


def test_nav_privacy_link_present(auth_client: TestClient) -> None:
    """/privacy page includes the Privacy nav link with href."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert 'href="/privacy"' in r.text


# ------------------------------------------------------------------
# Data table — every row present
# ------------------------------------------------------------------

# Each test checks one row of the privacy table from docs/privacy.md.


def test_table_row_deadlines(auth_client: TestClient) -> None:
    """Table row: deadlines (title, date, time, note)."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert b"Deadlines" in r.content
    assert b"Postgres op de homelab" in r.content
    assert b"60 dagen" in r.content


def test_table_row_reminder_settings(auth_client: TestClient) -> None:
    """Table row: reminder settings."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert b"Herinneringsinstellingen" in r.content
    assert b"tot wijziging" in r.content


def test_table_row_transcript_file(auth_client: TestClient) -> None:
    """Table row: uploaded transcript file (nowhere)."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert "Geüpload transcriptbestand".encode() in r.content
    assert b"nergens" in r.content


def test_table_row_transcript_text(auth_client: TestClient) -> None:
    """Table row: transcript text."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert b"Transcripttekst" in r.content
    assert b"job.transcript" in r.content
    assert b"7 dagen" in r.content


def test_table_row_summary(auth_client: TestClient) -> None:
    """Table row: meeting summary."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert b"Vergadersamenvatting" in r.content
    assert b"job.result" in r.content
    assert b"180 dagen" in r.content
    assert b"SUMMARY_RETENTION_DAYS" in r.content


def test_table_row_questions(auth_client: TestClient) -> None:
    """Table row: questions to @Agent."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert b"Vragen aan" in r.content
    assert b"@Agent" in r.content
    assert b"30 dagen" in r.content


def test_table_row_post_log(auth_client: TestClient) -> None:
    """Table row: post log."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert b"Postlogboek" in r.content
    assert b"180 dagen" in r.content
    assert b"POST_LOG_RETENTION_DAYS" in r.content


def test_table_row_teams_posts(auth_client: TestClient) -> None:
    """Table row: posts in Teams."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert b"Posts in Teams" in r.content
    assert b"Microsoft Teams" in r.content


# ------------------------------------------------------------------
# Content sections — what, where, how long, how to delete
# ------------------------------------------------------------------


def test_privacy_what_section(auth_client: TestClient) -> None:
    """/privacy explains what is stored."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert b"opgeslagen" in r.content


def test_privacy_where_section(auth_client: TestClient) -> None:
    """/privacy explains where data is stored."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert b"Postgres" in r.content
    assert b"homelab" in r.content


def test_privacy_how_to_delete(auth_client: TestClient) -> None:
    """/privacy explains how to delete data."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert b"verwijderd" in r.content.lower() or b"Verwijderen" in r.content
    assert b"kubectl" in r.content


def test_privacy_who_section(auth_client: TestClient) -> None:
    """/privacy explains who can see the data."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert b"wie" in r.content.lower() or b"iemand" in r.content.lower()
    assert b"teamwachtwoord" in r.content.lower() or b"team password" in r.content.lower()


def test_privacy_dutch_language(auth_client: TestClient) -> None:
    """/privacy page uses Dutch language."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert 'lang="nl"' in r.text


# ------------------------------------------------------------------
# Security headers
# ------------------------------------------------------------------


def test_privacy_security_headers(auth_client: TestClient) -> None:
    """/privacy includes security headers (SPEC 2.4)."""
    r = auth_client.get("/privacy")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("Referrer-Policy") == "same-origin"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "default-src 'self'" in r.headers.get("Content-Security-Policy", "")
