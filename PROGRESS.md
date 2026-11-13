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
