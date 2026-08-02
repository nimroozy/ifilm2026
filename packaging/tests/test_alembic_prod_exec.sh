#!/usr/bin/env bash
# Prove manual Alembic commands work inside a production-like Compose stack
# when DATABASE_URL is NOT injected into the backend-api container env.
#
# Builds a local backend image from Dockerfile.staging, starts postgres + api
# container (entrypoint writes runtime.env; long-running sleep keeps it up),
# then runs:
#   docker compose exec backend-api alembic current|history
#   docker compose exec backend-api ifilm-alembic current|upgrade head
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
COMPOSE_FILE="$TMP/docker-compose.yml"
PROJECT="ifilm_alembic_exec_$$"
IMAGE_TAG="ifilm-alembic-prod-exec-test:local"

cleanup() {
  docker compose -p "$PROJECT" -f "$COMPOSE_FILE" down -v --remove-orphans >/dev/null 2>&1 || true
  # Entrypoint may create root-owned media dirs on the bind mount.
  chmod -R u+w "$TMP" 2>/dev/null || true
  rm -rf "$TMP" 2>/dev/null || sudo rm -rf "$TMP" 2>/dev/null || true
}
trap cleanup EXIT

# Special-char password proves URL construction (not compose interpolation) is used.
PG_PASSWORD='p@ss:/#w0rd%X'

mkdir -p "$TMP/media" "$TMP/artwork" "$TMP/run"

cat >"$COMPOSE_FILE" <<EOF
name: ${PROJECT}
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ifilm
      POSTGRES_USER: ifilm
      POSTGRES_PASSWORD: "${PG_PASSWORD}"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ifilm -d ifilm"]
      interval: 3s
      timeout: 3s
      retries: 20
  backend-api:
    image: ${IMAGE_TAG}
    # Keep container alive after entrypoint writes /run/ifilm/runtime.env.
    # Alembic does not need uvicorn for this proof.
    command: ["sleep", "infinity"]
    environment:
      POSTGRES_HOST: postgres
      POSTGRES_PORT: "5432"
      POSTGRES_DB: ifilm
      POSTGRES_USER: ifilm
      POSTGRES_PASSWORD: "${PG_PASSWORD}"
      REDIS_HOST: redis
      REDIS_PORT: "6379"
      REDIS_DB: "0"
      REDIS_PASSWORD: redis-test-secret
      APP_ENV: production
      DEBUG: "false"
      JWT_SECRET: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
      PLAYBACK_TOKEN_SECRET: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
      ENABLE_LOCAL_STREAMING: "true"
      MEDIA_ROOT: /data/media
      ARTWORK_ROOT: /data/artwork
      # Intentionally omit DATABASE_URL — production Compose contract.
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ${TMP}/media:/data/media
      - ${TMP}/artwork:/data/artwork
EOF

echo "==> Building backend image ${IMAGE_TAG}"
docker build -f "$ROOT/app/backend/Dockerfile.staging" -t "$IMAGE_TAG" "$ROOT/app/backend" >/tmp/ifilm-alembic-build.log

echo "==> Starting production-like stack (no DATABASE_URL in backend env)"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" up -d postgres backend-api

for i in $(seq 1 60); do
  if docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T backend-api \
    sh -c 'test -f /run/ifilm/runtime.env && grep -q "^DATABASE_URL=" /run/ifilm/runtime.env'; then
    break
  fi
  sleep 2
  if [[ "$i" -eq 60 ]]; then
    echo "backend-api runtime.env was not written" >&2
    docker compose -p "$PROJECT" -f "$COMPOSE_FILE" logs backend-api >&2 || true
    exit 1
  fi
done

echo "==> Assert DATABASE_URL is absent from container environment"
if docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T backend-api printenv DATABASE_URL >/dev/null 2>&1; then
  echo "DATABASE_URL unexpectedly present in container env" >&2
  exit 1
fi

assert_no_secret_leak() {
  local output="$1"
  if grep -Fq "$PG_PASSWORD" <<<"$output"; then
    echo "password leaked in command output" >&2
    exit 1
  fi
  if grep -Eqi 'DATABASE_URL=postgresql' <<<"$output"; then
    echo "DATABASE_URL printed in command output" >&2
    exit 1
  fi
}

echo "==> Bare alembic history (POSTGRES_* fallback)"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T backend-api \
  alembic history >/tmp/alembic-history.txt 2>&1
assert_no_secret_leak "$(cat /tmp/alembic-history.txt)"
grep -q '012_system_update_notes' /tmp/alembic-history.txt

echo "==> Bare alembic current"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T backend-api \
  alembic current >/tmp/alembic-current.txt 2>&1
assert_no_secret_leak "$(cat /tmp/alembic-current.txt)"

echo "==> ifilm-alembic upgrade head"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T backend-api \
  ifilm-alembic upgrade head >/tmp/alembic-upgrade.txt 2>&1
assert_no_secret_leak "$(cat /tmp/alembic-upgrade.txt)"

echo "==> ifilm-alembic current (expects head)"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T backend-api \
  ifilm-alembic current >/tmp/alembic-current2.txt 2>&1
assert_no_secret_leak "$(cat /tmp/alembic-current2.txt)"
grep -q '012_system_update_notes' /tmp/alembic-current2.txt

echo "==> Bare alembic upgrade head is idempotent"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T backend-api \
  alembic upgrade head >/tmp/alembic-upgrade2.txt 2>&1
assert_no_secret_leak "$(cat /tmp/alembic-upgrade2.txt)"

echo "==> runtime.env exports DATABASE_URL without forcing APP_ENV=staging"
docker compose -p "$PROJECT" -f "$COMPOSE_FILE" exec -T backend-api \
  sh -c 'grep -q "^DATABASE_URL=" /run/ifilm/runtime.env && ! grep -q "^APP_ENV=" /run/ifilm/runtime.env && printenv APP_ENV | grep -qx production'

echo "test_alembic_prod_exec: PASSED"
