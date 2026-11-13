#!/usr/bin/env bash
# Human-owned image smoke test (SPEC 9.2), run by .github/workflows/image.yml.
# The devbox has no Docker; CI is where the image is built and started.
# Needs: docker, a Postgres reachable as DB_URL from inside the container (host network).
#   IMAGE=scrum-agent:smoke DB_URL=postgresql+psycopg://u:p@127.0.0.1:5432/db bash tests/ci/smoke-image.sh
set -euo pipefail

: "${IMAGE:?set IMAGE}"
: "${DB_URL:?set DB_URL}"
NAME=scrum-agent-smoke
PASS=smoke-test-password-123

docker_run() {
  docker run --rm --network host --read-only --tmpfs /tmp --user 10001 \
    -e APP_ENV=production -e DATABASE_URL="$DB_URL" -e TEAM_PASSWORD="$PASS" "$@"
}

echo "== migrate"
docker_run "$IMAGE" alembic upgrade head

echo "== tick and worker entry points import"
docker_run "$IMAGE" python -c "import app.main"
for mod in app.tick app.worker; do
  if [ -f "backend/${mod/./\/}.py" ]; then
    docker_run "$IMAGE" python -c "import $mod"
  fi
done

echo "== start the web app"
docker_run -d --name "$NAME" "$IMAGE"
cleanup() { docker logs "$NAME" 2>&1 | tail -n 30 || true; docker stop "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

for _ in $(seq 1 30); do
  curl -fsS http://127.0.0.1:8000/healthz >/dev/null 2>&1 && break
  sleep 1
done

curl -fsS http://127.0.0.1:8000/healthz
curl -fsS http://127.0.0.1:8000/readyz
code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/)
case "$code" in
  200|302|401|404) echo "/ answered $code" ;;  # 401 once auth exists; 404 on the bare scaffold
  *) echo "/ answered $code"; exit 1 ;;
esac
echo "== image smoke test passed"
