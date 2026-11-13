#!/usr/bin/env bash
# Human-owned migration check (SPEC 9.4). The agent may not edit tests/.
# Needs DATABASE_URL pointing at a throwaway Postgres database: this script WIPES it.
# Run from the repo root: DATABASE_URL=... bash tests/ci/check-migrations.sh
set -euo pipefail

: "${DATABASE_URL:?set DATABASE_URL to a throwaway Postgres database}"
# Use the psycopg 3 driver even when given a plain postgresql:// URL (the devbox sets one).
case "$DATABASE_URL" in
  postgresql://*) DATABASE_URL="postgresql+psycopg://${DATABASE_URL#postgresql://}" ;;
  postgres://*) DATABASE_URL="postgresql+psycopg://${DATABASE_URL#postgres://}" ;;
esac
export DATABASE_URL
ROOT=$(pwd)
HELPER="$ROOT/tests/ci/migcheck.py"
export APP_ENV=development

step() { printf '\n== %s\n' "$*"; }
# run <checkout> <cmd...>: run a command in that checkout's backend with its own deps
run() { local dir=$1; shift; (cd "$dir/backend" && uv run --frozen -q "$@"); }

step "one migration head"
heads=$(run "$ROOT" alembic heads | grep -c . || true)
if [ "$heads" -ne 1 ]; then
  echo "expected exactly 1 alembic head, found $heads (merge the branches)"; exit 1
fi

step "upgrade an empty database to head"
run "$ROOT" python "$HELPER" wipe
run "$ROOT" alembic upgrade head

step "models match the migrations (alembic check)"
run "$ROOT" alembic check

step "upgrade head again is a no-op"
run "$ROOT" alembic upgrade head

step "downgrade to base and back up"
run "$ROOT" alembic downgrade base
run "$ROOT" alembic upgrade head

step "existing data survives upgrading to head"
run "$ROOT" python "$HELPER" wipe
run "$ROOT" alembic upgrade head
run "$ROOT" python "$HELPER" seed
run "$ROOT" alembic upgrade head
run "$ROOT" python "$HELPER" verify

prev=$(git -C "$ROOT" tag -l 'v[0-9]*.[0-9]*.[0-9]*' --sort=-v:refname | head -n1)
if [ -z "$prev" ]; then
  step "no previous release tag: skipping the upgrade-from-release check"
  exit 0
fi

step "upgrade from the last release ($prev) with its data"
old=$(mktemp -d)
cleanup() { git -C "$ROOT" worktree remove --force "$old" >/dev/null 2>&1 || true; }
trap cleanup EXIT
git -C "$ROOT" worktree add -q --detach "$old" "$prev"
run "$ROOT" python "$HELPER" wipe
run "$old" alembic upgrade head
run "$old" python "$HELPER" seed
run "$ROOT" alembic upgrade head
run "$ROOT" python "$HELPER" verify

step "all migration checks passed"
