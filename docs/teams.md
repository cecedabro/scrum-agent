# Teams posts and the reminder schedule

## The webhook
The team created a Teams **Workflows** flow "Post to a channel when a webhook request is
received". Its URL is a secret (`TEAMS_WEBHOOK_URL`, from OpenBao); treat it like a password:
never log it, show it, or put it in an error. Empty URL = dry run.

Body (Microsoft's documented format; Workflows accepts Adaptive Cards in `attachments`):
```json
{"type": "message",
 "attachments": [{"contentType": "application/vnd.microsoft.card.adaptive",
                  "contentUrl": null,
                  "content": {"$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                              "type": "AdaptiveCard", "version": "1.4", "body": [...]}}]}
```
Limits: 28 KB per message (SPEC 5.2), about 4 requests per second (post one at a time).
A successful call returns 202 with an empty body. Markdown works in `TextBlock.text`; HTML
does not.

## `cards.py` (pure, no I/O)
Each function returns the inner card (`content`); `teams.envelope(card)` wraps it.
Use only `TextBlock`, `FactSet`, `Container` and `ColumnSet`, all with `"wrap": true`.
- `test_card()` — "Testbericht van de scrum agent".
- `weekly_overview(week_start, deadlines)` — title "Deadlines deze week (week 47)", a FactSet
  with `"ma 16 nov 23:59"` → title per deadline, or "Geen deadlines deze week".
- `deadline_reminder(deadline, days)` — "Herinnering: <title> is morgen" / "over 2 dagen" /
  "vandaag", the date, time and note.
- `sprint_nudge(end_date, deadlines)` — "De sprint eindigt vrijdag 20 november", the open
  deadlines until then, and a nudge to update the board.
- `summary_card(job)` — docs/summaries.md.
Example minimal body element: `{"type": "TextBlock", "text": "...", "weight": "Bolder",
"size": "Medium", "wrap": true}`.

## `teams.py`
- `post_card(card, *, client: httpx.Client | None = None) -> PostResult` — builds the
  envelope, enforces the size cap (shorten the longest TextBlocks, then add "… (ingekort)"),
  POSTs with a 15 s timeout, returns ok / retryable / permanent plus a short error
  (status code or exception class, never the URL).
- `send_once(session, kind, ref_key, card, *, client=None) -> str` — the post log logic
  (SPEC 5.3–5.4): skip if `sent` or if `dry_run`; skip if attempts ≥ 5 or the last failure
  was permanent; otherwise post, then record. Tests inject `httpx.Client(transport=
  httpx.MockTransport(handler))`.

## The schedule (`schedule.py`, pure)
`due_posts(now_utc, settings, deadlines) -> list[DuePost(kind, ref_key, card)]`.
For each enabled reminder type, compute today's local scheduled moment
`datetime.combine(local_date, time, tzinfo=ZoneInfo(...))`, and it is due when
`scheduled <= now < scheduled + 6 h`. Do the comparison on aware datetimes, so DST is
handled by `zoneinfo` (SPEC 6.5). Also check yesterday's moment, for a window that crosses
midnight. Whether it was already sent is the post log's job, not this function's.

Sprint ends: from the stored end date `E` and length `L` weeks, the ends are `E + k·L·7`
days for any integer `k`; the next end is the smallest one ≥ today. The nudge is due on
`end − days_before` at the configured time.

## `tick.py`
`run_tick(session, now, client=None) -> TickReport`: load settings and deadlines, send every
due post with `send_once`, retry failed rows that are still within their window, apply
retention (docs/privacy.md), and log one line per post (kind, ref_key, status). `main()` =
`python -m app.tick`: exit 0 normally, 1 when the database cannot be reached.

## Settings storage (`settings.py`)
One pydantic model `ReminderSettings` with the SPEC 4.1 defaults, stored as JSON in
`app_setting` under key `reminders`. `load(session)` returns defaults when nothing is
stored; `save(session, data)` validates first and stores nothing on error.

## Questions from Teams (`@Agent`, SPEC 10)
A team owner adds an **outgoing webhook** (team ⋯ → Manage team → Apps → "Create an outgoing
webhook"), name "Agent", callback `https://scrum.cedricschippers.dev/teams/outgoing`. Teams
shows a security token once; that is `TEAMS_HMAC_SECRET` (base64). Teams then POSTs a JSON
activity for every `@Agent` message in that team's standard channels. Fields we use: `text`
only (HTML, e.g. `<at>Agent</at> wat zijn de deadlines?`). Ignore `from` (names are not
stored).

Verify before parsing:
```python
expected = base64.b64encode(hmac.new(base64.b64decode(secret), body, hashlib.sha256).digest())
ok = hmac.compare_digest(expected, header.removeprefix("HMAC ").encode())
```
`body` is the exact raw request bytes (`await request.body()`), not re-serialised JSON.

The reply must arrive within 5 s, so the route only reads the DB: quick answers
(`answers.py`, pure functions) or a queued `question` job. Reply body:
`{"type": "message", "text": "**Deadlines**\n\n- ma 16 nov 23:59 — Sprint review (morgen)"}`.
Teams renders a small Markdown subset (bold, lists, line breaks); keep replies short.

The model's answer comes later through the normal Workflows webhook (`send_once`,
`question:<id>`) as a new post in the channel, not in the thread: an outgoing webhook can
only answer synchronously.

Tests sign bodies with a test secret, e.g. `base64.b64encode(b"test-secret-32-bytes-long......")`,
and set it with `monkeypatch.setenv("TEAMS_HMAC_SECRET", ...)` + `get_settings.cache_clear()`.
