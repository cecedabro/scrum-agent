"""T52: design tokens in app.css (docs/frontend.md §Tokens). Written by a human."""

from __future__ import annotations

import re

from tests._ui_helpers import COLOUR_LITERAL, css_without_comments, split_root, tokens

PENDING_UNTIL = "T52"  # see backend/conftest.py

EXPECTED = {
    "--color-bg": "#f5f5f9",
    "--color-surface": "#ffffff",
    "--color-text": "#1c1a33",
    "--color-muted": "#5f5c78",
    "--color-border": "#deddea",
    "--color-accent": "#25167a",
    "--color-accent-hover": "#1a0e5e",
    "--color-accent-soft": "#ecebf8",
    "--color-success": "#1e6b3a",
    "--color-success-soft": "#e3f3e8",
    "--color-info": "#1d4f91",
    "--color-info-soft": "#e4eefb",
    "--color-danger": "#b3261e",
    "--color-danger-soft": "#fbe9e7",
    "--color-neutral-soft": "#ececf1",
    "--font-size-sm": "0.875rem",
    "--font-size-base": "1rem",
    "--font-size-lg": "1.25rem",
    "--font-size-xl": "1.6rem",
    "--space-1": "0.25rem",
    "--space-2": "0.5rem",
    "--space-3": "0.75rem",
    "--space-4": "1rem",
    "--space-6": "1.5rem",
    "--space-8": "2rem",
    "--radius": "10px",
    "--radius-sm": "6px",
    "--max-width": "960px",
}


def test_tokens_have_the_agreed_values() -> None:
    root, _ = split_root(css_without_comments())
    found = tokens(root)
    for name, value in EXPECTED.items():
        assert found.get(name, "").lower() == value, f"{name}: {found.get(name)!r}"
    assert "system-ui" in found.get("--font-sans", "")
    assert "rgba(" in found.get("--shadow", "")


def test_root_comes_first() -> None:
    css = css_without_comments().lstrip()
    assert css.startswith(":root"), "the token block is the first rule in app.css"


def test_no_colour_literals_outside_root() -> None:
    _, rest = split_root(css_without_comments())
    bad = [m.group(0).strip() for m in COLOUR_LITERAL.finditer(rest)]
    assert bad == [], bad


def test_rest_of_the_file_uses_tokens() -> None:
    _, rest = split_root(css_without_comments())
    for name in ("--color-bg", "--color-text", "--color-accent", "--font-sans", "--radius"):
        assert f"var({name})" in rest, name
    body = re.search(r"\bbody\s*\{([^}]*)\}", rest)
    assert body and "var(--color-bg)" in body.group(1)
