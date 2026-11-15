"""T59: the /stijl style guide page (docs/frontend.md §Style guide page). Written by a human."""

from __future__ import annotations

from fastapi.testclient import TestClient

PENDING_UNTIL = "T59"  # see backend/conftest.py

MUST_SHOW = [
    'class="badge badge-queued"',
    'class="badge badge-running"',
    'class="badge badge-done"',
    'class="badge badge-failed"',
    'class="btn btn-primary"',
    'class="btn btn-secondary"',
    'class="btn btn-danger"',
    'class="inline-form"',
    '<div class="field">',
    'class="field field-invalid"',
    'class="field field-check"',
    "<select",
    "<textarea",
    'class="hint"',
    'class="model-state model-state-up"',
    'class="model-state model-state-down"',
    'class="alert alert-info"',
    'class="alert alert-success"',
    'class="alert alert-danger"',
    'class="empty-state"',
    '<section class="card">',
    'class="card-title"',
    '<ul class="list">',
    '<li class="list-item">',
    "<time datetime=",
    'class="relative"',
]


def test_style_guide_shows_every_component(auth_client: TestClient) -> None:
    r = auth_client.get("/stijl")
    assert r.status_code == 200
    missing = [s for s in MUST_SHOW if s not in r.text]
    assert missing == []


def test_style_guide_needs_login(client: TestClient) -> None:
    assert client.get("/stijl").status_code == 401


def test_not_in_nav_but_in_footer(auth_client: TestClient) -> None:
    html = auth_client.get("/").text
    nav = html[html.index("<nav") : html.index("</nav>")]
    assert "/stijl" not in nav
    footer = html[html.index('<footer class="site-footer">') :]
    assert 'href="/stijl"' in footer
