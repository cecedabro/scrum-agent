# SPEC (human-owned — do not edit)

Phase 1 of the scrum agent: a small self-hosted assistant for one student scrum team.
It keeps a deadlines list, posts reminders to the team's Microsoft Teams channel on a
schedule (no LLM), and turns uploaded meeting transcripts into summaries with the local
model `coder`. Requirements are testable sentences; `PLAN.md` maps tasks to them.

Words: **local** time is Europe/Amsterdam. **Post** = an Adaptive Card sent to the Teams
Workflows webhook. Stored timestamps are UTC (`timestamptz`); deadline dates and schedule
times are local calendar values. All user-facing text (pages and posts) is **Dutch**.

## 1. Skeleton and config (done by hand in T01)
- 1.1 `make check` passes: ruff, mypy (strict), pytest with ≥ 90 % coverage, bandit.
- 1.2 `GET /healthz` returns 200 `{"status": "ok"}` and never touches the database.
- 1.3 Config comes from env vars (`app/config.py`) with defaults that work for tests.
- 1.4 With `APP_ENV=production` the app refuses to start when `TEAM_PASSWORD` is the
      development default or shorter than 12 characters, or `TEAMS_WEBHOOK_URL` is set but
      not `https://`.
- 1.5 `GET /readyz` returns 200 `{"status": "ready"}` when `SELECT 1` works, else 503
      `{"status": "unavailable"}`.

## 2. Access and security
- 2.1 Every route except `/healthz`, `/readyz`, `/static/*` and `/teams/outgoing` (HMAC instead,
      SPEC 10.1) requires HTTP Basic auth with
      `TEAM_USER` / `TEAM_PASSWORD`; missing or wrong credentials → 401 with
      `WWW-Authenticate: Basic realm="scrum-agent"`. Compared with `hmac.compare_digest`.
- 2.2 More than 10 failed logins in 5 minutes from one client → 429 for that client until
      the window passes. The client is `CF-Connecting-IP` when present, else the peer address.
- 2.3 A `POST`, `PUT`, `PATCH` or `DELETE` whose `Sec-Fetch-Site` is `cross-site`, or whose
      `Origin` host differs from the `Host` header, → 403 (CSRF guard; Basic auth alone is
      replayed by browsers).
- 2.4 Every response sends `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`,
      `X-Frame-Options: DENY` and `Content-Security-Policy: default-src 'self'`. Pages use no
      inline scripts or inline event handlers.
- 2.5 Secrets (`TEAM_PASSWORD`, `TEAMS_WEBHOOK_URL`, `LLM_API_KEY`, `WAKER_TOKEN`,
      `TEAMS_HMAC_SECRET`) never
      appear in logs, pages, error messages or the post log.

## 3. Deadlines
- 3.1 A deadline has a title (1–200 chars), a local `due_date`, an optional local `due_time`
      (HH:MM), an optional note (≤ 1000 chars), `source` (`manual` now; `github` in phase 2),
      an optional `external_ref`, and created/updated timestamps.
- 3.2 `/deadlines` lists upcoming deadlines (today and later) sorted by date and time, with a
      Dutch date ("maandag 16 november") and a relative label ("vandaag", "morgen",
      "over 3 dagen"). Past deadlines are in a collapsed `<details>` section.
- 3.3 The page has an add form (title, date, time, note). Invalid input re-renders the form
      with a Dutch error next to the field and status 422; nothing is stored.
- 3.4 Each deadline can be edited and deleted from the page. Forms work without JavaScript;
      HTMX may enhance them.
- 3.5 JSON API: `GET /api/v1/deadlines` (upcoming; `?include_past=true` for all) returns
      `[{"id", "title", "due_date", "due_time", "note", "source"}]` with ISO dates and
      `due_time` `"HH:MM"` or null; `POST /api/v1/deadlines` with
      `{"title", "due_date", "due_time"?, "note"?}` → 201 and the object; invalid → 422;
      `DELETE /api/v1/deadlines/{id}` → 204, unknown id → 404.

## 4. Settings
- 4.1 `/settings` shows and saves (stored in the database, not env):
  weekly overview on/off, weekday (default maandag) and time (default 08:30);
  deadline reminders on/off, time (default 09:00) and days before (default `2,1`);
  sprint nudge on/off (default off), the end date of any one sprint, sprint length in weeks
  (1–4, default 2), days before the end (default 1) and time (default 09:00);
  summaries posted automatically on/off (default on).
- 4.2 Invalid values (bad time, weekday, days outside 0–14, length outside 1–4) → 422 with a
  Dutch error; the stored settings stay unchanged.
- 4.3 The page shows whether the webhook is configured (never the URL) and has a
  "Stuur testbericht" button that posts a test card and shows the result.

