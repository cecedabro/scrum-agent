"""T51: one shared Jinja environment (docs/frontend.md §Design system). Written by a human."""

from __future__ import annotations

from datetime import date

from tests._ui_helpers import APP

PENDING_UNTIL = "T51"  # see backend/conftest.py


def test_shared_environment() -> None:
    from app.templating import env, templates

    assert templates.env is env
    for name in ("datum", "datum_kort", "relatief", "STATUS_LABELS"):
        assert name in env.globals, name
    assert "datum_kort" in env.filters
    assert env.globals["STATUS_LABELS"]["done"] == "klaar"
    assert env.filters["datum_kort"](date(2026, 11, 16)) == "ma 16 nov"


def test_routers_use_it() -> None:
    from app.templating import templates

    import app.meetings
    import app.web

    assert app.web.templates is templates
    used = [v for v in vars(app.meetings).values() if type(v).__name__ == "Jinja2Templates"]
    assert used and all(t is templates for t in used)


def test_no_other_environment_is_built() -> None:
    offenders = [
        p.name
        for p in APP.glob("*.py")
        if p.name != "templating.py" and "Environment(" in p.read_text()
    ]
    assert offenders == []
