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

## Look
Calm and functional: system font stack, one accent colour (e.g. HvA-ish dark blue
`#25167a` on white), cards with a light border, generous spacing, clear status badges
(queued grey, running blue, done green, failed red). Light theme only is fine.

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

Nav (in `base.html`): Overzicht `/`, Deadlines, Vergaderingen, Instellingen, Privacy; the
current page's link has `aria-current="page"`.

## Polling
The job list polls only while something is queued or running: render
`hx-get="/meetings/partial" hx-trigger="every 10s" hx-swap="outerHTML"` on the list element
only in that case, so a finished list stops polling.

## Testing
Render pages with TestClient (with auth) and assert on the HTML: the expected titles and
Dutch labels, the empty states, form errors with status 422, `aria-current`, and that no
template contains `<script>` without `src`. See `docs/testing.md`.
