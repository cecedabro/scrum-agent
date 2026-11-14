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
- [x] T05: Base layout: `templates/base.html` (Dutch, nav per docs/frontend.md with `aria-current`, `<main>`, `<footer>`), `static/app.css`, a Jinja setup in `app/web.py` with the fmt filters registered, and `/` rendering an "Overzicht" page with an empty state. Write `tests/test_base_template.py` (nav links, `aria-current` on `/`, lang="nl", htmx loaded from /static/vendor, no inline `<script>` in any template file).
  accept: cd backend && uv run pytest tests/test_base_template.py -q

## Deadlines
- [x] T06: `Deadline` model per docs/backend.md §Data model and migration `0002_deadline`. Write `tests/test_models_deadline.py` (insert with and without time/note, `source` defaults to `manual`, timestamps set).
  accept: cd backend && uv run pytest tests/test_models_deadline.py -q
- [x] T07: Service functions in `app/deadlines.py`: a pydantic `DeadlineIn` with SPEC 3.1 validation and Dutch error messages, `create`, `update`, `delete`, `upcoming(session, today)`, `between(session, start, end)`, `past(session, today)`, sorted by date then time (no time = end of day). Write `tests/test_deadlines_service.py` (200 vs 201 chars, empty title, bad time, sorting, `between` inclusive on both ends).
  accept: cd backend && uv run pytest tests/test_deadlines_service.py -q
- [x] T08: JSON API per SPEC 3.5 (`GET`/`POST /api/v1/deadlines`, `DELETE /api/v1/deadlines/{id}`), behind auth. Write `tests/test_deadlines_api.py` (field names and formats, `include_past`, 201, 422 stores nothing, 204, 404).
  accept: cd backend && uv run pytest tests/test_deadlines_api.py -q
