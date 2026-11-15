"""Shared helpers for the human-written UI tests (docs/frontend.md §Design system)."""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
TEMPLATES = APP / "templates"
CSS = APP / "static" / "app.css"

COLOUR_LITERAL = re.compile(r":[^;{}]*(#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\()")


def css_without_comments() -> str:
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(), flags=re.DOTALL)


def split_root(css: str) -> tuple[str, str]:
    """Return (body of the first `:root { … }` block, the rest of the file)."""
    m = re.search(r":root\s*\{(.*?)\}", css, flags=re.DOTALL)
    assert m, "app.css must start with a :root { … } block of tokens"
    return m.group(1), css[: m.start()] + css[m.end() :]


def tokens(root_body: str) -> dict[str, str]:
    return {
        k.strip(): " ".join(v.split())
        for k, v in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", root_body)
    }


def render(source: str, **ctx: object) -> str:
    """Render a template string with the shared environment and `ui` imported."""
    from app.templating import env

    head = '{% import "_ui.html" as ui with context %}'
    return env.from_string(head + source).render(**ctx)


def template_source(name: str) -> str:
    return (TEMPLATES / name).read_text()
