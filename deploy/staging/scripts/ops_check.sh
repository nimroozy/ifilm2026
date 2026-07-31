#!/usr/bin/env bash
# Operational checks for staging compose stack.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_FILE="$ROOT/deploy/staging/.env.staging"
COMPOSE=(docker compose -f "$ROOT/deploy/staging/docker-compose.staging.yml" --env-file "$ENV_FILE")
BASE_URL="${STAGING_BASE_URL:-http://127.0.0.1:${STAGING_HTTP_PORT:-8080}}"
FAIL=0

need() {
  if ! "$@"; then
    echo "FAIL: $*"
    FAIL=1
  else
    echo "OK: $*"
  fi
}

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — ops check limited to compose config validation"
fi

echo "==> Docker Compose config"
need "${COMPOSE[@]}" config -q

if [[ -f "$ENV_FILE" ]]; then
  echo "==> Service status"
  "${COMPOSE[@]}" ps || FAIL=1

  echo "==> HTTP health via nginx"
  need curl -fsS "$BASE_URL/healthz" >/dev/null
  need curl -fsS "$BASE_URL/api/health/live" >/dev/null
  code=$(curl -s -o /tmp/ifilm_ready.json -w '%{http_code}' "$BASE_URL/api/health/ready" || true)
  echo "ready HTTP $code body=$(head -c 200 /tmp/ifilm_ready.json 2>/dev/null || true)"
  [[ "$code" == "200" ]] || FAIL=1

  echo "==> Alembic head"
  head=$("${COMPOSE[@]}" exec -T backend-api alembic heads 2>/dev/null | tr -d '\r' || true)
  echo "$head"
  echo "$head" | grep -Eq '010_subscriber_entitlements' || { echo "FAIL: unexpected alembic head"; FAIL=1; }

  echo "==> PostgreSQL connectivity"
  need "${COMPOSE[@]}" exec -T postgres pg_isready -U "${POSTGRES_USER:-ifilm_staging}" -d "${POSTGRES_DB:-ifilm_staging}"

  echo "==> Redis connectivity"
  need "${COMPOSE[@]}" exec -T redis redis-cli ping
  need "${COMPOSE[@]}" exec -T backend-api python -c "import redis,os; redis.from_url(os.environ['REDIS_URL']).ping()"

  echo "==> FFmpeg / ffprobe on media worker"
  need "${COMPOSE[@]}" exec -T media-processing-worker sh -c 'command -v ffmpeg && command -v ffprobe'

  echo "==> Writable media directories (API originals/temp/artwork; worker packages; API packages RO)"
  need "${COMPOSE[@]}" exec -T backend-api sh -c 'test -w /data/media/originals && test -w /data/media/temp && test -w /data/artwork'
  need "${COMPOSE[@]}" exec -T media-processing-worker sh -c 'test -w /data/media/packages'
  need "${COMPOSE[@]}" exec -T backend-api sh -c 'test ! -w /data/media/packages'

  echo "==> Disk space (host view)"
  df -h | head -20 || true

  echo "==> Worker containers running"
  ps_out=$("${COMPOSE[@]}" ps 2>/dev/null || true)
  echo "$ps_out" | grep -q 'media-processing-worker' || { echo "FAIL: media-processing-worker not listed"; FAIL=1; }
  echo "$ps_out" | grep -q 'publishing-worker' || { echo "FAIL: publishing-worker not listed"; FAIL=1; }
  echo "$ps_out" | grep -q 'media-processing-worker' && echo "OK: media-processing-worker listed"
  echo "$ps_out" | grep -q 'publishing-worker' && echo "OK: publishing-worker listed"
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "ops_check: FAILED"
  exit 1
fi
echo "ops_check: PASSED"
