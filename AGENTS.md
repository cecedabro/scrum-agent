# AGENTS.md — scrum agent

Read this first, every task. It is the contract between you (the coding agent) and the
human. Then read the area doc for the task (table below) and the `SPEC.md` part it names.

You are a local model working one small task at a time with no human to ask. Prefer the
boring, explicit option. When unsure about **code**, follow the area doc. When unsure
about **look and wording**, you decide (see `docs/frontend.md`).

## What this builds
A small assistant for a student scrum team (HvA). It keeps a deadlines list on a web page,
posts reminders to the team's Microsoft Teams channel on a schedule, and turns uploaded
Teams meeting transcripts into Dutch summaries with a local LLM (`coder`, on a PC that is
often asleep). Runs on a k3s homelab; public URL behind Cloudflare with a team password.

```
browser ──Basic auth──▶ web (FastAPI) ──▶ Postgres ◀── tick (CronJob, every 10 min) ──▶ Teams webhook
                                              ▲
                                    worker ───┴──▶ llama-server `coder` on the PC (may be asleep)
```

## Repository layout (top level is fixed)
| Path | What | Doc |
| --- | --- | --- |
| `backend/app/` | FastAPI app, models, tick, worker, templates, static | `docs/backend.md`, `docs/frontend.md` |
| `backend/tests/` | Your tests | `docs/testing.md` |
| `backend/alembic/` | Migrations (never edit an old one) | `docs/backend.md` |
| `tests/` | Human-owned CI checks and sample transcripts. **Do not edit.** | — |
| `deploy/` | Draft k3s manifests | `docs/deployment.md` |
| `docs/` | Area docs. **Do not edit.** | — |
| `SPEC.md`, `PLAN.md` | Requirements and task list. **Do not edit.** | — |
| `PROGRESS.md` | You append to this after each task | — |

Area docs: `docs/backend.md` (layout, deps, models), `docs/frontend.md` (pages),
`docs/teams.md` (cards, posting, schedule), `docs/summaries.md` (transcripts, LLM, worker),
`docs/testing.md`, `docs/deployment.md`, `docs/privacy.md`.

## How you are judged (the loop)
After you stop, the harness runs the task's `accept:` command and then `make check`. The
task counts only if both exit 0; then it commits. Otherwise your work is thrown away and the
task is retried with the error. So: **run `make check` yourself before you stop.**

## Working in a small context (read this)
The model has a 48k-token context; a session that goes over it dies and the attempt fails.
- Read only the files the task names, plus what they import. Use `grep -n` to find a
  function instead of reading whole files; read long files in parts.
- Never open binary files (`tests/fixtures/sample.docx`, anything under `static/vendor/`).
- Run single test files with `uv run pytest tests/test_x.py -q -x --no-cov --tb=short`;
  run `make check` once at the end, not after every edit.
- Write big files in several small edits, not one huge write.
- When a test file for your task already exists, it was written by a human: read it first
  and make it pass; never edit it.

## Rules
- No human answers questions. Never ask "shall I continue". Pick the simplest option, do
  the task, and note the choice in `PROGRESS.md`.
- Change only what the task needs. Do not start other tasks.
- Stay inside the repo. `/tmp` and paths outside it are rejected. Scratch files go in
  `.agent/tmp/` (git-ignored).
- Never edit `tests/` (root), `docs/`, `SPEC.md`, `PLAN.md`, `AGENTS.md` or anything in
  `.agent-protected`. The harness rejects it. If a human check seems wrong, satisfy it and
  note the concern in `PROGRESS.md`.
- You write the code **and its tests** in `backend/tests/`. Weak tests count as a failed
  task (`docs/testing.md`). Never call the real Teams webhook or the real LLM in tests.
- Add a dependency only if `docs/backend.md` allows it. Pin the exact version.
- No secrets in the repo. Config from env vars (`app/config.py`). Never log a secret.
- After each task append 3–5 lines to `PROGRESS.md`: what changed, where, and what the next
  task must know (a new env var, route, table, gotcha).

## Fixed decisions (do not revisit)
- Python 3.11, FastAPI, SQLAlchemy 2.x, Alembic, Postgres, `uv`. No SQLite anywhere.
- Server-rendered Jinja2 + HTMX (vendored in `static/vendor/`). No SPA, no build step.
- Reminders never use the LLM. Only meeting summaries do, through the worker queue.
- Teams posts go only through the Workflows webhook (`app/teams.py`). No Graph, no bot.
- UTC in storage; Europe/Amsterdam for deadline dates, schedule times and display.
- All user-facing text is Dutch. Code, comments, docs and commit messages are English.

## Commands
- `make setup` — `uv sync`. `make fmt` — ruff format + fix. Run before `make check`.
- `make check` — lint, mypy, tests with coverage ≥ 90 %, bandit, JS syntax, shellcheck,
  the migration check (when `DATABASE_URL` is set), and `deploy/` validation once it exists.
- `make dev` — the site on :8000 with a throwaway Postgres and a fake LLM (for humans).
- `make tick` / `make worker` — run one tick / the worker locally.
- Offline docs are in `~/docs/` (fastapi, sqlalchemy, alembic, jinja, htmx, python). Search
  with `rg -i <term> ~/docs/<name>`; never read a whole file.
