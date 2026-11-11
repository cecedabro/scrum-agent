SHELL := bash
.PHONY: setup fmt check run dev migrate migcheck tick worker
# `make check` MUST pass after every task. Later tasks extend it, never weaken it.

setup:
	cd backend && uv sync --frozen

fmt:
	cd backend && uv run ruff format . && uv run ruff check --fix .

check:
	cd backend && uv run ruff check . && uv run mypy app && uv run pytest -q --cov=app --cov-fail-under=90 && uv run bandit -r app -q -ll
	@for f in $(wildcard backend/app/static/*.js); do node --check $$f || exit 1; done
	@if command -v shellcheck >/dev/null; then shellcheck tests/ci/*.sh $(wildcard scripts/*.sh); fi
	@if [ -n "$${DATABASE_URL:-}" ]; then $(MAKE) -s migcheck; fi
	@if [ -f deploy/Makefile ]; then $(MAKE) -s -C deploy validate; fi

run:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

dev:
	cd backend && uv run python scripts/dev.py

migrate:
	cd backend && uv run alembic upgrade head

tick:
	cd backend && uv run python -m app.tick

worker:
	cd backend && uv run python -m app.worker

# Human-owned migration check (tests/ci/). Uses a separate, wiped database next to DATABASE_URL.
migcheck:
	@DATABASE_URL="$${DATABASE_URL%/*}/migcheck" bash tests/ci/check-migrations.sh