## 5. Posting to Teams
- 5.1 A post is `POST TEAMS_WEBHOOK_URL` with
  `{"type": "message", "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive",
  "contentUrl": null, "content": <AdaptiveCard version "1.4">}]}`. Any 2xx (Workflows answers
  202) is success. Timeout 15 s.
- 5.2 The JSON body is at most 28 KB; longer text is cut and ends with "… (ingekort)".
- 5.3 Every post is recorded in a post log with a `kind` and a unique `ref_key`. A post whose
  `ref_key` was already sent is never sent again. Status `sent`, `failed` (with attempts and
  a short error) or `dry_run` (no webhook configured: recorded, not sent).
- 5.4 A failed post (network error, 429, 5xx) is retried on later ticks, at most 5 attempts.
  A 4xx other than 429 is not retried.

## 6. Scheduled reminders (`python -m app.tick`, no LLM)
The tick runs every 10 minutes from a Kubernetes CronJob. It takes `now` as a parameter so
tests never sleep or depend on the real clock.
- 6.1 A reminder is due when its local scheduled moment has passed and is less than 6 hours
  ago (no old reminders after an outage) and its `ref_key` is not yet `sent`.
- 6.2 Weekly overview: on the configured weekday and time, one card listing every deadline
  from that Monday to Sunday (date, time, title), or "Geen deadlines deze week".
  `ref_key` `weekly:<ISO year>-W<week>`.
- 6.3 Deadline reminders: at the reminder time, one card per deadline whose `due_date` is N
  days after today for each configured N ("over 2 dagen", "morgen", "vandaag" for 0).
  `ref_key` `deadline:<id>:<due_date>:<N>`, so moving a deadline reminds again.
- 6.4 Sprint nudge (when on): N days before each sprint end (end date + k × length weeks),
  "De sprint eindigt <dag>", listing the deadlines up to that end date.
  `ref_key` `sprint:<end date>`.
- 6.5 Daylight-saving changes do not skip or double a reminder (08:30 local is 07:30 UTC in
  winter, 06:30 UTC in summer).
- 6.6 The tick also applies retention (section 8) and exits 0 even when Teams is down; it
  exits 1 only when the database is unreachable.

## 7. Meeting summaries
- 7.1 `/meetings` has an upload form: a transcript file (`.vtt` or `.docx`, at most
  `MAX_UPLOAD_BYTES`), an optional title and a meeting date (default today). Other types,
  too large, or no spoken text → 422 with a Dutch error; nothing stored.
- 7.2 Transcripts become a list of turns (speaker, text). For `tests/fixtures/sample.vtt`
  and `sample.docx` this gives 11 turns from 4 speakers, the first by "Sanne Bakker",
  with Teams markup (`<v>`, cue ids, timestamps) removed and a cue split over two lines
  joined into one turn. The uploaded file is parsed in memory and never written to disk.
- 7.3 An upload creates a job `queued`. `/meetings` lists jobs (title, date, status in
  Dutch: "in de wachtrij", "bezig", "klaar", "mislukt") and refreshes the list every 10 s
  through HTMX while any job is queued or running. It also shows the model state:
  "model bereikbaar" or "model offline (pc slaapt of is gepauzeerd), laatst gezien …".
- 7.4 The worker (`python -m app.worker`) checks `GET {LLM_BASE_URL}/models` (5 s timeout)
  before each job. When the model is unreachable, jobs stay queued and the worker retries
  every 60 s. It claims one job at a time with `SELECT … FOR UPDATE SKIP LOCKED`.
- 7.5 The summary comes from `POST {LLM_BASE_URL}/chat/completions` with model `LLM_MODEL`,
  a Dutch prompt, thinking off, and a JSON-schema response:
  `{"summary": str, "decisions": [str], "action_items": [{"owner": str|null, "task": str,
  "due": str|null}], "open_questions": [str]}`. Invalid JSON is retried once.
- 7.6 Transcripts longer than `SUMMARY_CHUNK_CHARS` are split at turn boundaries, each part
  summarised, then the partial results merged in one more call.
- 7.7 A job that fails 3 times is `failed` with a short Dutch error. A job `running` for more
  than 30 minutes (worker died) goes back to `queued` when a worker starts.
- 7.8 `/meetings/{id}` shows the summary, decisions, action items and open questions. When
  auto-post is on, a finished summary is posted at once (`ref_key` `summary:<job id>`);
  otherwise the page has a "Post naar Teams" button. The card ends with
  "Gemaakt door het lokale taalmodel; controleer de actiepunten."
- 7.9 Optional wake: when `WAKER_URL` and `WAKER_TOKEN` are set, a job is queued and the model
  is unreachable, the worker sends `POST {WAKER_URL}/wake` with header `X-Waker-Token`, at
  most once per 30 minutes.

## 8. Privacy and retention (see docs/privacy.md)
- 8.1 A job's transcript text is deleted as soon as its summary is stored; a failed job's
  transcript after 7 days.
