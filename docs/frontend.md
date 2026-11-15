# Frontend (pages)

Server-rendered Jinja2 templates with HTMX for small updates. No SPA, no build step, no
CDN. You own the visual design within the rules below; keep it plain and readable.

## Rules
- Templates in `backend/app/templates/`, all extending `base.html`. Static files in
  `backend/app/static/`: one stylesheet `app.css`, optional small JS files, and the vendored
  `vendor/htmx.min.js` (htmx 2.0.11, already there; do not download anything).
- No inline `<script>`, `style=""` or `onclick=""` (the CSP forbids them). JS files are
  checked with `node --check` by `make check`.
- Forms work without JavaScript (normal POST + redirect, Post/Redirect/Get). HTMX only
  enhances: `hx-post`, `hx-target`, `hx-swap`. A route can return a partial when the
  request has the `HX-Request` header.
- Dutch copy, `<html lang="nl">`. Semantic HTML: `<nav>`, `<main>`, `<footer>`, a `<label>`
  for every control, readable on a 360 px phone without horizontal scrolling.
- Show times in Europe/Amsterdam with `fmt.py` filters (`datum`, `tijd`, `relatief`).

## Design system (one place to change the look)
The look lives in three places, and only there:
1. **Tokens** — CSS custom properties in the `:root` block at the top of `static/app.css`.
   Every colour, font size, space, radius and shadow in the rest of `app.css` is a
   `var(--…)`. Changing the accent colour = changing one line.
2. **Components** — Jinja macros in `templates/_ui.html`. Pages import them with
   `{% import "_ui.html" as ui with context %}` and never write raw form controls, badges or
   delete forms themselves. Changing how every form field looks = changing one macro.
3. **Layout** — `templates/base.html`: header with the brand and the nav (the nav items come
   from one list in that file), `<main id="inhoud">`, footer.

One shared Jinja environment, `app/templating.py`, is used by every router (`templates`, and
`env` with the globals `datum`, `datum_kort`, `relatief`, `STATUS_LABELS` and the filter
`datum_kort`). No router builds its own `Environment`.

### Tokens (exact names and values)
```css
:root {
  --color-bg: #f5f5f9;          /* page background */
  --color-surface: #ffffff;     /* cards, header */
  --color-text: #1c1a33;
  --color-muted: #5f5c78;
  --color-border: #deddea;
  --color-accent: #25167a;      /* HvA-ish dark blue */
  --color-accent-hover: #1a0e5e;
  --color-accent-soft: #ecebf8;
  --color-success: #1e6b3a;  --color-success-soft: #e3f3e8;
  --color-info: #1d4f91;     --color-info-soft: #e4eefb;
  --color-danger: #b3261e;   --color-danger-soft: #fbe9e7;
  --color-neutral-soft: #ececf1;
  --font-sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-size-sm: 0.875rem; --font-size-base: 1rem; --font-size-lg: 1.25rem; --font-size-xl: 1.6rem;
  --space-1: 0.25rem; --space-2: 0.5rem; --space-3: 0.75rem; --space-4: 1rem;
  --space-6: 1.5rem; --space-8: 2rem;
  --radius: 10px; --radius-sm: 6px;
  --shadow: 0 1px 2px rgba(28, 26, 51, 0.06), 0 1px 8px rgba(28, 26, 51, 0.04);
  --max-width: 960px;
}
```
Extra tokens may be added below these (they are: `--color-accent-ring`, `--font-mono`,
`--font-size-xs`, `--space-10`, `--radius-pill`, `--shadow-header`, `--control-height`,
`--gutter`); the values above stay fixed.
Outside `:root`, `app.css` contains no colour literals (`#…`, `rgb(`, `rgba(`, `hsl(`).

### Components (`templates/_ui.html`)
Exact output matters: tests and the existing page tests rely on it.

| Macro | Renders |
| --- | --- |
| `ui.badge(status)` | `<span class="badge badge-{status}">{label}</span>`; labels from `STATUS_LABELS` (queued "in de wachtrij", running "bezig", done "klaar", failed "mislukt"); unknown status → the status itself, class `badge-neutral` |
| `ui.field(name, label, type="text", value="", error=None, hint=None, required=False, options=None, attrs=None)` | `<div class="field">` (plus ` field-invalid` with an error) containing `<label for="{name}">`, the control with `id="{name}" name="{name}"`, then `<p class="hint" id="{name}-hint">` if `hint`, then `<p class="error" id="{name}-error">` if `error`. With an error the control gets `aria-invalid="true"` and `aria-describedby="{name}-error"`. `type`: any `<input>` type, `"textarea"` (value as content), `"select"` (`options` = list of `(value, label)`, the one equal to `value` gets `selected`) or `"checkbox"` (`value` truthy → `checked`; the label comes after the box, class `field field-check`). `attrs`: extra attributes (e.g. `{"accept": ".vtt,.docx", "rows": 3, "min": 1}`), rendered with `xmlattr`. `value` is always escaped. |
| `ui.button(text, kind="primary", type="submit")` | `<button type="{type}" class="btn btn-{kind}">`; kinds `primary`, `secondary`, `danger` |
| `ui.post_button(action, text, kind="secondary")` | `<form method="post" action="{action}" class="inline-form">` + `ui.button(text, kind)`; used for delete, post-to-Teams, test message |
| `ui.empty(text)` | `<p class="empty-state">{text}</p>` |
| `ui.card(title=None)` + `{% call %}` | `<section class="card">`, with `<h2 class="card-title">{title}</h2>` when given, then the caller's content |
| `ui.when(day, time=None, today=None)` | `<time datetime="{iso}">{datum(day)}{" om HH:MM" if time}</time>` and, when `today` is given, ` <span class="relative">({relatief(day, today)})</span>`; `datetime` is `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM` |
| `ui.model_state(up, text)` | `<p class="model-state model-state-{up|down}"><span class="dot" aria-hidden="true"></span>{text}</p>` |
| `ui.alert(text, kind="info")` | `<div class="alert alert-{kind}" role="status">{text}</div>`; kinds `info`, `success`, `danger` |

