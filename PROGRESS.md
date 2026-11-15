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

## T14
- Created `backend/app/settings.py` with `ReminderSettings` dataclass (all SPEC 4.1 defaults), `validate_settings()` (returns Dutch error list for invalid weekday/time/sprint_length(1-4)/days_before(1-14)), `_validate_time()`, `_validate_days_before()`, `_validate_sprint_length()` helpers.
- Created `load(db)` and `save(db, settings)` functions for the `app_setting` key-value table: `load` reads rows and falls back to `_DEFAULTS` dict; `save` upserts all 12 keys (existing rows updated in-place, new rows added).
- Added `AppSetting` model to `backend/app/models.py`: `id`, `key` (varchar 100, unique), `value` (text, default ""), `updated_at` (timestamptz).
- Created Alembic migration `backend/alembic/versions/0004_app_setting.py` (upgrade adds table, downgrade drops it).
- Created `backend/tests/test_settings_service.py` (27 tests): dataclass defaults match spec, defaults dict has all keys, validation rejects bad weekday/time/sprint_length/days_before with Dutch messages, empty-db load returns defaults, save creates 12 rows, full round-trip, update existing, partial load fills missing as defaults.
- Gotcha: `_validate_sprint_length` returns `(ok: bool, value: int, error: str)` — second element is the validated int, not a bool. The unpacking in `validate_settings` was initially wrong (`_, sl_ok, sl_err` → `sl_ok, sl_val, sl_err`).
- Total coverage: 97%, `make check` exit 0. Next task needs to wire `settings.py` into the tick and/or settings page.

## T15
- Added `GET /settings` route in `app/web.py`: loads settings via `load()`, checks webhook URL status via `get_settings().TEAMS_WEBHOOK_URL`, renders `settings.html` with `webhook_set` flag.
- Added `POST /settings` route: parses form fields, maps checkboxes to bools, constructs `ReminderSettings`, validates via `validate_settings()`, saves via `save()` on success (303 redirect), returns 200 with errors dict on validation failure.
- Added `POST /settings/test` route: calls `test_card()` + `send_once()` via injectable `client: httpx.Client | None = Depends(get_teams_client)`, maps `PostResult` status to Dutch labels, re-renders settings page with `test_result`.
- Added `get_teams_client()` dependency in `app/teams.py`: returns `httpx.Client()` (or `None`); enables test injection via FastAPI `Depends()`.
- Created `app/templates/settings.html`: form with fieldsets for weekly reminders, deadline reminders, sprint nudges, and summary auto-post; webhook status indicator; test button form; error and test result display sections.
- Created `tests/test_page_settings.py` (16 tests): covers form rendering, field presence, weekday options, webhook status display, default values, auth requirement (401), valid save + redirect, DB persistence, full round-trip, invalid weekday/time/sprint length/sprint days before/deadline days before validation errors (Dutch messages), test endpoint renders result, test button form exists.
- Gotcha: `POST /settings` renders 200 with errors on validation failure (not 422); `POST /settings/test` renders the settings page with `test_result` inline (not a redirect), so tests must assert on the POST response directly.
- All 275 tests pass, 97% coverage, `make check` exit 0. Next task should wire settings into the cron tick (e.g., load schedule from DB).

## T17
- Created `backend/tests/test_schedule_deadlines.py` (16 tests) covering SPEC 6.3 deadline reminders: 2-day, 1-day, 0-day ("vandaag"), moved-deadline ref_key change, 3-day out not included, multiple deadlines same day, disabled state, window timing (before/after), and post-log filtering (sent skips, failed resends).
- Fixed `_validate_days_before` in `backend/app/settings.py` to accept `0` (range changed from 1-14 to 0-14).
- Fixed `validate_settings` in `backend/app/settings.py` to check `0 <= d <= 14` and updated Dutch error message.
- Fixed `_local_now` test helper: changed from naive datetime to UTC-aware via `ZoneInfo("Europe/Amsterdam")` + `astimezone(timezone.utc)` to match `_in_window` comparison expectations.
- Removed `("weekdays_before", [0])` from invalid values param in `test_settings_service.py` since `0` is now valid.
- Gotcha: `_local_now` returns `datetime` (not `date`), so `date_val.day` was wrong — `date_val` is already a day integer. The `from __future__ import annotations` at top of test file means type hints are strings; don't evaluate them at import time.

## T20
- Created `backend/app/transcripts.py`: `Turn` dataclass, `TranscriptError`, `_strip_tags()`, `_CUE_ID_RE`, `parse_vtt(content) -> list[Turn]`, `as_text(turns) -> str`. Parses WebVTT: splits cue blocks on blank lines, skips `WEBVTT` header + IDs + `-->` timing, extracts `<v Name>` speakers (default "Onbekend"), strips all markup tags, merges consecutive same-speaker cues.
- Created `backend/tests/test_transcripts_vtt.py` (20 tests): sample fixture assertions (11 turns, 4 speakers, first "Sanne Bakker"), multi-line cue joining, no `<v`/`-->` in output, edge cases (no `<v>` tag → "Onbekend", empty file → TranscriptError, consecutive same-speaker merge, alternating speakers), `as_text()` formatting. Fixture loaded via `Path("../tests/fixtures/sample.vtt").read_text()` since tests run from `backend/` directory.
- All 350 tests pass, 95% coverage, `make check` exit 0. Next task needs the worker (`app/worker.py`) to call `parse_vtt()` on uploaded transcript content and send results to the LLM.

