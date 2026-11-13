# PLAN

One task per line, smallest useful units. `accept:` exits 0 when done; the harness also runs
`make check`. Read the named doc before starting. The harness marks the boxes, not you.
Every task writes the test file its `accept:` names (in `backend/tests/`).

## Foundation
- [x] T01: Scaffold: uv project, app factory, config, /healthz, /readyz, Alembic baseline, test fixtures, Makefile, Dockerfile, CI. Done by hand.
  accept: make check
- [x] T02: `app/clock.py` (`now_utc()`, `today_local(now)`, `to_local(dt)`, `local_moment(day, hhmm)` returning an aware UTC datetime) and `app/fmt.py` with Dutch weekday/month names (no locale module), `datum(d)` → "maandag 16 november", `datum_kort(d)` → "ma 16 nov", `relatief(d, today)` → "vandaag" / "morgen" / "over 3 dagen" / "gisteren" / "3 dagen geleden". See docs/backend.md §Time. Write `tests/test_clock_fmt.py` including both 2026 DST switch days.
  accept: cd backend && uv run pytest tests/test_clock_fmt.py -q
- [x] T03: `app/auth.py`: a `require_team` dependency (SPEC 2.1, `hmac.compare_digest`) applied to every router except /healthz, /readyz and /static, and the failed-login limiter (SPEC 2.2, injectable clock, state reset per app). Add a temporary protected `GET /` returning "Scrum agent" so it can be tested; add an `auth_client` fixture to conftest. Write `tests/test_auth.py` (no credentials, wrong password, right password, 11th failure → 429, `CF-Connecting-IP` keys the limit, /healthz stays open).
  accept: cd backend && uv run pytest tests/test_auth.py -q
- [x] T04: Security middleware (SPEC 2.3, 2.4): the headers on every response, and the CSRF guard returning 403 for unsafe methods when `Sec-Fetch-Site: cross-site` or the `Origin` host differs from `Host`. Write `tests/test_security.py` (headers on /healthz and /, cross-site POST 403, same-origin POST passes the guard, missing Origin passes).
  accept: cd backend && uv run pytest tests/test_security.py -q
- [ ] T05: Base layout: `templates/base.html` (Dutch, nav per docs/frontend.md with `aria-current`, `<main>`, `<footer>`), `static/app.css`, a Jinja setup in `app/web.py` with the fmt filters registered, and `/` rendering an "Overzicht" page with an empty state. Write `tests/test_base_template.py` (nav links, `aria-current` on `/`, lang="nl", htmx loaded from /static/vendor, no inline `<script>` in any template file).
  accept: cd backend && uv run pytest tests/test_base_template.py -q

## Deadlines
- [ ] T06: `Deadline` model per docs/backend.md §Data model and migration `0002_deadline`. Write `tests/test_models_deadline.py` (insert with and without time/note, `source` defaults to `manual`, timestamps set).
  accept: cd backend && uv run pytest tests/test_models_deadline.py -q
- [ ] T07: Service functions in `app/deadlines.py`: a pydantic `DeadlineIn` with SPEC 3.1 validation and Dutch error messages, `create`, `update`, `delete`, `upcoming(session, today)`, `between(session, start, end)`, `past(session, today)`, sorted by date then time (no time = end of day). Write `tests/test_deadlines_service.py` (200 vs 201 chars, empty title, bad time, sorting, `between` inclusive on both ends).
  accept: cd backend && uv run pytest tests/test_deadlines_service.py -q
- [ ] T08: JSON API per SPEC 3.5 (`GET`/`POST /api/v1/deadlines`, `DELETE /api/v1/deadlines/{id}`), behind auth. Write `tests/test_deadlines_api.py` (field names and formats, `include_past`, 201, 422 stores nothing, 204, 404).
  accept: cd backend && uv run pytest tests/test_deadlines_api.py -q
- [ ] T09: `/deadlines` page per SPEC 3.2–3.3: upcoming list with `datum` and `relatief`, collapsed past list, add form with Post/Redirect/Get and 422 + Dutch field errors. Write `tests/test_page_deadlines.py` (empty state, order, labels for a fixed `today` via a clock override, add redirects 303 and stores, invalid → 422 and stores nothing).
  accept: cd backend && uv run pytest tests/test_page_deadlines.py -q
- [ ] T10: Edit and delete from the page (SPEC 3.4): `GET/POST /deadlines/{id}/edit`, `POST /deadlines/{id}/delete`, 404 for unknown ids; buttons on each row. Write `tests/test_page_deadlines_edit.py`.
  accept: cd backend && uv run pytest tests/test_page_deadlines_edit.py -q

## Teams posting
- [ ] T11: `app/cards.py` per docs/teams.md: `test_card`, `weekly_overview`, `deadline_reminder`, `sprint_nudge`, all returning Adaptive Card 1.4 dicts with wrapped TextBlocks and Dutch text. Write `tests/test_cards.py` (exact titles for days 0/1/2, "Geen deadlines deze week", week number, FactSet values like "ma 16 nov 23:59", the card is JSON-serialisable).
  accept: cd backend && uv run pytest tests/test_cards.py -q
