"""T58: app.css styles every component and layout class (docs/frontend.md §Look).

Written by a human.
"""

from __future__ import annotations

import re

import pytest

from tests._ui_helpers import css_without_comments, split_root

PENDING_UNTIL = "T58"  # see backend/conftest.py

CLASSES = [
    "skip-link",
    "site-header",
    "brand",
    "container",
    "site-footer",
    "card",
    "card-title",
    "list",
    "list-item",
    "relative",
    "empty-state",
    "field",
    "field-invalid",
    "field-check",
    "hint",
    "error",
    "btn",
    "btn-primary",
    "btn-secondary",
    "btn-danger",
    "inline-form",
    "badge",
    "badge-queued",
    "badge-running",
    "badge-done",
    "badge-failed",
    "badge-neutral",
    "model-state",
    "model-state-up",
    "model-state-down",
    "dot",
    "alert",
    "alert-info",
    "alert-success",
    "alert-danger",
]


def rest() -> str:
    return split_root(css_without_comments())[1]


@pytest.mark.parametrize("cls", CLASSES)
def test_class_is_styled(cls: str) -> None:
    assert re.search(rf"\.{re.escape(cls)}(?![\w-])[^{{]*\{{", rest()), f".{cls} has no rule"


def test_focus_is_visible() -> None:
    assert ":focus-visible" in rest()


def test_skip_link_appears_on_focus() -> None:
    assert re.search(r"\.skip-link:focus", rest())


def test_small_screens() -> None:
    assert re.search(r"@media\s*\((max|min)-width:\s*\d+px\)", rest())


@pytest.mark.parametrize(
    ("cls", "token"),
    [
        ("badge-done", "--color-success-soft"),
        ("badge-failed", "--color-danger-soft"),
        ("badge-running", "--color-info-soft"),
        ("badge-queued", "--color-neutral-soft"),
        ("btn-primary", "--color-accent"),
    ],
)
def test_variants_use_their_tokens(cls: str, token: str) -> None:
    m = re.search(rf"\.{cls}(?![\w-])[^{{]*\{{([^}}]*)\}}", rest())
    assert m and f"var({token})" in m.group(1), cls