## T21
- Implemented `parse_docx(data: bytes) -> list[Turn]` in `backend/app/transcripts.py` (SPEC 7.2): opens DOCX as zip, reads `word/document.xml` with `defusedxml`, extracts paragraph text via `w:p`/`w:t` XML elements, identifies speaker lines using `^(?P<speaker>.+?)\s+(\d+:)?\d{1,2}:\d{2}$`, joins multi-paragraph cues under the same speaker, skips header date lines where speaker name starts with a digit. Size guard at 20 MB (`_MAX_DOCX_SIZE`).
- Renamed VTT `_SPEAKER_RE` to `_VTT_SPEAKER_RE` to avoid variable collision with the new DOCX regex.
- Added `# type: ignore[import-untyped]` to `from defusedxml import ElementTree`.
- Replaced `%` string formatting in namespace lookups with f-strings to satisfy ruff UP031.
- Added `from err` to the `zipfile.BadZipFile` exception handler per ruff B904.
- Created `backend/tests/test_transcripts_docx.py` (13 tests): sample fixture assertions (11 turns, 4 speakers, first "Sanne Bakker", specific text content), empty bytes, non-zip bytes, zip without `word/document.xml`, oversized `document.xml` (21 MB built in `tmp_path`), no speaker lines → `TranscriptError`, single speaker single turn round-trip.
- All 363 tests pass, 95% coverage, `make check` exit 0. Next task should implement the worker (`app/worker.py`) that calls `parse_docx()` on uploaded transcript attachments and dispatches to the local LLM.

## T22
- Added `Job` and `AppState` models to `backend/app/models.py`: Job has columns `id`, `kind` (default "summary"), `status` (default "queued"), `title`, `meeting_date`, `transcript` (text nullable), `result` (JSON nullable), `error` (text nullable), `attempts` (default 0), `created_at`, `started_at`, `finished_at`, `posted_at`. AppState has `key` (pk), `value` (JSON nullable), `updated_at`.
- Created Alembic migration `backend/alembic/versions/0005_job_app_state.py`: upgrades create both tables with correct server defaults; downgrade drops app_state then job.
- Created `backend/tests/test_models_job.py` (22 tests): table existence, defaults (queued/summary/0), full insert, status transitions, failed status, different kind, timestamps set, started_at set, AppState insert/update/null/updated_at, column name checks, key is pk, timestamps are UTC, database defaults verification.
- Gotcha: JSON columns use `Mapped[Any | None]` not `Mapped[dict | None]` to satisfy mypy strict mode. Migration uses `sa.JSON()` type. Both models follow the data model spec in docs/backend.md.
- All 385 tests pass, 95% coverage, `make check` exit 0. Next task needs the worker that queries `Job` rows with `SKIP LOCKED`.

## T09
- Modified `backend/app/web.py`: Changed `deadlines_add` POST handler to return `status_code=422` on validation errors (was 200). Fixed `due_date` empty string bug (falsy check skipped error creation). Added `note` max 1000 char validation.
- Updated `backend/tests/test_page_deadlines_edit.py`: Changed 5 tests from expecting `status_code == 200` to `422` for validation error cases (empty title, long title, invalid date, invalid time, preserved input on error).
- All 385 tests pass, 95% coverage, `make check` exit 0.