- [ ] T12: `PostLog` model + migration `0003_post_log`, and `app/teams.py`: `envelope`, `post_card` (SPEC 5.1–5.2: 15 s timeout, 2xx ok, 429/5xx/network retryable, other 4xx permanent, 28 KB cap with "… (ingekort)", error text without the URL). Write `tests/test_teams_post.py` with `httpx.MockTransport` (exact envelope, 202, 429, 400, timeout, a 40 KB card is cut to ≤ 28 KB, the webhook URL never appears in the error).
  accept: cd backend && uv run pytest tests/test_teams_post.py -q
- [ ] T13: `send_once` per docs/teams.md (SPEC 5.3–5.4): sent once, dry run when no webhook URL, retries up to 5 attempts, no retry after a permanent failure. Write `tests/test_post_log.py`.
  accept: cd backend && uv run pytest tests/test_post_log.py -q

## Settings
- [ ] T14: `AppSetting` model + migration `0004_app_setting`, and `app/settings.py` `ReminderSettings` (SPEC 4.1 defaults, 4.2 validation), `load`, `save`. Write `tests/test_settings_service.py` (defaults when empty, round trip, each invalid value rejected and nothing stored).
  accept: cd backend && uv run pytest tests/test_settings_service.py -q
- [ ] T15: `/settings` page (SPEC 4): the form, 422 with Dutch errors, "Webhook ingesteld: ja/nee" (never the URL), and `POST /settings/test` sending `test_card()` through `send_once` with a unique ref_key and showing the status. Make the Teams client injectable through a dependency. Write `tests/test_page_settings.py`.
  accept: cd backend && uv run pytest tests/test_page_settings.py -q

## Reminders (no LLM)
- [ ] T16: `app/schedule.py` `due_posts` for the weekly overview (SPEC 6.1, 6.2, 6.5) per docs/teams.md §schedule. Write `tests/test_schedule_weekly.py` (Monday 08:29 not due, 08:30 due, 14:29 due, 14:31 not, Tuesday not, other weekday setting, summer and winter UTC offsets, ref_key `weekly:2026-W47`, disabled → nothing).
  accept: cd backend && uv run pytest tests/test_schedule_weekly.py -q
- [ ] T17: Deadline reminders in `due_posts` (SPEC 6.3). Write `tests/test_schedule_deadlines.py` (2 days, 1 day, `0` in days_before → "vandaag", a moved deadline gets a new ref_key, a deadline 3 days out is not due).
  accept: cd backend && uv run pytest tests/test_schedule_deadlines.py -q
- [ ] T18: Sprint nudge in `due_posts` (SPEC 6.4). Write `tests/test_schedule_sprint.py` (end dates from an anchor in the past and in the future, length 1 and 2 weeks, days_before 1, off by default, the deadlines listed stop at the end date).
  accept: cd backend && uv run pytest tests/test_schedule_sprint.py -q
- [ ] T19: `app/tick.py` `run_tick` and `main` (SPEC 6.6) per docs/teams.md §tick. Write `tests/test_tick.py` (a Monday tick posts the overview once across two ticks, Teams 500 → exit 0 and retried on the next tick, unreachable database → `main()` returns 1).
  accept: cd backend && uv run pytest tests/test_tick.py -q

## Meeting summaries
- [ ] T20: `app/transcripts.py` `parse_vtt`, `as_text` (SPEC 7.2) per docs/summaries.md. Write `tests/test_transcripts_vtt.py` against `tests/fixtures/sample.vtt` (11 turns, 4 speakers, first "Sanne Bakker", the split cue joined, no `<v` or `-->` left) plus inline edge cases (no `<v>`, empty file → `TranscriptError`).
  accept: cd backend && uv run pytest tests/test_transcripts_vtt.py -q
- [ ] T21: `parse_docx` (SPEC 7.2) with zipfile + defusedxml and the size guard. Write `tests/test_transcripts_docx.py` against `tests/fixtures/sample.docx` (same 11 turns as the VTT) plus a non-zip, a zip without `word/document.xml`, and an oversized entry built in `tmp_path`.
  accept: cd backend && uv run pytest tests/test_transcripts_docx.py -q
- [ ] T22: `Job` and `AppState` models + migration `0005_job_app_state` per docs/backend.md. Write `tests/test_models_job.py` (defaults: `queued`, attempts 0, kind `summary`).
  accept: cd backend && uv run pytest tests/test_models_job.py -q
- [ ] T23: `/meetings` upload (SPEC 7.1): form, size limit, `.vtt`/`.docx` only, 422 with Dutch errors, creates a `queued` job with the `as_text` transcript, never writes the file to disk. Write `tests/test_page_meetings_upload.py` (both samples accepted, `.txt` refused, `MAX_UPLOAD_BYTES + 1` refused, empty VTT refused, rows counted).
  accept: cd backend && uv run pytest tests/test_page_meetings_upload.py -q
