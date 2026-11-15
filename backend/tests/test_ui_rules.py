"""T60: the design-system rules hold everywhere (docs/frontend.md §Design system).

Written by a human.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import Job
from tests._ui_helpers import APP, COLOUR_LITERAL, TEMPLATES, css_without_comments, split_root

PENDING_UNTIL = "T60"  # see backend/conftest.py

TEMPLATE_FILES = sorted(p.name for p in TEMPLATES.glob("*.html"))


@pytest.mark.parametrize("name", TEMPLATE_FILES)
def test_no_inline_styles(name: str) -> None:
    assert "style=" not in (TEMPLATES / name).read_text()


@pytest.mark.parametrize("name", [n for n in TEMPLATE_FILES if n != "_ui.html"])
def test_form_controls_only_in_components(name: str) -> None:
    src = (TEMPLATES / name).read_text()
    inputs = [m for m in re.findall(r"<input\b[^>]*>", src) if 'type="hidden"' not in m]
    assert inputs == [], f"{name}: use ui.field"
    assert "<textarea" not in src and "<select" not in src, f"{name}: use ui.field"


@pytest.mark.parametrize(
    "name", [n for n in TEMPLATE_FILES if not n.startswith("_") and n != "base.html"]
)
def test_pages_extend_base_and_import_ui(name: str) -> None:
    src = (TEMPLATES / name).read_text()
    assert '{% extends "base.html" %}' in src
    assert '{% import "_ui.html" as ui with context %}' in src


def test_css_has_no_colour_literals_outside_root() -> None:
    _, rest = split_root(css_without_comments())
    assert [m.group(0) for m in COLOUR_LITERAL.finditer(rest)] == []


def test_one_jinja_environment() -> None:
    assert [
        p.name
        for p in APP.glob("*.py")
        if p.name != "templating.py" and "Environment(" in p.read_text()
    ] == []


def test_every_page_has_the_layout(db: Any, auth_client: TestClient) -> None:
    job = Job(kind="summary", status="queued", title="X", meeting_date=date(2026, 11, 16))
    db.add(job)
    db.commit()
    for path in (
        "/",
        "/deadlines",
        "/meetings",
        f"/meetings/{job.id}",
        "/settings",
        "/privacy",
        "/stijl",
    ):
        html = auth_client.get(path).text
        assert 'class="skip-link"' in html, path
        assert '<main id="inhoud" class="container">' in html, path
        assert html.count("<h1") == 1, f"{path}: exactly one h1"
