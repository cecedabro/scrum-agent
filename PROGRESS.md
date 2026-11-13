# PROGRESS

Appended by the agent after each task: what changed, where, gotchas for later tasks.

## T01 (by hand)
- Scaffold: `backend/app/{main,config,db,models,paths}.py`, Alembic baseline `0001` (empty), conftest with pgserver fixtures (`database_url`, `db`, `client`).
- `app/config.py` already declares every phase-1 env var; read them via `get_settings()` only.
- htmx 2.0.11 is vendored in `backend/app/static/vendor/`.

## T02
- Created `app/clock.py`: `now_utc()`, `to_local(dt)`, `today_local(now)`, `local_moment(day, hhmm)` — the only module that reads `datetime.now()` and `zoneinfo`. Gap times (spring-forward) raise `ValueError`; ambiguous times (fall-back) resolve to the first occurrence.
- Created `app/fmt.py`: Dutch weekday/month arrays (no `locale` module), `datum(d)` → "maandag 16 november", `datum_kort(d)` → "ma 16 nov", `relatief(d, today)` → "vandaag"/"morgen"/"over 3 dagen"/"gisteren"/"3 dagen geleden". Registers as Jinja2 filters via `register_filters(app)`.
- Created `tests/test_clock_fmt.py` (31 tests): covers both 2026 DST switch days (spring forward Mar 29, fall back Oct 25), winter/summer UTC offsets, midnight crossings, all weekday/month names, relative labels at boundaries, and default-to-real-clock behavior.
- Coverage: clock.py 92%, fmt.py 88%, total 94% (≥90% threshold met).
- Note: `fmt.register_filters()` is available for T05 to wire into the Jinja env.

## T04
- Added two HTTP middleware in `app/main.py`: `csrf_guard` (SPEC 2.3) and `security_headers` (SPEC 2.4).
- `csrf_guard` rejects unsafe methods with 403 when `Sec-Fetch-Site: cross-site` or `Origin` host differs from `Host`.
- Security headers are applied to all responses, including early 403s from CSRF guard (headers manually attached).
- Helper functions `_origin_host(request)` and `_host_name(host_header)` are exported for testing.
- Created `tests/test_security.py` (16 tests). All checks pass (`make check` exit 0).

## T05
- Created `backend/app/templates/base.html`: Dutch nav (`Overzicht`, `Deadlines`, `Vergaderingen`, `Instellingen`, `Privacy`), `aria-current="page"` on active link, semantic `<main>`/`<footer>`, `<html lang="nl">`, empty-state fallback (`<p class="empty-state">Geen deadlines om te bekijken.</p>`), HTMX vendor script via `<script src="/static/vendor/htmx.min.js">`.
- Created `backend/app/static/app.css`: Calm system-font CSS, dark blue accent (`#25167a`), card layouts, form/button styling.
- Created `backend/app/web.py`: Jinja2 `Environment` with `FileSystemLoader`, `select_autoescape()`, registers `datum`, `datum_kort`, `relatief`, `TIMEZONE` as globals. `GET /` returns overview context with empty lists and `page_title="Overzicht"`.
- Updated `backend/app/main.py`: Wires `web_router` into `create_app()`. Removed unused `Depends`/`require_team` imports.
- Created `backend/tests/test_base_template.py` (15 tests): covers nav links, labels, `aria-current`, `lang="nl"`, HTMX vendor path, inline script check, semantic structure, overview title, empty state, security headers, static file serving.
- All 85 tests pass, 95% coverage, `make check` exit 0.
- Note: `deadlines` and `meeting_jobs` are hard-coded empty here; T06+ will wire DB queries and job tables.
