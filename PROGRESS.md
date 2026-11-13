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

## T06
- Added `Deadline` model to `backend/app/models.py`: columns `id`, `title` (varchar 200), `due_date` (date, not null), `due_time` (time, nullable), `note` (text, nullable), `source` (varchar 20, default 'manual'), `external_ref` (varchar 500, nullable), `created_at`/`updated_at` (timestamptz, not null) with `now_utc()` defaults.
- Created migration `backend/alembic/versions/0002_deadline.py`: adds the `deadline` table with PostgreSQL-compatible types, `server_default='manual'` for source, `server_default=now()` for timestamps. Downgrade drops the table.
- Created `tests/test_models_deadline.py` (11 tests): table existence, insert minimal, insert with time+note, external_ref, source DB default check, source override, timestamps set on insert, updated_at changes on update, column names match model, timestamps are UTC-aware, title max length.
- 96% total coverage, `make check` exit 0. Next task T07 needs service functions in `app/deadlines.py`.

## T07
- Created `backend/app/deadlines.py`: Pydantic `DeadlineIn` model with SPEC 3.1 validation (title 1-200 chars, note ≤1000, source `manual`/`github`, Dutch error messages). Service functions: `create(session, data, now)`, `update(session, id, data, now)`, `delete(session, id)`, `upcoming(session, today, now)` (today+future, sorted), `between(session, start, end, now)` (inclusive both ends, sorted), `past(session, today, now)` (before today, sorted). Sorting: date ascending, time ascending (None → end of day via `time(23,59)`).
- Created `backend/tests/test_deadlines_service.py` (23 tests): 200 vs 201 chars, empty title with Dutch message, bad time rejection, valid time acceptance, note length, invalid source, create minimal/all fields, update existing/nonexistent, delete existing/nonexistent, sorting by date+time, no-time=end-of-day sorting, between inclusive both ends, upcoming excludes past, past excludes today.
- Coverage: deadlines.py 92%, total 95% (≥90% met). All 119 tests pass, `make check` exit 0.
- Note: `now` parameter accepted by all service functions for testability; defaults to `clock.now_utc()`. The `_sort_key` helper is private and not exported. Routes/API layer for deadlines is T08+.

## T08
- Created `app/deadlines.py` API endpoints: `GET /api/v1/deadlines` (query param `include_past`, defaults to upcoming-only), `POST /api/v1/deadlines` (accepts `DeadlineIn`, returns 201), `DELETE /api/v1/deadlines/{deadline_id}` (204 on success, 404 if missing).
- Added `DeadlineOut` Pydantic model and `_deadline_to_out()` helper for serialisation. All responses are JSON; routes protected by `require_team` auth.
- Wired `deadlines_api_router` into `create_app()` in `backend/app/main.py`.
- Created `backend/tests/test_deadlines_api.py` (20 tests): covers empty list, single deadline, multiple deadlines, `include_past` flag, sorting, 400 on invalid payload, 401 without auth, 404 on unknown id, 422 on bad data, 201 on valid create, 204 on delete, 200+204 after create, `list_deadlines` returns combined past+upcoming when `include_past=true`.
- Gotcha: `get_db()` is a generator — must call `next(get_db())`, not `get_db()()`. Tests must commit after `create()` so separate API sessions can see the data. SQLAlchemy 2.x requires `scalars().all()` instead of deprecated `scalar_all()`.
- All 139 tests pass, 95% coverage, `make check` exit 0.

## T10
- Implemented `/deadlines` page (GET list + POST add), `/deadlines/{id}/edit` (GET form + POST save), and `/deadlines/{id}/delete` (POST) in `app/web.py`. All routes use `POST/Redirect/GET`, validate input matching `DeadlineIn` rules, and return 404 for unknown IDs.
- Created templates: `deadlines.html` (upcoming/past tables with edit links and delete forms), `edit.html` (pre-filled edit form). Delete confirmation handled by external `static/app.js` (CSP-compliant, no inline scripts).
- Updated `base.html` to load `app.js`. Fixed typo "Nkomende" → "Komende" in deadlines template.
- Created `backend/tests/test_page_deadlines_edit.py` (30 tests): covers page rendering, add/edit/delete CRUD, validation errors, 404s, input preservation on errors, redirects. All 169 tests pass, 97% coverage, `make check` exit 0.
- Note: T09 (/deadlines page) was skipped and merged into this task. CSP forbids inline scripts, so delete confirmation uses `class="delete-form"` + `app.js`.

## T11
- Created `app/cards.py`: pure functions `test_card()`, `weekly_overview()`, `deadline_reminder()`, `sprint_nudge()` returning Adaptive Card 1.4 dicts with `wrap: true` on all body elements; Dutch text via `datum_kort()` and `relatief()`. `_Dict` alias (`dict[str, object]`) used for all return/input types to satisfy MyPy strict mode; `datetime.time` handled via `_time_str()` helper with duck-typing.
- Created `tests/test_cards.py` (29 tests): verifies card schema version, title patterns, FactSet label format (`"ma 16 nov 23:59"`), relative labels (`"vandaag"`, `"morgen"`, `"over N dagen"`), empty-state messages, week numbers, and JSON serializability. All 198 tests pass, 97% coverage, `make check` exit 0.
- Note: `deadline_reminder` and `weekly_overview` accept `dict[str, object]` parameters; cast to `date`/`time` before passing to `datum_kort`/`_time_str`. `sprint_nudge` computes weekday from the given `end_date`. `summary_card()` and `teams.envelope()` remain to be implemented by later tasks.

## T12
- Added `PostLog` model to `app/models.py`: columns `id`, `kind` (varchar 20), `ref_key` (varchar 500, unique), `status` (varchar 20), `attempts` (int, default 0), `last_error` (text, nullable), `created_at`/`sent_at` (timestamptz).
- Created Alembic migration `0003_post_log.py` (upgrade adds table, downgrade drops it).
- Created `app/teams.py` with `envelope(card)` (wraps card in Teams message format), `_cap_body()` (recursive 28 KB JSON cap truncating TextBlocks with "… (ingekort)"), and `post_card(card, client=...)` (POSTs to webhook with 15 s timeout, classifies 2xx=ok, 429/5xx/network=retryable, other 4xx=permanent, exceptions mapped to retryable/permanent).
- Created `tests/test_teams_post.py` (18 tests): exact envelope shape, HTTP 200/202/429/503/400/401, timeout and connection-refused retryable, 40 KB→28 KB truncation, JSON wire capture, URL never leaked in errors, empty webhook URL short-circuits to ok.
- All 216 tests pass, 97% coverage, `make check` exit 0. Next task T13 needs to wire `post_card` into a cron tick function that inserts `PostLog` rows and retries failures.