- [x] T09: `/deadlines` page per SPEC 3.2–3.3: upcoming list with `datum` and `relatief`, collapsed past list, add form with Post/Redirect/Get and 422 + Dutch field errors. Most of the page already exists (built in T10); what is missing is mainly 422 on invalid input and the note length check (use `DeadlineIn`'s validation and show its Dutch messages). The test `tests/test_page_deadlines.py` is ALREADY WRITTEN by a human: read it first, do not change it, make it pass. It fixes "today" by patching `app.clock.now_utc`, so the page must get today via `today_local()` without arguments.
  accept: cd backend && uv run pytest tests/test_page_deadlines.py -q
- [x] T10: Edit and delete from the page (SPEC 3.4): `GET/POST /deadlines/{id}/edit`, `POST /deadlines/{id}/delete`, 404 for unknown ids; buttons on each row. Write `tests/test_page_deadlines_edit.py`.
  accept: cd backend && uv run pytest tests/test_page_deadlines_edit.py -q

## Teams posting
- [x] T11: `app/cards.py` per docs/teams.md: `test_card`, `weekly_overview`, `deadline_reminder`, `sprint_nudge`, all returning Adaptive Card 1.4 dicts with wrapped TextBlocks and Dutch text. Write `tests/test_cards.py` (exact titles for days 0/1/2, "Geen deadlines deze week", week number, FactSet values like "ma 16 nov 23:59", the card is JSON-serialisable).
  accept: cd backend && uv run pytest tests/test_cards.py -q
- [x] T12: `PostLog` model + migration `0003_post_log`, and `app/teams.py`: `envelope`, `post_card` (SPEC 5.1–5.2: 15 s timeout, 2xx ok, 429/5xx/network retryable, other 4xx permanent, 28 KB cap with "… (ingekort)", error text without the URL). Write `tests/test_teams_post.py` with `httpx.MockTransport` (exact envelope, 202, 429, 400, timeout, a 40 KB card is cut to ≤ 28 KB, the webhook URL never appears in the error).
  accept: cd backend && uv run pytest tests/test_teams_post.py -q
- [x] T13: `send_once` per docs/teams.md (SPEC 5.3–5.4): sent once, dry run when no webhook URL, retries up to 5 attempts, no retry after a permanent failure. Write `tests/test_post_log.py`.
  accept: cd backend && uv run pytest tests/test_post_log.py -q

## Settings
- [x] T14: `AppSetting` model + migration `0004_app_setting`, and `app/settings.py` `ReminderSettings` (SPEC 4.1 defaults, 4.2 validation), `load`, `save`. Write `tests/test_settings_service.py` (defaults when empty, round trip, each invalid value rejected and nothing stored).
  accept: cd backend && uv run pytest tests/test_settings_service.py -q
- [x] T15: `/settings` page (SPEC 4): the form, 422 with Dutch errors, "Webhook ingesteld: ja/nee" (never the URL), and `POST /settings/test` sending `test_card()` through `send_once` with a unique ref_key and showing the status. Make the Teams client injectable through a dependency. Write `tests/test_page_settings.py`.
  accept: cd backend && uv run pytest tests/test_page_settings.py -q

## Reminders (no LLM)
- [x] T16: `app/schedule.py` `due_posts` for the weekly overview (SPEC 6.1, 6.2, 6.5) per docs/teams.md §schedule. Write `tests/test_schedule_weekly.py` (Monday 08:29 not due, 08:30 due, 14:29 due, 14:31 not, Tuesday not, other weekday setting, summer and winter UTC offsets, ref_key `weekly:2026-W47`, disabled → nothing).
  accept: cd backend && uv run pytest tests/test_schedule_weekly.py -q
- [x] T17: Deadline reminders in `due_posts` (SPEC 6.3). Write `tests/test_schedule_deadlines.py` (2 days, 1 day, `0` in days_before → "vandaag", a moved deadline gets a new ref_key, a deadline 3 days out is not due).
  accept: cd backend && uv run pytest tests/test_schedule_deadlines.py -q
- [x] T18: Sprint nudge in `due_posts` (SPEC 6.4). Write `tests/test_schedule_sprint.py` (end dates from an anchor in the past and in the future, length 1 and 2 weeks, days_before 1, off by default, the deadlines listed stop at the end date).
  accept: cd backend && uv run pytest tests/test_schedule_sprint.py -q
- [x] T19: `app/tick.py` `run_tick` and `main` (SPEC 6.6) per docs/teams.md §tick. Write `tests/test_tick.py` (a Monday tick posts the overview once across two ticks, Teams 500 → exit 0 and retried on the next tick, unreachable database → `main()` returns 1).
  accept: cd backend && uv run pytest tests/test_tick.py -q

## Meeting summaries
- [x] T20: `app/transcripts.py` `parse_vtt`, `as_text` (SPEC 7.2) per docs/summaries.md. Write `tests/test_transcripts_vtt.py` against `tests/fixtures/sample.vtt` (11 turns, 4 speakers, first "Sanne Bakker", the split cue joined, no `<v` or `-->` left) plus inline edge cases (no `<v>`, empty file → `TranscriptError`).
  accept: cd backend && uv run pytest tests/test_transcripts_vtt.py -q
- [x] T21: `parse_docx` (SPEC 7.2) with zipfile + defusedxml and the size guard. Write `tests/test_transcripts_docx.py` against `tests/fixtures/sample.docx` (same 11 turns as the VTT) plus a non-zip, a zip without `word/document.xml`, and an oversized entry built in `tmp_path`.
  accept: cd backend && uv run pytest tests/test_transcripts_docx.py -q
- [x] T22: `Job` and `AppState` models + migration `0005_job_app_state` per docs/backend.md. Write `tests/test_models_job.py` (defaults: `queued`, attempts 0, kind `summary`).
  accept: cd backend && uv run pytest tests/test_models_job.py -q
## Meetings (split up after the first run: the agent ran out of context on bigger tasks)
- [x] T23: `app/meetings.py` with an `APIRouter` (include it in `create_app`) and `GET /meetings` rendering `templates/meetings.html`: the upload form only (SPEC 7.1: `enctype="multipart/form-data"`, `<input type="file" name="file" accept=".vtt,.docx">`, `title`, `meeting_date`). No upload handling yet. The test file is ALREADY WRITTEN by a human: read it first, do not change it, make it pass. Only `test_form_is_shown` must pass now.
  accept: cd backend && uv run pytest tests/test_page_meetings_upload.py -q -k form_is_shown
- [x] T24: `POST /meetings` upload (SPEC 7.1) in `app/meetings.py`: check the extension (case-insensitive), read at most `MAX_UPLOAD_BYTES + 1` bytes, parse with `parse_vtt`/`parse_docx` from `app/transcripts.py` (a UTF-8 decode error or no turns = refused), default title "Vergadering " + `datum_kort(date)`, default date `today_local()`; store a `queued` `summary` job with `as_text(turns)`; 303 to `/meetings`. Refusals re-render `meetings.html` with status 422 and a Dutch `<span class="error">`. Do not open `tests/fixtures/sample.docx` (binary). The test file is ALREADY WRITTEN by a human: read it first, do not change it, make it pass.
  accept: cd backend && uv run pytest tests/test_page_meetings_upload.py -q
- [x] T25: Job list on `/meetings` (SPEC 7.3): `summary` jobs newest first, each with a link to `/meetings/{id}`, the title, `datum_kort(meeting_date)`, the Dutch status label, and the error of a failed job; never the transcript; "Nog geen vergaderingen." when empty. Put the list in its own template `templates/_jobs.html` included by `meetings.html`. The test file is ALREADY WRITTEN by a human: read it first, do not change it, make it pass. The model-state and polling tests come in T26.
  accept: cd backend && uv run pytest tests/test_page_meetings_list.py -q -k "not model and not partial and not poll"
- [ ] T26: Model state and polling on `/meetings` (SPEC 7.3, docs/frontend.md §Polling): read `app_state` `model_status`; "model bereikbaar", or "model offline (pc slaapt of is gepauzeerd), laatst gezien <datum_kort> <HH:MM local>" / "… nog nooit gezien"; `GET /meetings/partial` returns only `_jobs.html` (declare it before any `/meetings/{id}` route); the `hx-get`/`hx-trigger="every 10s"`/`hx-swap="outerHTML"` attributes only while a job is queued or running. The test file is ALREADY WRITTEN by a human: read it first, do not change it, make it pass.
  accept: cd backend && uv run pytest tests/test_page_meetings_list.py -q

## Summaries
- [ ] T27: `app/llm.py` `is_up` and `chat_json` per docs/summaries.md §LLM client (SPEC 7.5). Write `tests/test_llm.py` with MockTransport (request body has model, `chat_template_kwargs.enable_thinking == false`, `response_format.type == "json_schema"`, bearer header; 200 up / connect error down; bad JSON and wrong shape → `LlmError`).
  accept: cd backend && uv run pytest tests/test_llm.py -q
- [ ] T28: `app/summarize.py` `summarize(transcript, client) -> Summary` for a transcript that fits in one call: the Dutch system prompt, the JSON schema from SPEC 7.5 as a pydantic model, and one retry when `chat_json` raises `LlmError` for bad output (raise `SummaryError` after the second). No chunking yet. Write `tests/test_summarize.py` with a fake `chat_json` (1 call for a short transcript, the transcript is in the user message, invalid then valid = success, invalid twice = `SummaryError`).
  accept: cd backend && uv run pytest tests/test_summarize.py -q
- [ ] T29: Chunking in `summarize` (SPEC 7.6): transcripts longer than `SUMMARY_CHUNK_CHARS` are split at turn boundaries (`\n` between turns from `as_text`), each part summarised, then one merge call. Write `tests/test_summarize_chunks.py` (3× the chunk size = parts + 1 merge call, no part over the limit, no turn split, the merge call gets the partial results).
  accept: cd backend && uv run pytest tests/test_summarize_chunks.py -q
- [ ] T30: `app/worker.py` `run_once(session, now, llm_client, teams_client) -> str` per docs/summaries.md §Worker, without the model check: claim one queued job (`with_for_update(skip_locked=True)`), success → `done`, `result` stored, `transcript = None`, `finished_at`; failure → back to `queued` with `error`, at 3 attempts `failed` with a short Dutch error; no job → `"idle"`. Write `tests/test_worker.py` (each case, with `summarize` patched).
  accept: cd backend && uv run pytest tests/test_worker.py -q
- [ ] T31: Model check and recovery in the worker (SPEC 7.4, 7.7): before claiming, `llm.is_up`; store `model_status` (`{"up", "checked_at", "last_up_at"}`) in `app_state`; down → `"model_offline"` and the job stays queued; `reset_stuck(session, now)` puts jobs `running` for > 30 min back to `queued`; `main()` loop per docs/summaries.md. Write `tests/test_worker_model.py` (down → queued + status stored, up → last_up_at updated, 31 min stuck reset, 29 min not; `main` is not tested).
  accept: cd backend && uv run pytest tests/test_worker_model.py -q
- [ ] T32: `cards.summary_card(job)` per docs/summaries.md §Summary card (pure). Write `tests/test_summary_card.py` (title and date, decisions, action items with and without owner/due, empty lists left out, the closing line "Gemaakt door het lokale taalmodel; controleer de actiepunten.", JSON-serialisable).
  accept: cd backend && uv run pytest tests/test_summary_card.py -q
- [ ] T33: Auto-post (SPEC 7.8): after a job is `done`, the worker posts `summary_card` with `send_once(kind="summary", ref_key=f"summary:{id}")` when the `summary_auto_post` setting is on, and sets `posted_at` when sent. Write `tests/test_summary_autopost.py` (on → posted once and `posted_at` set; off → nothing posted; Teams failure → job still `done`, `posted_at` empty).
  accept: cd backend && uv run pytest tests/test_summary_autopost.py -q
- [ ] T34: `/meetings/{id}` detail page (SPEC 7.8): summary, decisions, action items, open questions; status text while not done; 404 for unknown ids; a "Post naar Teams" form (`POST /meetings/{id}/post`, 303 back) when the job is done and not posted. Write `tests/test_page_meeting_detail.py`.
  accept: cd backend && uv run pytest tests/test_page_meeting_detail.py -q
- [ ] T35: Optional wake (SPEC 7.9) in the worker. Write `tests/test_waker.py` (not configured → no call; configured + queued + model down → one POST with `X-Waker-Token`; a second call within 30 min → none; after 31 min → again; waker 500 does not crash).
  accept: cd backend && uv run pytest tests/test_waker.py -q

## Privacy and polish
- [ ] T36: `app/retention.py` `apply_retention(session, now)` (SPEC 8.1–8.2, docs/privacy.md table), called by `run_tick`. Write `tests/test_retention.py` (each rule one day before and after its limit; a failed job's transcript after 7 days).
  accept: cd backend && uv run pytest tests/test_retention.py -q
- [ ] T37: Delete a meeting (SPEC 8.3): `POST /meetings/{id}/delete` → 303 to `/meetings`, 404 for unknown ids, and a delete button on the detail page. Write `tests/test_meeting_delete.py`.
  accept: cd backend && uv run pytest tests/test_meeting_delete.py -q
- [ ] T38: `/privacy` page in Dutch (SPEC 8.4) with the contents of docs/privacy.md (what, where, how long, how to delete). Write `tests/test_page_privacy.py` (200 behind auth, each row of the table present, nav `aria-current`).
  accept: cd backend && uv run pytest tests/test_page_privacy.py -q
- [ ] T39: The `/` overview (docs/frontend.md): next 5 deadlines, last 3 summary jobs with status, model state. Move the empty-state text out of `base.html` into this page's own template. Write `tests/test_page_home.py`.
  accept: cd backend && uv run pytest tests/test_page_home.py -q
- [ ] T40: `backend/scripts/dev.py` for `make dev`: start pgserver in `backend/.devdb/`, migrate, seed 4 deadlines relative to today and one finished summary, set `LLM_BASE_URL` to a tiny in-process fake that returns a canned summary, and run uvicorn on :8000. Write `tests/test_dev_seed.py` for the seed function only (not the server).
  accept: cd backend && uv run pytest tests/test_dev_seed.py -q

## Delivery
- [ ] T41: `backend/scripts/next_version.py` (stdlib only) per SPEC 9.3. Write `tests/test_next_version.py` (no tags → v0.1.0, patch bump, `[minor]`, `[major]`, non-semver tags ignored).
  accept: cd backend && uv run pytest tests/test_next_version.py -q
- [ ] T42: `.github/workflows/release.yml` (SPEC 9.3): on push to main; `permissions: contents: write, packages: write`; concurrency group `release`, no cancel; a first job `uses: ./.github/workflows/migrations.yml`; then full-history checkout, `make setup && make check`, next version, `docker/login-action@v3`, `docker/setup-buildx-action@v3`, `docker/build-push-action@v6` pushing `:X.Y.Z` and `:sha-<short>`, then create and push the tag. Skip all when the message contains `[skip release]`.
  accept: uvx --from actionlint-py actionlint .github/workflows/release.yml
- [ ] T43: `deploy/` part 1: `Makefile` (validate), `kustomization.yaml`, `namespace.yaml`, `app.yaml` (web Deployment with wait-for-db and migrate initContainers, Service) exactly per docs/deployment.md.
  accept: make -C deploy validate
- [ ] T44: `deploy/` part 2: `worker.yaml`, `tick.yaml`, `postgres.yaml`, `secret.example.yaml` (REPLACE_ME values, not in the kustomization) and `deploy/README.md` (egress needs, OpenBao paths `secret/scrum-agent/app` and `secret/scrum-agent/db`).
  accept: make -C deploy validate && grep -q REPLACE_ME deploy/secret.example.yaml && grep -q 'secret/scrum-agent/app' deploy/README.md

## Questions in Teams (phase 3, SPEC 10)
- [ ] T45: `TEAMS_HMAC_SECRET: str = ""` in `Settings` plus the production check (SPEC 10.1), and `app/teams_in.py`: `verify_hmac(body: bytes, header: str | None, secret_b64: str) -> bool` and `clean_text(text: str) -> str` (SPEC 10.2). Write `tests/test_teams_in.py` (a signature computed in the test passes; wrong signature, wrong secret, missing header, no `HMAC ` prefix and bad base64 fail; `<at>Agent</at> Wat zijn de   deadlines?&nbsp;` → `Wat zijn de deadlines?`; production refuses a non-base64 secret).
  accept: cd backend && uv run pytest tests/test_teams_in.py -q
- [ ] T46: `app/answers.py`: `quick_answer(text, today, deadlines, sprint_end) -> str | None` per SPEC 10.3, pure (no DB, no clock), `None` means "ask the model". Write `tests/test_answers.py` (help, `HULP`, "wat zijn de deadlines?", "deadlines deze week" on a Monday and on a Sunday, the 10-line cap with "… en 2 meer", no deadlines, sprint on/off, a line with and without a time, "wie moet de demo doen?" → None).
  accept: cd backend && uv run pytest tests/test_answers.py -q
- [ ] T47: `POST /teams/outgoing` (SPEC 10.1–10.3) using `teams_in` and `answers`; for now an unknown question replies "Dat kan ik nog niet beantwoorden." Write `tests/test_teams_outgoing.py` (a signed help message → 200 with `{"type": "message"}`, deadlines from the DB with a patched `app.clock.now_utc`, unsigned → 401, wrong signature → 401, no secret → 503, 70 KB body → 413, works without Basic auth and with `Sec-Fetch-Site: cross-site`, other routes still need auth).
  accept: cd backend && uv run pytest tests/test_teams_outgoing.py -q
- [ ] T48: Queue model questions (SPEC 10.4): unknown questions create a `question` job; the two reply texts depending on `model_status`; the limit of 5 queued; `/meetings` lists only `summary` jobs (SPEC 10.6). Write `tests/test_question_queue.py` (job stored with the cleaned, cut text and no sender name, both replies, the 6th question is refused and not stored, a question job does not show on `/meetings`).
  accept: cd backend && uv run pytest tests/test_question_queue.py -q
- [ ] T49: The worker answers `question` jobs (SPEC 10.5): `app/ask.py` builds the Dutch prompt with the context and calls `llm.chat_json` with schema `{"answer": str}`; `cards.question_card(question, answer)`; the worker picks the handler by `job.kind` and posts with `ref_key` `question:<id>` even when auto-post is off. Write `tests/test_worker_question.py` with `httpx.MockTransport` for the model and for Teams (the prompt contains the question, a deadline title and the last summary but not a 4th older one; answer posted once; invalid JSON retried; model offline leaves it queued; summary jobs still work).
  accept: cd backend && uv run pytest tests/test_worker_question.py -q
- [ ] T50: Retention and privacy for questions (SPEC 10.6): the tick deletes `question` jobs older than 30 days; `/privacy` gets the "Vragen aan @Agent" row from docs/privacy.md. Write `tests/test_retention_questions.py` (31-day-old question deleted, 29-day-old kept, summary jobs untouched, `/privacy` mentions "Vragen aan @Agent").
  accept: cd backend && uv run pytest tests/test_retention_questions.py -q
