"""T54: the page layout in base.html (docs/frontend.md §Layout). Written by a human."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import Job
from tests._ui_helpers import template_source

PENDING_UNTIL = "T54"  # see backend/conftest.py

NAV = [
    ("/", "Overzicht"),
    ("/deadlines", "Deadlines"),
    ("/meetings", "Vergaderingen"),
    ("/settings", "Instellingen"),
    ("/privacy", "Privacy"),
]


def nav_html(html: str) -> str:
    m = re.search(r'<nav aria-label="Hoofdnavigatie">(.*?)</nav>', html, flags=re.DOTALL)
    assert m, "nav missing"
    return m.group(1)


def current_links(html: str) -> list[str]:
    return re.findall(r'<a [^>]*href="([^"]+)"[^>]*aria-current="page"', nav_html(html))


def test_skip_link_is_first_in_body(auth_client: TestClient) -> None:
    html = auth_client.get("/").text
    body = html[html.index("<body") :]
    first = re.search(r"<body[^>]*>\s*(<[^>]+>)", body)
    assert first and 'class="skip-link"' in first.group(1) and 'href="#inhoud"' in first.group(1)
    assert "Naar de inhoud" in html


def test_header_brand_and_nav(auth_client: TestClient) -> None:
    html = auth_client.get("/").text
    header = re.search(r'<header class="site-header">(.*?)</header>', html, flags=re.DOTALL)
    assert header, "header.site-header missing"
    assert '<a class="brand" href="/">Scrum agent</a>' in " ".join(header.group(1).split())
    assert 'aria-label="Hoofdnavigatie"' in header.group(1)
    links = re.findall(r'href="([^"]+)"[^>]*>\s*([^<]+?)\s*</a>', nav_html(html))
    assert links == NAV


def test_main_and_footer(auth_client: TestClient) -> None:
    html = auth_client.get("/").text
    assert '<main id="inhoud" class="container">' in html
    footer = re.search(r'<footer class="site-footer">(.*?)</footer>', html, flags=re.DOTALL)
    assert footer
    assert 'href="/privacy"' in footer.group(1) and 'href="/stijl"' in footer.group(1)


@pytest.mark.parametrize(("path", "current"), [(p, p) for p, _ in NAV])
def test_current_page_marked(auth_client: TestClient, path: str, current: str) -> None:
    assert current_links(auth_client.get(path).text) == [current]


def test_subpage_marks_its_section(db: Any, auth_client: TestClient) -> None:
    job = Job(kind="summary", status="queued", title="Planning", meeting_date=date(2026, 11, 16))
    db.add(job)
    db.commit()
    assert current_links(auth_client.get(f"/meetings/{job.id}").text) == ["/meetings"]


def test_nav_items_defined_once() -> None:
    src = template_source("base.html")
    assert "nav_items" in src
    assert src.count("aria-current") == 1, "one loop renders every nav link"
