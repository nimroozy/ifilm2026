#!/usr/bin/env bash
# Operational checks for staging compose stack.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_FILE="$ROOT/deploy/staging/.env.staging"
COMPOSE=(docker compose -f "$ROOT/deploy/staging/docker-compose.staging.yml" --env-file "$ENV_FILE")
BASE_URL="${STAGING_BASE_URL:-http://127.0.0.1:${STAGING_HTTP_PORT:-8080}}"
FAIL=0

ok() { echo "OK: $*"; }
bad() { echo "FAIL: $*"; FAIL=1; }

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — ops check limited to compose config validation"
fi

echo "==> Docker Compose config"
if "${COMPOSE[@]}" config -q; then ok "compose config"; else bad "compose config"; fi

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a
  # shellcheck source=/dev/null
  source <(grep -E '^[A-Z0-9_]+=' "$ENV_FILE" | sed 's/\r$//')
  set +a

  echo "==> Service status"
  ps_out=$("${COMPOSE[@]}" ps 2>&1 || true)
  echo "$ps_out"
  for svc in postgres redis backend-api frontend media-processing-worker publishing-worker nginx; do
    echo "$ps_out" | grep -q "$svc" && ok "$svc listed" || bad "$svc not listed"
  done

  echo "==> HTTP health via nginx"
  curl -fsS "$BASE_URL/healthz" >/dev/null && ok "healthz" || bad "healthz"
  curl -fsS "$BASE_URL/api/health/live" >/dev/null && ok "api live" || bad "api live"
  code=$(curl -s -o /tmp/ifilm_ready.json -w '%{http_code}' "$BASE_URL/api/health/ready" || true)
  echo "ready HTTP $code body=$(head -c 200 /tmp/ifilm_ready.json 2>/dev/null || true)"
  [[ "$code" == "200" ]] && ok "api ready" || bad "api ready"

  echo "==> Public media paths denied"
  for path in /media/ /packages/ /originals/; do
    c=$(curl -s -o /dev/null -w '%{http_code}' "$BASE_URL$path" || true)
    [[ "$c" == "404" || "$c" == "403" ]] && ok "deny $path ($c)" || bad "deny $path ($c)"
  done

  echo "==> Alembic head"
  head=$("${COMPOSE[@]}" exec -T backend-api alembic heads 2>/dev/null | tr -d '\r' || true)
  echo "$head"
  echo "$head" | grep -Eq '010_subscriber_entitlements' && ok "alembic head" || bad "unexpected alembic head"

  echo "==> PostgreSQL connectivity"
  "${COMPOSE[@]}" exec -T postgres pg_isready -U "${POSTGRES_USER:-ifilm_staging}" -d "${POSTGRES_DB:-ifilm_staging}" \
    && ok "postgres pg_isready" || bad "postgres pg_isready"

  echo "==> DATABASE_URL special-char encoding + connect"
  "${COMPOSE[@]}" exec -T backend-api python - <<'PY' && ok "database url encode+connect" || bad "database url encode+connect"
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from app.core.db_url import build_postgres_sqlalchemy_url, validate_database_url

password = os.environ["POSTGRES_PASSWORD"]
assert any(ch in password for ch in "@:/#"), "POSTGRES_PASSWORD must include @:/# for staging"
url = os.environ["DATABASE_URL"]
validate_database_url(url)
built = build_postgres_sqlalchemy_url(
    user=os.environ["POSTGRES_USER"],
    password=password,
    host=os.environ.get("POSTGRES_HOST", "postgres"),
    port=int(os.environ.get("POSTGRES_PORT", "5432")),
    database=os.environ["POSTGRES_DB"],
)
pa, pb = make_url(url), make_url(built)
assert (pa.username, pa.password, pa.host, pa.database, int(pa.port or 5432)) == (
    pb.username, pb.password, pb.host, pb.database, int(pb.port or 5432)
)
assert pa.password == password
engine = create_engine(url, pool_pre_ping=True)
with engine.connect() as conn:
    assert conn.execute(text("SELECT 1")).scalar_one() == 1
engine.dispose()
print("connected with encoded DATABASE_URL")
PY

  echo "==> Redis connectivity"
  "${COMPOSE[@]}" exec -T redis sh -c 'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli ping' | grep -q PONG \
    && ok "redis ping" || bad "redis ping"
  "${COMPOSE[@]}" exec -T backend-api python -c "import redis,os; redis.from_url(os.environ['REDIS_URL']).ping()" \
    && ok "api redis url ping" || bad "api redis url ping"

  echo "==> FFmpeg / ffprobe on media worker"
  "${COMPOSE[@]}" exec -T media-processing-worker sh -c 'command -v ffmpeg && command -v ffprobe' \
    && ok "ffmpeg/ffprobe" || bad "ffmpeg/ffprobe"

  echo "==> Writable media directories + mount policy"
  "${COMPOSE[@]}" exec -T backend-api sh -c 'test -w /data/media/originals && test -w /data/media/temp && test -w /data/artwork' \
    && ok "api originals/temp/artwork writable" || bad "api originals/temp/artwork writable"
  "${COMPOSE[@]}" exec -T media-processing-worker sh -c 'test -w /data/media/packages && test -w /data/media/temp' \
    && ok "worker packages+temp writable" || bad "worker packages+temp writable"
  "${COMPOSE[@]}" exec -T backend-api sh -c 'test ! -w /data/media/packages' \
    && ok "api packages read-only" || bad "api packages read-only"
  "${COMPOSE[@]}" exec -T media-processing-worker sh -c 'test ! -w /data/media/originals' \
    && ok "worker originals read-only" || bad "worker originals read-only"

  echo "==> Disk space (host view)"
  df -h | head -20 || true

  echo "==> Worker processes alive"
  echo "$ps_out" | grep -E 'media-processing-worker' | grep -qiE 'running|up' \
    && ok "media-processing-worker running" || bad "media-processing-worker not running"
  echo "$ps_out" | grep -E 'publishing-worker' | grep -qiE 'running|up' \
    && ok "publishing-worker running" || bad "publishing-worker not running"

  echo "==> Radius safety flags"
  "${COMPOSE[@]}" exec -T backend-api python - <<'PY' && ok "radius safety" || bad "radius safety"
import os
assert os.environ.get("RADIUS_ENTITLEMENT_MAPPING_ENABLED","").lower() in {"0","false","no",""}
assert os.environ.get("RADIUS_ENABLED","").lower() in {"0","false","no",""}
assert os.environ.get("SUBSCRIBER_IDENTITY_MODE") == "fixture"
assert os.environ.get("APP_ENV") == "staging"
assert os.environ.get("STAGING_ALLOW_FIXTURE_AUTH","").lower() in {"1","true","yes"}
print("fixture staging-only; live radius mapping disabled")
PY
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "ops_check: FAILED"
  exit 1
fi
echo "ops_check: PASSED"
