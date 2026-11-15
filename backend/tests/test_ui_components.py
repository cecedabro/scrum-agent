"""T53: the component macros in templates/_ui.html (docs/frontend.md §Components).

Written by a human. Renders each macro through the shared environment (`app.templating.env`)
and checks the agreed HTML contract.
"""

from __future__ import annotations

from datetime import date, time

import pytest

from tests._ui_helpers import render

PENDING_UNTIL = "T53"  # see backend/conftest.py


def squash(html: str) -> str:
    return " ".join(html.split())


@pytest.mark.parametrize(
    ("status", "label"),
    [("queued", "in de wachtrij"), ("running", "bezig"), ("done", "klaar"), ("failed", "mislukt")],
)
def test_badge(status: str, label: str) -> None:
    html = squash(render("{{ ui.badge(s) }}", s=status))
    assert f'<span class="badge badge-{status}">{label}</span>' in html


def test_badge_unknown_status() -> None:
    html = squash(render('{{ ui.badge("raar") }}'))
    assert '<span class="badge badge-neutral">raar</span>' in html


def test_text_field() -> None:
    html = squash(
        render('{{ ui.field("title", "Titel", value="Mijn <b>titel</b>", required=True) }}')
    )
    assert '<div class="field">' in html
    assert '<label for="title">Titel</label>' in html
    assert 'id="title"' in html and 'name="title"' in html and 'type="text"' in html
    assert 'value="Mijn &lt;b&gt;titel&lt;/b&gt;"' in html
    assert "required" in html
    assert 'class="error"' not in html and "aria-invalid" not in html


def test_field_with_error_and_hint() -> None:
    html = squash(
        render(
            '{{ ui.field("due_date", "Datum", type="date", '
            'error="Ongeldige datum", hint="JJJJ-MM-DD") }}'
        )
    )
    assert '<div class="field field-invalid">' in html
    assert 'type="date"' in html
    assert 'aria-invalid="true"' in html
    assert 'aria-describedby="due_date-error"' in html
    assert '<p class="hint" id="due_date-hint">JJJJ-MM-DD</p>' in html
    assert '<p class="error" id="due_date-error">Ongeldige datum</p>' in html
    assert html.index('class="hint"') < html.index('class="error"')


def test_textarea_field() -> None:
    html = squash(
        render(
            '{{ ui.field("note", "Notitie", type="textarea", value="a & b", attrs={"rows": 3}) }}'
        )
    )
    assert '<textarea id="note" name="note"' in html
    assert 'rows="3"' in html
    assert ">a &amp; b</textarea>" in html


def test_select_field() -> None:
    html = squash(
        render(
            '{{ ui.field("dag", "Dag", type="select", value="dinsdag", '
            'options=[("maandag", "Maandag"), ("dinsdag", "Dinsdag")]) }}'
        )
    )
    assert '<select id="dag" name="dag"' in html
    assert '<option value="maandag">Maandag</option>' in html
    assert '<option value="dinsdag" selected>Dinsdag</option>' in html


@pytest.mark.parametrize(("value", "checked"), [(True, True), (False, False)])
def test_checkbox_field(value: bool, checked: bool) -> None:
    html = squash(render('{{ ui.field("aan", "Inschakelen", type="checkbox", value=v) }}', v=value))
    assert '<div class="field field-check">' in html
    assert 'type="checkbox"' in html and 'id="aan"' in html and 'name="aan"' in html
    assert ("checked" in html) is checked
    assert html.index('type="checkbox"') < html.index('<label for="aan">Inschakelen</label>')


def test_file_field_with_attrs() -> None:
    html = squash(
        render(
            '{{ ui.field("file", "Bestand", type="file", '
            'attrs={"accept": ".vtt,.docx"}, required=True) }}'
        )
    )
    assert 'type="file"' in html and 'name="file"' in html
    assert 'accept=".vtt,.docx"' in html


@pytest.mark.parametrize("kind", ["primary", "secondary", "danger"])
def test_button(kind: str) -> None:
    html = squash(render("{{ ui.button('Opslaan', kind=k) }}", k=kind))
    assert f'<button type="submit" class="btn btn-{kind}">Opslaan</button>' in html


def test_button_defaults_to_primary() -> None:
    assert 'class="btn btn-primary"' in render("{{ ui.button('Ok') }}")


def test_post_button() -> None:
    html = squash(
        render("{{ ui.post_button('/deadlines/3/delete', 'Verwijderen', kind='danger') }}")
    )
    assert '<form method="post" action="/deadlines/3/delete" class="inline-form">' in html
    assert '<button type="submit" class="btn btn-danger">Verwijderen</button>' in html
    assert html.rstrip().endswith("</form>")


def test_empty() -> None:
    assert '<p class="empty-state">Niets hier.</p>' in squash(
        render("{{ ui.empty('Niets hier.') }}")
    )


def test_card_with_and_without_title() -> None:
    html = squash(render("{% call ui.card('Deadlines') %}<p>inhoud</p>{% endcall %}"))
    assert '<section class="card">' in html
    assert '<h2 class="card-title">Deadlines</h2>' in html
    assert html.index("card-title") < html.index("<p>inhoud</p>") < html.index("</section>")
    plain = squash(render("{% call ui.card() %}<p>x</p>{% endcall %}"))
    assert '<section class="card">' in plain and "card-title" not in plain


def test_when_with_time_and_relative() -> None:
    html = squash(
        render(
            "{{ ui.when(d, t, today) }}",
            d=date(2026, 11, 18),
            t=time(14, 30),
            today=date(2026, 11, 16),
        )
    )
    assert '<time datetime="2026-11-18T14:30">woensdag 18 november om 14:30</time>' in html
    assert '<span class="relative">(over 2 dagen)</span>' in html


def test_when_date_only() -> None:
    html = squash(render("{{ ui.when(d) }}", d=date(2026, 11, 16)))
    assert '<time datetime="2026-11-16">maandag 16 november</time>' in html
    assert "relative" not in html


@pytest.mark.parametrize(("up", "cls"), [(True, "model-state-up"), (False, "model-state-down")])
def test_model_state(up: bool, cls: str) -> None:
    html = squash(render("{{ ui.model_state(up, 'model bereikbaar') }}", up=up))
    assert f'<p class="model-state {cls}">' in html
    assert '<span class="dot" aria-hidden="true"></span>model bereikbaar' in html


@pytest.mark.parametrize("kind", ["info", "success", "danger"])
def test_alert(kind: str) -> None:
    html = squash(render("{{ ui.alert('Opgeslagen', kind=k) }}", k=kind))
    assert f'<div class="alert alert-{kind}" role="status">Opgeslagen</div>' in html