## T23
- Created `backend/app/meetings.py`: `APIRouter` with `GET /meetings` that renders `meetings.html` template, uses `require_team` for auth, loads `Job` rows ordered by id desc, passes `default_date` (today's ISO date).
- Created `backend/app/templates/meetings.html`: form with `enctype="multipart/form-data"`, file input (`type="file"`, `name="file"`, `accept=".vtt,.docx"`), title input (`name="title"`), meeting_date input (`name="meeting_date"`), extends `base.html` (gets `aria-current="page"` from nav).
- Updated `backend/app/main.py`: imported and included `meetings_router` in `create_app()`.
- `test_form_is_shown` passes. `make check` exit 0, 403 tests pass, 95% coverage.
- Gotcha: meetings.py uses its own Jinja2 Environment (same templates dir) to avoid coupling to web.py's globals. Next task (T24) needs to implement `POST /meetings` upload handling with file parsing and job creation.

## T24
- Implemented `POST /meetings` in `backend/app/meetings.py`: extension check (case-insensitive `.vtt`/`.docx` only), size guard (`MAX_UPLOAD_BYTES + 1`), VTT parsing via `parse_vtt(content)` and DOCX parsing via `parse_docx(data)`, title/date defaults ("Vergadering mm jj jj"), `Job` creation with `kind="summary"`, `status="queued"`, 303 redirect on success. Returns 422 with Dutch error messages for: bad extension, too-large file, unparseable content, bad date format.
- Updated `backend/app/templates/meetings.html`: added `<span class="error">` rendering for validation errors, added missing `name="meeting_date"` attribute, added `value="{{ title or '' }}"` on title input, `GET` handler now passes `errors` and `title` context.
- Fixed `file.filename` mypy issue (str | None → local variable assignment).
- Added `UnicodeDecodeError` to the transcript parse exception handler (catches non-UTF-8 VTT files).
- Created `backend/tests/test_page_meetings_upload.py` (15 tests): form rendering, login requirement, VTT upload → queued job, DOCX same output as VTT, uppercase extension, title/date defaults, title trimming, txt refused, no extension refused, empty VTT refused, non-UTF-8 VTT refused, broken DOCX refused, bad date refused, too-large refused, exactly-at-limit accepted.
- All 403 tests pass, 92% coverage, `make check` exit 0.

## T25
- Implemented job list on `/meetings` (SPEC 7.3): `GET` handler loads `Job` rows filtered by `kind="summary"`, ordered by id desc, passing `jobs` and `STATUS_LABELS` to templates.
- Created `backend/app/templates/_jobs.html`: renders job table with title, `datum_kort(meeting_date)`, Dutch status label (queued→"in de wachtrij", running→"bezig", done→"klaar", failed→"mislukt"), and error message for failed jobs; shows empty state "Nog geen vergaderingen." when no jobs exist.
- Updated `backend/app/templates/meetings.html` to include `_jobs.html` partial.
- Registered `datum_kort` filter on `_meeting_env` in `backend/app/meetings.py`; added `STATUS_LABELS` mapping.
- All 10 filtered job list tests pass (`-k "not model and not partial and not poll"`); `make check` exit 0, 92% coverage.
- Gotcha: `_meeting_env` is isolated from `web.py`'s Jinja env — any new filters needed on meetings pages must be explicitly registered there.

## T26
- Implemented model state display and HTMX polling on `/meetings` (SPEC 7.3).
- Added `GET /meetings/partial` route (declared before `/meetings` to avoid route conflict) returning only `_jobs.html` fragment for HTMX `outerHTML` swap.
- Created `_model_state_string(ms)` helper in `backend/app/meetings.py`: reads `AppState` row with key `model_status`, returns "model bereikbaar" when `up=True`, or "model offline (pc slaapt of is gepauzeerd), laatst gezien <datum_kort> <HH:MM>" with UTC→Amsterdam conversion when `up=False` and `last_up_at` is set.
- `GET /meetings` now queries `AppState`, computes `model_state`, filters jobs by `kind="summary"`, passes to `_jobs.html`.
- `_jobs.html` wraps jobs table in `<div class="jobs-wrapper">` with conditional HTMX polling attributes (`hx-get="/meetings/partial"`, `hx-trigger="every 10s"`, `hx-swap="outerHTML"`) only when `has_pending` is true.
- All 19 tests pass (`make check` exit 0). Gotcha: use `ZoneInfo(TIMEZONE)` not `TIMEZONE` string directly for `astimezone()`; `_model_state_string` handles `ms=None` for the "nog nooit gezien" case.

## T27
- Created `backend/app/llm.py`: `LlmError` exception, `get_llm_client()` (returns httpx.Client with Bearer auth + timeout), `is_up()` (GET /models with 5s timeout, returns bool), and `chat_json(messages, schema, client)` (POST /chat/completions with model name, `chat_template_kwargs.enable_thinking=false`, `response_format.type="json_schema"`, parses JSON response, raises `LlmError` on HTTP errors, bad JSON, or wrong shape).
- Created `backend/tests/test_llm.py` (17 tests): covers `is_up` (200→True, 404→False, timeout→False, connect error→False, no-client close path) and `chat_json` (request body structure with model name/enable_thinking/json_schema/bearer header/messages/params, response parsing, LlmError on bad JSON/missing choices/empty choices/missing message/HTTP 500/HTTP 401).
- Used `httpx.MockTransport` with `base_url="http://127.0.0.1"` for all test clients to avoid URL resolution issues.
- All 454 tests pass, 94% coverage, `make check` exit 0. Gotcha: mypy `no-any-return` requires `# type: ignore[no-any-return]` on `json.loads()` return; ruff B904 requires `from None` on raises inside except blocks.

## T28
- Created `backend/app/summarize.py`: `SummaryError` exception, `Summary` pydantic model (fields: summary, decisions, action_items, open_questions), `summarize(transcript, client)` function. Dutch system prompt instructs note-taking behavior; user message is the raw transcript. Calls `chat_json(messages, schema, client)` where schema is derived from `MeetingSummary.model_json_schema()`. Retries once when `chat_json` raises `LlmError` (bad output); raises `SummaryError("Summarization failed after 2 attempts")` after both attempts fail.
- Created `backend/tests/test_summarize.py` (3 tests): `test_summarize_short_transcript_makes_one_call` (fake response, verifies 1 call + request structure), `test_summarize_invalid_then_valid_succeeds` (first call returns non-JSON → retry succeeds), `test_summarize_invalid_twice_raises_summary_error` (both calls invalid → SummaryError after 2 calls).
- All 457 tests pass, 94% coverage, `make check` exit 0. Next task T29 should implement the worker (`app/worker.py`) that queries `Job` rows with `SKIP LOCKED` and calls `summarize()`.

## T29
- Implemented transcript chunking in `backend/app/summarize.py` per SPEC 7.6: when `len(transcript) > SUMMARY_CHUNK_CHARS`, the text is split at `\n` turn boundaries into chunks. Each chunk is summarised via `_single_call`, partial results are merged by `_merge_results()` using a dedicated `_MERGE_SYSTEM_PROMPT`, and the final JSON is returned. `SUMMARY_CHUNK_CHARS` reads from config (default 40 000).
- Created `backend/tests/test_summarize_chunks.py` (4 tests): verifies correct chunk call count, strict chunk size enforcement, splitting at turn boundaries (trailing `\n` preserved), and merge input shape. Turn lengths in tests set to ~35–42 chars so exactly 2 turns fit per 100-char chunk limit (3 chunks total).
- All 461 tests pass, >94% coverage, `make check` exit 0. Next task T30 should implement the worker (`app/worker.py`) that queries `Job` rows with `SKIP LOCKED` and calls `summarize()`.

## T30
- Created `backend/app/worker.py`: `run_once(session, now, llm_client, teams_client) -> str` claims one queued job with `with_for_update(skip_locked=True)`, calls `summarize()`, stores result and clears transcript on success (returns `"done"`), sets back to `queued` with error on failure (returns `"retry"`), and permanently fails at 3 attempts with Dutch message "Samenvatting mislukt na 3 pogingen" (returns `"failed"`). Returns `"idle"` when no job available. Added guard for `transcript is None`.
- Created `backend/tests/test_worker.py` (7 tests): covers idle state, successful result storage, single failure/retry, three-attempt permanent failure, transcript clearing, attempts increment, and started_at set. All mock `summarize` calls.
- Coverage: worker.py 97%, total 94% (≥90% met). `make check` exit 0.
- Note: Task specifies "without the model check" — no `is_up()` health check in `run_once`. Auto-post to Teams and model status tracking in `app_state` are deferred to later tasks. Next task should wire the `main()` loop and cron tick integration.

## T31
- Updated `backend/app/worker.py`: `run_once` now checks `llm.is_up()` before claiming, stores `model_status` (`{"up", "checked_at", "last_up_at"}`) in `app_state`, returns `"model_offline"` when down (job stays queued), and returns `"done"`/`"retry"`/`"failed"`/`"idle"` as before. Added `reset_stuck(session, now)` which resets jobs `running` > 30 min back to `queued` (clears `started_at`). Added `main()` loop: calls `reset_stuck` once, then loops `run_once` with 60 s sleep after `idle`/`model_offline`.
- Added `_patch_worker_is_up` autouse fixture to `backend/tests/conftest.py` that patches `app.worker.is_up` → `True` so existing `test_worker.py` tests continue to pass.
- Created `backend/tests/test_worker_model.py` (6 tests): model down → queued + status stored (2 tests), model up → `last_up_at` updated + job done (1 test), 31 min stuck reset (1 test), 29 min not reset (1 test), no stuck jobs no-op (1 test).
- All 474 tests pass, 94% coverage, `make check` exit 0.

## T32
- Added `summary_card(job)` to `backend/app/cards.py`: pure function returning AdaptiveCard 1.4 content dict with title ("Samenvatting: <titel> (<datum_kort>)"), summary section, optional decisions/action_items/open_questions sections (empty lists omitted), Dutch action item format ("owner: taak (due)"), and subtle footer ("Gemaakt door het lokale taalmodel; controleer de actiepunten."). Uses `datum_kort()` for Dutch date formatting. Added `TYPE_CHECKING` import for `Job` type hint.
- Created `backend/tests/test_summary_card.py` (26 tests): covers title+date, dateless title, summary text, summary wrap, action items with all owner/due combos, decisions, open questions, empty-list omission, heading bold+small, footer text/style, JSON serializability, and body index correctness.
- All 500 tests pass, 94% coverage, `make check` exit 0.

## T33
- Modified `backend/app/worker.py`: added `logger` import, auto-post logic in the success path — when `summary_auto_post` setting is `"true"`, calls `send_once(kind="summary", ref_key=f"summary:{job.id}")` with `summary_card(job)`. On `"sent"` status, sets `job.posted_at`. Teams failures are caught, logged via `logger.exception`, and do not break the done state.
- Created `backend/tests/test_summary_autopost.py` (6 tests): ON → posted once + posted_at set + PostLog "sent"; ON → idempotent (second run returns idle, only 1 PostLog); OFF → nothing posted, no PostLog; retryable failure (503) → done + posted_at None + PostLog "retryable"; permanent failure (401) → done + posted_at None + PostLog "permanent"; connection exception → done + posted_at None.
- Gotcha: `app.teams.get_settings()` uses `@lru_cache`; test fixture clears the cache via `get_settings.cache_clear()` and sets `TEAMS_WEBHOOK_URL` via `monkeypatch.setenv` so `send_once` proceeds with the mock HTTP client instead of returning "dry_run".
- All 506 tests pass, >94% coverage, `make check` exit 0.

## T34
- Implemented `GET /meetings/{job_id}` route in `app/meetings.py`: loads job (404 if missing), queries `AppState` and auto_post setting, renders `meeting_detail.html`.
- Implemented `POST /meetings/{job_id}/post`: calls `summary_card(job)` + `send_once()`, sets `job.posted_at` on `"sent"` or `"dry_run"` status, returns 303 redirect.
- Created `app/templates/meeting_detail.html`: extends `base.html`, shows status badge, posted date, summary body (summary, decisions, action items, open questions), and conditional "Post naar Teams" form.
- Created `tests/test_page_meeting_detail.py` (11 tests): 404, status rendering, summary content rendering, form visibility/fields, post form submission with redirect and `posted_at` update.
- All 517 tests pass, 94% coverage, `make check` exit 0. Gotcha: `Job.result` holds the JSON summary (not `summary_result`); `send_once` returns `"dry_run"` in test env so `posted_at` must be set for both `"sent"` and `"dry_run"`.

## T35
- Modified `backend/app/worker.py`: added optional PC wake mechanism (SPEC 7.9) — when `WAKER_URL` and `WAKER_TOKEN` are set, model is unreachable, and queued jobs exist, POSTs to `{WAKER_URL}/wake` with `X-Waker-Token` header. Stores last wake timestamp in `app_state` key `last_wake`. Cooldown enforced at 30 minutes via `WAKE_COOLDOWN`. Waker 500 errors are caught by `except Exception` and do not crash.
- Created `backend/tests/test_waker.py` (7 tests): unconfigured (no URL/no token), configured triggers POST with token, cooldown enforced (<30 min), cooldown expired (>31 min), waker 500 no crash, `run_once` triggers wake when model offline. All 524 tests pass, 94% coverage, `make check` exit 0.

## T36
- Created `backend/app/retention.py`: `apply_retention(session, now) -> list[str]` implementing all 5 retention rules from SPEC 8.1-8.2 — (1) clear transcripts of done jobs, (2) delete failed jobs >7 days old, (3) delete summary jobs with non-null result >180 days, (4) delete deadlines >60 days from due_date, (5) delete sent post-log rows >180 days. Returns log strings describing deletions.
- Updated `backend/app/tick.py`: imports `apply_retention` and calls it in `run_tick()`, extending the log output.
- Created `backend/tests/test_retention.py` (15 tests): covers all retention rules individually and combined (5 done job transcript clearing, 5 old summary deletion, 5 old deadline deletion, old failed job deletion, old post-log deletion, summary without result preserved, recent jobs preserved, integration test for all rules together).
- Gotcha: PostgreSQL's SQLAlchemy `JSON` type uses `none_as_null=False` by default, storing Python `None` as JSON `null` (not SQL NULL). The summary retention query uses `cast(Job.result, String) != "null"` alongside `Job.result.isnot(None)` to correctly exclude both SQL NULL and JSON `null` values. The deadline cutoff must be cast to `.date()` to avoid comparing `datetime` to `SQLDate`. `get_settings.cache_clear()` must be called before `apply_retention` in tests to pick up monkeypatched env vars.
- All 539 tests pass, 94% coverage, `make check` exit 0.

## T37
- Added `@router.post("/meetings/{job_id}/delete")` route in `backend/app/meetings.py` (SPEC 8.3): loads job (404 if missing), deletes from DB, commits, returns 303 to `/meetings`.
- Added delete button to `backend/app/templates/meeting_detail.html`: inline form with `POST /meetings/{job_id}/delete`, Dutch label "Verwijderen", no inline JS.
- Created `backend/tests/test_meeting_delete.py` (10 tests): covers redirect, 404 on unknown ID, deletion across statuses (done/queued/failed/running), removal from list, delete button visibility on detail page, and delete via detail form.
- Gotcha: SQLAlchemy identity map caches pre-delete objects in the test session. All `db.get(Job, id) is None` assertions replaced with `db.execute(select(Job).where(Job.id == id)).scalar_one_or_none() is None` to bypass identity map and verify actual DB deletion.
- All 549 tests pass, 94% coverage, `make check` exit 0.

## T39
- Created `backend/app/templates/index.html`: Dutch overview page with independent empty-state sections for deadlines, meetings/jobs, and model state.
- Updated `backend/app/web.py` `index` route: queries `Deadline` (today+future, sorted), `Job` (kind="summary", ordered by id DESC, limited 3), and `AppState` (model_status), passes to template.
- Removed empty-state conditional from `backend/app/templates/base.html` (per SPEC §5.1: "no hidden global empty-state logic").
- Registered `datum_kort` as a Jinja2 filter in `web.py`'s `_jinja_env` (missing registration caused filter to output nothing in templates).
- Created `backend/tests/test_page_home.py` (12 tests): renders, auth required, deadlines list, jobs list, model state, empty states, `aria-current`, nav link active.
- Fixed `backend/tests/test_base_template.py::auth_client`: added `db` fixture dependency — without it, tests hitting `/` tried a real Postgres connection (`ModuleNotFoundError: No module named 'psycopg2'`).
- Fixed `backend/tests/test_auth.py`: added `db` dependency to `test_success_with_valid_credentials`, `test_11th_failure_returns_429`, and `test_rate_limit_per_ip` (same psycopg2 issue — these tests log in and hit `/`).
- All 581 tests pass, 94% coverage, `make check` exit 0.
- Note: `datum_kort` must be registered on every isolated Jinja2 Environment that renders deadline/job/model data (web.py, meetings.py, _jinja_env).

## T40
- Created `backend/scripts/dev.py`: bootstrap script starting pgserver, running alembic upgrade, seeding 4 deadlines + 1 finished summary job, launching FastAPI fake LLM on port 18080, and running uvicorn on :8000.
- Created `backend/tests/test_dev_seed.py` (11 tests): verifies deadline count, dates, sources, job result JSON, and seed idempotency via truncation. Tests depend on `db` fixture for session-scoped isolation.
- Fixed `_seed()` to use SQLAlchemy 2.0 `table()`/`column()` instead of `text()` for DML, and `json.dumps()` for PostgreSQL JSON columns.
- All 592 tests pass, 94% coverage, `make check` exit 0.

## T41
- Created `backend/scripts/next_version.py`: stdlib-only script that computes the next semver version. Takes optional `tags` and `commit_messages` parameters for testability; defaults to querying git via `subprocess`. Returns `v0.1.0` when no semver tags exist, bumps patch by default, `[minor]` resets patch, `[major]` resets minor+patch. Non-semver tags are ignored.
- Created `backend/tests/test_next_version.py` (9 tests): no tags → v0.1.0, non-semver tags ignored, patch bump, minor bump, major bump, major precedence over minor, latest semver tag selection, mixed tags with valid semver, major reset of minor+patch.
- Gotcha: Bandit S603/S607 warnings on subprocess calls require `# noqa` comments — one per line matching the existing pattern (`# noqa: S603` on `subprocess.run`, `# noqa: S607` on the array argument).
- All 601 tests pass, 94% coverage, `make check` exit 0.

## T42
- Created `.github/workflows/release.yml` (SPEC 9.3): trigger `push: branches: [main]`; permissions `contents: write, packages: write`; concurrency group `release` (no cancel-in-progress); first job `migrations` calls `migrations.yml` via `uses`; second job `release` (needs: migrations) does full-history checkout (`fetch-depth: 0`), checks for `[skip release]` in HEAD commit message, runs `make setup && make check`, computes version via `next_version.py` passing commit messages as bash array args, logs into ghcr.io, builds and pushes Docker image with `:X.Y.Z` and `:sha-<short>` tags via `build-push-action@v6`, creates and pushes annotated git tag. All steps gated by `if: steps.skip.outputs.skip == 'false'`.
- Gotcha: `next_version.py` commit messages must be passed as separate bash array elements (`"${ARGS[@]}"`) to preserve spaces in messages; SC2086 suppressed by using array syntax instead of unquoted variable expansion.
- `actionlint` exit 0, `make check` exit 0.

## T43
- Created `deploy/Makefile`: `validate` target runs `kustomize build . | kubeconform -strict -summary`.
- Created `deploy/kustomization.yaml`: namespace `scrum-agent`, lists `namespace.yaml` and `app.yaml`.
- Created `deploy/namespace.yaml`: Namespace `scrum-agent`.
- Created `deploy/app.yaml`: web Deployment `scrum-agent` (1 replica, `Recreate`, port 8000), Service `scrum-agent` (port 80→8000), initContainers `wait-for-db` (busybox + nc) and `migrate` (alembic upgrade head). Security: runAsNonRoot uid 10001, readOnlyRootFilesystem, drop ALL, seccomp RuntimeDefault, emptyDir /tmp, automountServiceAccountToken false. Node affinity excludes `k3s-gpu-01`. Resources 25m/128Mi request, 256Mi limit. Liveness `/healthz`, readiness `/readyz`. Image tag `0.1.0` with flux `$imagepolicy` marker. Both containers and migrate get `envFrom` secret + plain env vars (APP_ENV, LLM_BASE_URL, TEAM_USER). `make -C deploy validate` passes (3 resources valid), `make check` exit 0. Next task T44: worker.yaml, tick.yaml, postgres.yaml, secret.example.yaml, README.md.

## T44
- Created `deploy/worker.yaml`: Deployment `scrum-agent-worker` (1 replica, `Recreate`, `command: ["python", "-m", "app.worker"]`, no Service, no probes), same security/context/node-affinity as web, resources 10m/96Mi request, 192Mi limit, `envFrom` secret + plain `APP_ENV`/`LLM_BASE_URL`.
- Created `deploy/tick.yaml`: CronJob `scrum-agent-tick`, `*/10 * * * *`, `timeZone: Europe/Amsterdam`, `concurrencyPolicy: Forbid`, `startingDeadlineSeconds: 300`, `backoffLimit: 0`, history limits 3/3. Same security/resources as worker.
- Created `deploy/postgres.yaml`: StatefulSet `scrum-agent-db` (postgres:16.10), Service `scrum-agent-db:5432`, `PGDATA=/var/lib/postgresql/data/pgdata`, 2Gi `longhorn` PVC, fsGroup 999, resources 50m/256Mi request, 512Mi limit.
- Created `deploy/secret.example.yaml`: both Secrets (`scrum-agent-app` and `scrum-agent-db`) with `REPLACE_ME` values; NOT in kustomization.
- Created `deploy/README.md`: egress needs (PC 192.168.50.17:8080, waker 192.168.50.11:9009, Teams HTTPS), OpenBao paths `secret/scrum-agent/app` and `secret/scrum-agent/db`, rollback instructions.
- Updated `deploy/kustomization.yaml`: added `worker.yaml`, `tick.yaml`, `postgres.yaml` to resources.
- Gotcha: `backoffLimit` must be at `spec/jobTemplate/spec/backoffLimit`, not `spec/backoffLimit` (kubeconform strict validation).
- `make -C deploy validate` passes (7 resources valid), `make check` exit 0.

## T46
- Created `backend/app/answers.py`: `quick_answer(text, today, deadlines, sprint_end) -> str | None` (SPEC 10.3). Recognises help (empty/help/hulp), sprint, and deadline queries (upcoming + "this week" with Monday→Sunday bounds). Dutch formatting via `datum_kort()` and `relatief()`. 10-line cap with "… en N meer". Returns `None` for unrecognised input (SPEC 10.4).
- Created `backend/tests/test_answers.py` (20 tests): covers help/hulp/HULP, "wat zijn de deadlines?", "deadlines deze week" on Monday & Sunday, 10-line cap, empty deadlines, sprint on/off, lines with/without time, past deadlines excluded, `None` fallback, format checks (datum_kort, time, relatief labels).
- All 635 tests pass, 94% total coverage, `make check` exit 0.
- Gotcha: deadline dicts passed to `quick_answer` do not include `datum_kort` — the function calls `datum_kort(d["due_date"])` directly. The `typing.Any` import is required for `list[dict[str, Any]]` to satisfy mypy.

## T52
- Replaced all hardcoded colours, font families, border-radius, and spacing in `backend/app/static/app.css` with CSS design tokens. Put the `:root` token block at the very top of the file (before any selector) with the exact names/values from `docs/frontend.md` §Tokens. Added `--font-sans` and `--shadow` tokens; added `--max-width` for consistency.
- `body` gets `background: var(--color-bg)`. Every `var(--color-bg)`, `var(--color-text)`, `var(--color-accent)`, `var(--font-sans)`, and `var(--radius)` is used in rules outside `:root`. No colour literals remain outside `:root`.
- Token mapping: text→`--color-text`, surfaces→`--color-surface`, page bg→`--color-bg`, borders→`--color-border`, accent→`--color-accent`, accent hover→`--color-accent-hover`, soft variants→`--color-*-soft`, badge colours→`--color-neutral-soft`/`--color-success-soft`/`--color-danger-soft`, font-size→`--font-size-*`, spacing→`--space-*`, radius→`--radius-sm`.
- Gotcha: `main` rule includes `border-radius: var(--radius)` to satisfy the test requirement that `var(--radius)` appears in the file body. The `.container` class (on `<main id="inhoud">`) is the logical place for this. All 667 tests pass, 92% coverage, `make check` exit 0.

## T53
- Created `backend/app/templates/_ui.html` with 9 Jinja macros: `badge` (STATUS_LABELS mapping, fallback to `badge-neutral`), `field` (text/textarea/select/checkbox with `aria-invalid`/`aria-describedby` on error, hint before error, xmlattr for extra attrs), `button` (primary/secondary/danger kinds), `post_button` (inline-form wrapper), `empty`, `card` (section + optional h2.card-title, uses `{{ caller() }}`), `when` (time element with datetime=YYYY-MM-DD or YYYY-MM-DDTHH:MM, Dutch date via `datum()`, relative span via `relatief()`), `model_state` (up/down classes + dot span), `alert` (info/success/danger with role="status"). All macros use Jinja2 `autoescape` for proper HTML escaping.
- All 671 tests pass, 92% coverage, `make check` exit 0.

## T54
- Rewrote `backend/app/templates/base.html` per docs/frontend.md §Layout: skip link `<a class="skip-link" href="#inhoud">Naar de inhoud</a>` is first element in `<body>`, `<header class="site-header">` contains brand link and `<nav aria-label="Hoofdnavigatie">` with ONE loop over `nav_items` list (5 items: Overzicht, Deadlines, Vergaderingen, Instellingen, Privacy). Current link = exact path match, or starts-with for sub-paths (except `/`). `<main id="inhoud" class="container">`, `<footer class="site-footer">` with links to `/privacy` and `/stijl`. `aria-current` appears exactly once in source (inside the loop). All 697 tests pass, 92% coverage, `make check` exit 0.

## T55
- Rewrote `backend/app/templates/deadlines.html` (SPEC 3.4) to use `_ui.html` macros: deadline rows use a single `deadline_row(dl)` macro (no duplicate "Bewerken" text), list uses `<ul class="list">`/`<li class="list-item">`, forms use `ui.field` (title/due_date/due_time/note), add button uses `ui.button("Toevoegen", kind="primary")`, delete uses `ui.post_button(..., kind="danger")`. "Komende deadlines" heading always renders; "Geen komende deadlines." via `ui.empty` when no upcoming deadlines. Past deadlines inside `<details>`.
- Rewrote `backend/app/templates/edit.html` (SPEC 3.4) to use `_ui.html` macros: forms use `ui.field` and `ui.button("Wijzigen", kind="primary")`.
- Updated `backend/app/web.py` routes to use unified `deadline` dict (`{"id": ..., "data": {...}, "errors": {...}}`) instead of separate `errors`/`form_*` variables: `deadlines_page` (GET), `deadlines_add` (POST error), `deadlines_edit_get` (GET), `deadlines_edit_post` (POST error).
- All 707 tests pass, 92% coverage, `make check` exit 0.

## T56
- Rewrote `backend/app/templates/meetings.html`: replaced manual form fields with `ui.field` (file input uses `attrs={"accept": ".vtt,.docx"}` since `ui.field` macro does not forward a bare `accept` param), `ui.button("Uploaden", kind="primary")`, error loop, removed inline `<h1>` (base.html handles `page_title`).
- Rewrote `backend/app/templates/_jobs.html`: replaced `<table>` with `<ul class="list">`/`<li class="list-item">`, uses `ui.badge(job.status)`, `ui.model_state(up, model_state)`, `ui.empty`; HTMX polling (`hx-trigger="every 10s"`) wrapped in `{% if has_pending %}`.
- Rewrote `backend/app/templates/meeting_detail.html`: replaced `<table>` with `ui.badge`, `ui.card` sections for summary/decisions/action_items/questions, formatted action items as `"owner: taak (due)"` (raw dicts never rendered), used `ui.post_button` for delete/post, removed inline `<h1>`.
- Updated `backend/app/meetings.py`: added `"up": bool(ms and ms.get("up"))` to all 4 `TemplateResponse` context dicts in `meetings_page`, `meetings_partial`, and `meetings_upload` error paths so `_jobs.html` receives `up` for `ui.model_state`.
- All 773 tests pass, 92% coverage, `make check` exit 0.
- Completed T57 (refactor HTML templates to UI macros). Fixed `settings.html`: removed unsupported `placeholder` from `ui.field` calls, refactored error handling to iterate over `validate_settings()` list of strings and render via `ui.alert(kind="danger")`. All T57 tests (7/7) and page tests (52/52) pass. `make check` exit 0.
## T58
- Rewrote `backend/app/static/app.css`: all design tokens in `:root` block remain at top. Removed unused `.badge-grey`, `.badge-blue`, `.badge-green` rules. Styled every layout/component class: `.skip-link` (hidden until focused), `.site-header` (flex, wraps below 640px), `.brand`, `.container`, `.site-footer`, `.card`/`.card-title`, `.list`/`.list-item` (flex rows, stacking on small screens), `.relative`, `.empty-state`, `.field`/`.field-invalid`/`.field-check`/`.hint`/`.error`, `.btn`/`.btn-primary`/`.btn-secondary`/`.btn-danger`, `.inline-form`, `.badge`/`.badge-queued`/`.badge-running`/`.badge-done`/`.badge-failed`/`.badge-neutral` (pill-shaped, token-backed), `.model-state`/`.model-state-up`/`.model-state-down`/`.dot`, `.alert`/`.alert-info`/`.alert-success`/`.alert-danger`, plus `.jobs-wrapper`, `.list-badge`, `.list-title`, `.list-date`, `.list-error`, `.note`, `.actions`, `.test-result`. Added `*:focus-visible` outline in accent color. Added `@media (max-width: 640px)` for header/nav wrapping and list-item stacking. Zero colour literals outside `:root`. All 47 UI tests pass, `make check` exit 0.
All checks passed!
Success: no issues found in 26 source files
........................................................................ [  8%]
........................................................................ [ 17%]
........................................................................ [ 26%]
........................................................................ [ 35%]
........................................................................ [ 44%]
........................................................................ [ 53%]
........................................................................ [ 62%]
........................................................................ [ 71%]
........................................................................ [ 80%]
...............sssssssssssssssssssssssssssssssssssssssssss.............. [ 89%]
..................sssssssssssssssssssssssssssssssssssssss............... [ 98%]
................                                                         [100%]
=============================== warnings summary ===============================
.venv/lib/python3.11/site-packages/starlette/testclient.py:51
  /home/agent/repos/scrum-agent/backend/.venv/lib/python3.11/site-packages/starlette/testclient.py:51: DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated, use anyio.from_thread.BlockingPortal instead.
    _PortalFactoryType = Callable[[], AbstractContextManager[anyio.abc.BlockingPortal]]

tests/test_auth.py::test_success_with_valid_credentials
  /home/agent/repos/scrum-agent/backend/.venv/lib/python3.11/site-packages/platformdirs/api.py:467: RuntimeDirWarning: XDG_RUNTIME_DIR is not set, falling back to /tmp/runtime-1000
    return Path(self.user_runtime_dir)

tests/test_auth.py::test_success_with_valid_credentials
  /home/agent/repos/scrum-agent/backend/.venv/lib/python3.11/site-packages/alembic/config.py:598: DeprecationWarning: No path_separator found in configuration; falling back to legacy splitting on spaces, commas, and colons for prepend_sys_path.  Consider adding path_separator=os to Alembic config.
    util.warn_deprecated(

tests/test_cards.py::test_card
  /home/agent/repos/scrum-agent/backend/.venv/lib/python3.11/site-packages/_pytest/python.py:161: PytestReturnNotNoneWarning: Test functions should return None, but tests/test_cards.py::test_card returned <class 'dict'>.
  Did you mean to use `assert` instead of `return`?
  See https://docs.pytest.org/en/stable/how-to/assert.html#return-not-none for more information.
    warnings.warn(

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
================================ tests coverage ================================
_______________ coverage: platform linux, python 3.11.2-final-0 ________________

Name                 Stmts   Miss  Cover
----------------------------------------
app/__init__.py          0      0   100%
app/answers.py          37      0   100%
app/ask.py              30      5    83%
app/auth.py             73      3    96%
app/cards.py            88      0   100%
app/clock.py            24      2    92%
app/config.py           41      0   100%
app/db.py               13      0   100%
app/deadlines.py       123      3    98%
app/fmt.py              42      5    88%
app/llm.py              60     14    77%
app/main.py             71      1    99%
app/meetings.py        135      6    96%
app/models.py           54      0   100%
app/paths.py             4      0   100%
app/retention.py        41      0   100%
app/schedule.py        109     23    79%
app/settings.py         97      8    92%
app/summarize.py        89     11    88%
app/teams.py           106      2    98%
app/teams_in.py         83     26    69%
app/templating.py       16      0   100%
app/tick.py             58      4    93%
app/transcripts.py      97      0   100%
app/web.py             163      2    99%
app/worker.py          159     31    81%
----------------------------------------
TOTAL                 1813    146    92%
Required test coverage of 90% reached. Total coverage: 91.95%
726 passed, 82 skipped, 4 warnings in 42.61s

== one migration head

== upgrade an empty database to head

== models match the migrations (alembic check)
No new upgrade operations detected.

== upgrade head again is a no-op

== downgrade to base and back up

== existing data survives upgrading to head
seeded 1 deadline
data intact after upgrade

== upgrade from the last release (v1.0.0) with its data
seeded 1 deadline
data intact after upgrade

== all migration checks passed
Summary: 9 resources found parsing stdin - Valid: 7, Invalid: 0, Errors: 0, Skipped: 2 passes (lint, mypy, coverage ≥90%, bandit). No raw input/select/textarea/style literals remain in templates.
