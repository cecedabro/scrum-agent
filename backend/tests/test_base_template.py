"""Tests for base template, nav, aria-current, lang, HTMX, and no-inline-script rules.

Covers the layout requirements from docs/frontend.md and SPEC 2.4 (no inline
scripts).  Tests live in ``backend/tests/`` so they run with ``cd backend &&
uv run pytest tests/test_base_template.py -q``.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app

BASE_DIR = Path(__file__).resolve().parent.parent / "app"
TEMPLATES_DIR = BASE_DIR / "templates"


@pytest.fixture()
def auth_client():
    """TestClient with valid Basic auth headers."""
    settings = get_settings()
    encoded = base64.b64encode(f"{settings.TEAM_USER}:{settings.TEAM_PASSWORD}".encode()).decode()
    headers = {"Authorization": f"Basic {encoded}"}
    with TestClient(create_app(), headers=headers) as c:
        yield c


@pytest.fixture()
def client():
    """TestClient without auth (for public routes)."""
    with TestClient(create_app()) as c:
        yield c


# ------------------------------------------------------------------
# Nav links (frontend.md page table)
# ------------------------------------------------------------------
def test_nav_links_present(auth_client: TestClient) -> None:
    """/ must include nav links for all expected pages."""
    r = auth_client.get("/")
    assert r.status_code == 200
    expected = ["/", "/deadlines", "/meetings", "/settings", "/privacy"]
    for path in expected:
        assert path in r.text


def test_nav_labels_dutch(auth_client: TestClient) -> None:
    """/ nav must use Dutch labels (Overzicht, Deadlines, Vergaderingen, Instellingen, Privacy)."""
    r = auth_client.get("/")
    assert r.status_code == 200
    for label in ["Overzicht", "Deadlines", "Vergaderingen", "Instellingen", "Privacy"]:
        assert label in r.text


# ------------------------------------------------------------------
# aria-current on /
# ------------------------------------------------------------------
def test_nav_aria_current_on_index(auth_client: TestClient) -> None:
    """/ nav link for Overzicht has aria-current=\"page\"."""
    r = auth_client.get("/")
    assert r.status_code == 200
    assert 'aria-current="page"' in r.text
    # Other nav links should NOT have aria-current
    assert r.text.count('aria-current="page"') == 1


# ------------------------------------------------------------------
# lang="nl"
# ------------------------------------------------------------------
def test_html_lang_is_dutch(auth_client: TestClient) -> None:
    """/ must have <html lang=\"nl\">."""
    r = auth_client.get("/")
    assert r.status_code == 200
    assert 'lang="nl"' in r.text


# ------------------------------------------------------------------
# HTMX loaded from vendor
# ------------------------------------------------------------------
def test_htmx_loaded_from_static_vendor(auth_client: TestClient) -> None:
    """/ must load htmx from /static/vendor/htmx.min.js (not inline)."""
    r = auth_client.get("/")
    assert r.status_code == 200
    assert "/static/vendor/htmx.min.js" in r.text


def test_htmx_js_file_exists_and_valid_syntax(auth_client: TestClient) -> None:
    """/static/vendor/htmx.min.js is valid JS (node --check passes)."""
    import subprocess

    js_path = BASE_DIR / "static" / "vendor" / "htmx.min.js"
    assert js_path.exists(), "htmx.min.js must exist in vendor/"
    result = subprocess.run(  # noqa: S603
        ["node", "--check", str(js_path)],  # noqa: S607
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"htmx.min.js syntax error: {result.stderr}"


# ------------------------------------------------------------------
# No inline <script> in any template
# ------------------------------------------------------------------
def test_no_inline_script_in_templates() -> None:
    """No template may contain <script> without a src attribute (CSP rule)."""
    for tpl_file in TEMPLATES_DIR.rglob("*.html"):
        content = tpl_file.read_text()
        # Find all <script> tags
        import re

        tags = re.findall(r"<script\b([^>]*)>", content, re.IGNORECASE)
        for attrs in tags:
            assert "src=" in attrs, f"Inline <script> in {tpl_file.name}: {attrs.strip()}"


# ------------------------------------------------------------------
# Semantic HTML structure
# ------------------------------------------------------------------
def test_has_main_and_footer(auth_client: TestClient) -> None:
    """/ must contain <main> and <footer> elements."""
    r = auth_client.get("/")
    assert r.status_code == 200
    assert "<main>" in r.text
    assert "<footer>" in r.text


def test_has_nav_element(auth_client: TestClient) -> None:
    """/ must contain a <nav> element."""
    r = auth_client.get("/")
    assert r.status_code == 200
    assert "<nav" in r.text.lower()


# ------------------------------------------------------------------
# Overview page content
# ------------------------------------------------------------------
def test_overview_title(auth_client: TestClient) -> None:
    """/ renders the 'Overzicht' page title."""
    r = auth_client.get("/")
    assert r.status_code == 200
    assert "Overzicht" in r.text


# ------------------------------------------------------------------
# Empty state
# ------------------------------------------------------------------
def test_empty_state_message(auth_client: TestClient) -> None:
    """/ shows an empty-state message when there are no deadlines or jobs."""
    r = auth_client.get("/")
    assert r.status_code == 200
    assert "Geen deadlines" in r.text or "geen" in r.text.lower()


# ------------------------------------------------------------------
# Security headers
# ------------------------------------------------------------------
def test_security_headers_present(auth_client: TestClient) -> None:
    """/ must include CSP and other security headers (SPEC 2.4)."""
    r = auth_client.get("/")
    assert r.status_code == 200
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("Referrer-Policy") == "same-origin"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "default-src 'self'" in r.headers.get("Content-Security-Policy", "")


def test_static_css_served() -> None:
    """/static/app.css is served (no auth needed)."""
    with TestClient(create_app()) as c:
        r = c.get("/static/app.css")
    assert r.status_code == 200


def test_static_htmx_served() -> None:
    """/static/vendor/htmx.min.js is served (no auth needed)."""
    with TestClient(create_app()) as c:
        r = c.get("/static/vendor/htmx.min.js")
    assert r.status_code == 200