### Layout (`base.html`)
- First element in `<body>`: `<a class="skip-link" href="#inhoud">Naar de inhoud</a>`.
- `<header class="site-header">` with `<a class="brand" href="/">Scrum agent</a>` and the
  `<nav aria-label="Hoofdnavigatie">`. Nav items come from one `{% set nav_items = [...] %}`
  list (path, label). A link is current (`aria-current="page"`) on its own path and, except
  `/`, on paths below it (`/meetings/5` → Vergaderingen).
- `<main id="inhoud" class="container">`, `<footer class="site-footer">` with links to
  `/privacy` and `/stijl`.

### Look
Calm and functional. Page background `--color-bg`, content in white cards with
`--radius`, `--shadow` and a 1px `--color-border`. Header: white bar with the brand left and
the nav right (wrapping under the brand below 640 px); the current nav item gets
`--color-accent-soft` with accent text. Buttons: primary = accent background, secondary =
white with border, danger = danger text and border (filled on hover). Lists of deadlines and
meetings are `<ul class="list">` with `<li class="list-item">` rows (title left, date and
actions right, stacking on small screens), not tables. Badges are pill-shaped: queued
neutral-soft, running info-soft, done success-soft, failed danger-soft, with the matching
text colour. Focus is always visible (`:focus-visible` outline in the accent colour).
Readable at 360 px without horizontal scrolling. Light theme only.

Layout helpers in `app.css` (use them instead of new one-off classes):
- Header and footer span the full width; their content lines up with the 960 px column via
  `--gutter`. Below 640 px the nav is one horizontally swipeable row under the brand.
- `.card-grid`: cards side by side on wide screens, stacked on phones.
- List rows: `<li class="list-item">` with `<div class="list-main">` (`.list-title`,
  `.list-meta`, `.note`) and `<div class="actions">` (never a `<p>`: a `<form>` inside a
  `<p>` breaks out of it). Buttons in `.actions` render small.
- Forms: `.form-grid` puts short fields side by side; `.form-actions` holds the buttons.
  Put length limits in the field `hint`, not in the label.
- `.lead` (intro under the `<h1>`), `.meta` (badge and facts under the `<h1>`),
  `.page-actions` (button row at the end of a page; "Terug" is an `<a class="btn btn-secondary">`).
- `.items` for decision / action item / question lists, with `.item-meta` and `.chip`.
- `.facts` / `.fact` / `.fact-detail` for label–value rows. No `<table>`: tables overflow on phones.
- Inputs use 16 px text (smaller makes iOS Safari zoom in on focus).

### Style guide page
`GET /stijl` (behind the team password, not in the nav, linked from the footer) shows every
component in every variant with sample data, so a change to a token or macro can be checked
in one place.

## Pages
| Path | Shows | SPEC |
| --- | --- | --- |
| `/` | Next 5 deadlines, last 3 meeting jobs, model state, links to the rest | — |
| `/deadlines` | Upcoming list, collapsed past list, add form; edit/delete per row | 3 |
| `/deadlines/{id}/edit` | Edit form (same fields) | 3.4 |
| `/meetings` | Upload form, job list (`/meetings/partial` refreshes every 10 s), model state | 7.1, 7.3 |
| `/meetings/{id}` | Summary, decisions, action items, open questions, post/delete buttons | 7.8, 8.3 |
| `/settings` | Reminder settings form, webhook state, "Stuur testbericht" | 4 |
| `/privacy` | What is stored, how long, how to delete (Dutch, from `docs/privacy.md`) | 8.4 |
| `/stijl` | Style guide: every component and variant | — |

Nav (in `base.html`, from `nav_items`): Overzicht `/`, Deadlines, Vergaderingen, Instellingen,
Privacy; the current page's link has `aria-current="page"`.

## Polling
The job list polls only while something is queued or running: render
`hx-get="/meetings/partial" hx-trigger="every 10s" hx-swap="outerHTML"` on the list element
only in that case, so a finished list stops polling.

## Testing
Render pages with TestClient (with auth) and assert on the HTML: the expected titles and
Dutch labels, the empty states, form errors with status 422, `aria-current`, and that no
template contains `<script>` without `src`. See `docs/testing.md`.