- [ ] T24: Job list (SPEC 7.3): Dutch status labels, model state from `app_state`, `/meetings/partial`, polling attribute only while a job is queued or running. Write `tests/test_page_meetings_status.py`.
  accept: cd backend && uv run pytest tests/test_page_meetings_status.py -q
- [ ] T25: `app/llm.py` `is_up` and `chat_json` per docs/summaries.md §LLM client (SPEC 7.5). Write `tests/test_llm.py` with MockTransport (request body has model, `chat_template_kwargs.enable_thinking == false`, `response_format.type == "json_schema"`, bearer header; 200 up / connect error down; bad JSON and wrong shape → `LlmError`).
  accept: cd backend && uv run pytest tests/test_llm.py -q
- [ ] T26: `app/summarize.py`: Dutch prompt, one retry on invalid output, chunking and merge (SPEC 7.5–7.6). Write `tests/test_summarize.py` (short transcript = 1 call; 3× chunk size = parts + 1 merge call, no part over the limit, turns never split; invalid then valid = success; invalid twice = error).
  accept: cd backend && uv run pytest tests/test_summarize.py -q
- [ ] T27: `app/worker.py` `run_once` and `main` per docs/summaries.md §Worker (SPEC 7.4, 7.7). Write `tests/test_worker.py` (model down → job stays queued and model_status stored; success → done, transcript None; LLM error → queued with attempts 1; third failure → failed; stuck running > 30 min reset, 29 min not).
  accept: cd backend && uv run pytest tests/test_worker.py -q
- [ ] T28: `summary_card` and posting (SPEC 7.8): auto-post in the worker when the setting is on (`summary:<id>`, `posted_at`), `/meetings/{id}` detail page, `POST /meetings/{id}/post` button when off or not yet posted. Write `tests/test_summary_post.py`.
  accept: cd backend && uv run pytest tests/test_summary_post.py -q
- [ ] T29: Optional wake (SPEC 7.9) in the worker. Write `tests/test_waker.py` (not configured → no call; configured + queued + model down → one POST with `X-Waker-Token`; a second call within 30 min → none; after 31 min → again; waker 500 does not crash).
  accept: cd backend && uv run pytest tests/test_waker.py -q

## Privacy and polish
- [ ] T30: Retention in the tick and delete buttons (SPEC 8.1–8.3): `POST /meetings/{id}/delete`, cleanup function called by `run_tick`. Write `tests/test_retention.py` (each rule at its boundary day, delete removes the row, 404 for unknown).
  accept: cd backend && uv run pytest tests/test_retention.py -q
- [ ] T31: `/privacy` page in Dutch (SPEC 8.4) based on docs/privacy.md, and the `/` overview filled in (next 5 deadlines, last 3 jobs, model state). Write `tests/test_page_privacy_home.py`.
  accept: cd backend && uv run pytest tests/test_page_privacy_home.py -q
- [ ] T32: `backend/scripts/dev.py` for `make dev`: start pgserver in `backend/.devdb/`, migrate, seed 4 deadlines relative to today and one finished summary, set `LLM_BASE_URL` to a tiny in-process fake that returns a canned summary, and run uvicorn on :8000. Write `tests/test_dev_seed.py` for the seed function only (not the server).
  accept: cd backend && uv run pytest tests/test_dev_seed.py -q

## Delivery
- [ ] T33: `backend/scripts/next_version.py` (stdlib only) per SPEC 9.3. Write `tests/test_next_version.py` (no tags → v0.1.0, patch bump, `[minor]`, `[major]`, non-semver tags ignored).
  accept: cd backend && uv run pytest tests/test_next_version.py -q
- [ ] T34: `.github/workflows/release.yml` (SPEC 9.3): on push to main; `permissions: contents: write, packages: write`; concurrency group `release`, no cancel; a first job `uses: ./.github/workflows/migrations.yml`; then full-history checkout, `make setup && make check`, next version, `docker/login-action@v3`, `docker/setup-buildx-action@v3`, `docker/build-push-action@v6` pushing `:X.Y.Z` and `:sha-<short>`, then create and push the tag. Skip all when the message contains `[skip release]`.
  accept: uvx --from actionlint-py actionlint .github/workflows/release.yml
- [ ] T35: `deploy/` part 1: `Makefile` (validate), `kustomization.yaml`, `namespace.yaml`, `app.yaml` (web Deployment with wait-for-db and migrate initContainers, Service) exactly per docs/deployment.md.
  accept: make -C deploy validate
- [ ] T36: `deploy/` part 2: `worker.yaml`, `tick.yaml`, `postgres.yaml`, `secret.example.yaml` (REPLACE_ME values, not in the kustomization) and `deploy/README.md` (egress needs, OpenBao paths `secret/scrum-agent/app` and `secret/scrum-agent/db`).
  accept: make -C deploy validate && grep -q REPLACE_ME deploy/secret.example.yaml && grep -q 'secret/scrum-agent/app' deploy/README.md
