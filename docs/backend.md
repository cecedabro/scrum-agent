# Backend

FastAPI app plus two entry points that share its code: `python -m app.tick` (reminders,
retention) and `python -m app.worker` (meeting summaries). One image, three processes.

## Allowed dependencies (exact pins in `pyproject.toml`)
Runtime: fastapi, uvicorn[standard], sqlalchemy, alembic, psycopg[binary], pydantic,
pydantic-settings, jinja2, python-multipart, httpx (Teams, LLM and waker calls; tests use
`httpx.MockTransport`), defusedxml (`.docx` parsing). `tzdata` only if `zoneinfo` cannot find
Europe/Amsterdam. Dev: pytest, pytest-cov, ruff, mypy, bandit, pgserver. Nothing else
without a reason in `PROGRESS.md`. Use the stdlib for everything else (`zipfile`, `zoneinfo`,
`hmac`, `re`, `json`).

## Layout (inside `backend/app/`; split a module once it passes ~300 lines)
```
main.py        create_app(): middleware, routers, /healthz, /readyz. Nothing else.
config.py      Settings (env). Already has every env var phase 1 needs.
db.py          get_engine(), session_factory(), get_db() dependency
models.py      SQLAlchemy models (one Base)
auth.py        Basic auth dependency, failed-login limiter, CSRF guard (SPEC 2)
clock.py       now_utc(), today_local(), to_local(): the only place that reads the clock
fmt.py         Dutch dates and relative labels, also registered as Jinja filters
deadlines.py   service functions + /deadlines routes + /api/v1/deadlines
settings.py    app settings stored in the DB (SPEC 4) + /settings routes
cards.py       pure functions: data -> Adaptive Card dict (docs/teams.md)
teams.py       post_card(): envelope, size cap, httpx call; post log (SPEC 5)
schedule.py    pure: due_posts(now, settings, deadlines) -> list[DuePost] (SPEC 6)
tick.py        `python -m app.tick`: due posts, retries, retention
transcripts.py parse_vtt(), parse_docx() -> list[Turn] (docs/summaries.md)
llm.py         model health check + chat completion client
summarize.py   prompt, chunking, merge, validation
worker.py      `python -m app.worker`: the job loop
meetings.py    /meetings routes (upload, list, partial, detail, post, delete)
web.py         /, /privacy, shared template setup
templates/, static/
```
Keep route handlers thin: logic lives in functions that take a `Session` (and `now`) and
are tested directly.

## Data model (shape fixed; names of extra columns are yours)
| Table | Columns |
| --- | --- |
| `deadline` | id, title, due_date (date), due_time (time, null), note (text, null), source (str, default `manual`), external_ref (str, null), created_at, updated_at |
| `app_setting` | key (pk, str), value (JSON), updated_at |
| `post_log` | id, kind, ref_key (unique), status (`sent`/`failed`/`dry_run`), attempts, last_error (null), created_at, sent_at (null) |
| `job` | id, kind (`summary` now; others later), status (`queued`/`running`/`done`/`failed`), title, meeting_date, transcript (text, null), result (JSON, null), error (null), attempts, created_at, started_at, finished_at, posted_at |
| `app_state` | key (pk), value (JSON), updated_at — e.g. `model_status`, `last_wake` |

`job.kind` and `deadline.source` exist so phases 2–3 add rows, not tables. Timestamps are
`DateTime(timezone=True)`; build them with `clock.now_utc()`.

## Migrations
- Every model change gets a new Alembic revision in the same task (`alembic revision
  --autogenerate -m "..."`, then read and tidy it). Number them `0002_…`, `0003_…`, and set
  `revision`/`down_revision` to those short ids. Never edit an existing one.
- Additive only (new tables/columns, nullable or with a server default). `downgrade()`
  must work. `make migcheck` (part of `make check` on the devbox) proves all of it.

## Config
All env vars are already in `app/config.py` (`Settings`, read through the cached
`get_settings()`). Tests change env with `monkeypatch.setenv` and then
`get_settings.cache_clear()`. Never read `os.environ` elsewhere.

## Time
Only `clock.py` calls `datetime.now`. Everything else gets `now` as an argument or calls
`clock.now_utc()`, so tests can pass fixed moments. Local = `ZoneInfo("Europe/Amsterdam")`
(`config.TIMEZONE`).