- 8.2 Summaries are deleted after `SUMMARY_RETENTION_DAYS`, deadlines
  `DEADLINE_RETENTION_DAYS` after their date, post-log rows after `POST_LOG_RETENTION_DAYS`.
- 8.3 Each meeting job and each deadline has a delete button that removes it at once.
- 8.4 `/privacy` explains in Dutch what is stored, for how long, where, and how to delete it.

## 9. Delivery
- 9.1 CI (`.github/workflows/ci.yml`, human-owned) runs `make check` on pull requests and on
  pushes to `main` and `agent/**`.
- 9.2 The image builds from the root `Dockerfile`, runs as uid 10001 with a read-only root
  filesystem, and passes `tests/ci/smoke-image.sh` (workflow `image.yml`).
- 9.3 Every push to `main` that passes is a release `vX.Y.Z` (patch +1; `[minor]`/`[major]`
  in the commit message bump more; first `v0.1.0`; `[skip release]` skips), images
  `ghcr.io/cecedabro/scrum-agent:X.Y.Z` and `:sha-<short>`, then the git tag.
- 9.4 The human-owned migration check (`tests/ci/check-migrations.sh`) passes: one head,
  empty → head, `alembic check`, re-run no-op, down and up, and deadlines survive upgrades.
- 9.5 `deploy/` holds draft Kustomize manifests that pass `kustomize build | kubeconform
  -strict`; secrets are referenced by name only.

## 10. Questions in Teams (phase 3)
Teams **outgoing webhook** named "Agent": a channel member types `@Agent <vraag>` and Teams
POSTs the message to the app. Microsoft's rules: standard channels only, the reply must come
within 5 seconds, and the reply lands in the same thread.
- 10.1 `POST /teams/outgoing` is exempt from Basic auth (2.1) and the CSRF guard (2.3). It
  reads the raw body (at most 64 KB, else 413) and checks the header
  `Authorization: HMAC <base64>`: the HMAC-SHA256 of the raw body bytes, keyed with the
  base64-decoded `TEAMS_HMAC_SECRET`, compared with `hmac.compare_digest`. Missing, malformed
  or wrong → 401 with no detail. Empty `TEAMS_HMAC_SECRET` → 503 (feature off). In
  production a set `TEAMS_HMAC_SECRET` must be valid base64 (`ConfigError` otherwise).
- 10.2 The question is the body's `text` with every `<at>…</at>` mention and other HTML tags
  removed, HTML entities decoded, whitespace collapsed and trimmed. The reply is
  `{"type": "message", "text": "<markdown>"}` with status 200.
- 10.3 Answered at once, without the LLM, matched case-insensitively on the cleaned text:
  - empty, `help` or `hulp` → a short Dutch list of what you can ask;
  - contains `deadline` and `week` → the deadlines from today up to and including Sunday of
    this week, or "Geen deadlines meer deze week.";
  - contains `deadline` → the upcoming deadlines (today and later), at most 10, then
    "… en N meer"; none → "Er staan geen deadlines gepland.";
  - contains `sprint` → the end date of the current sprint with `relatief`, or "Er is geen
    sprint ingesteld." when the sprint nudge is off.
  Deadline lines look like `- ma 16 nov 23:59 — <title> (morgen)` (no time → no clock).
- 10.4 Anything else is a question for the model: a job with `kind = "question"`, the cleaned
  text (cut to 500 chars) in `title`, status `queued`. The immediate reply is "Ik denk even
  na; het antwoord komt zo in dit kanaal." when `app_state.model_status` says up, else "De pc
  met het taalmodel slaapt. Je vraag staat in de wachtrij; het antwoord komt in dit kanaal
  zodra hij aan is." With 5 or more question jobs `queued`, nothing is queued and the reply
  is "Er staan al 5 vragen in de wachtrij; probeer het later nog eens." The sender's name is
  not stored.
- 10.5 The worker answers question jobs like summary jobs (same queue order, attempts, model
  check and wake). The prompt is Dutch and gives the model: the question, today's date, the
  upcoming deadlines (at most 30), the sprint end date if set, and the `summary`,
  `decisions` and `action_items` of the 3 most recent finished summary jobs. JSON schema
  `{"answer": str}`. The answer is posted at once (always, regardless of auto-post) with
  `send_once(kind="question", ref_key=f"question:{id}")`; the card shows "Vraag: <question>",
  the answer, and "Antwoord van het lokale taalmodel; kan fouten bevatten."
- 10.6 `/meetings` lists only `summary` jobs. Question jobs are deleted 30 days after they
  were created (in the tick, with the other retention).

## Later phases (not now; keep the model open for them)
- Phase 2: GitHub Projects (stale issues, sprint progress) → deadlines with
  `source = "github"` and `external_ref`. Waits for the stakeholder's OK.
- Phase 3: done, see section 10.
- Phase 4: retro prompts and ideas.
