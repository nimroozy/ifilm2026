#!/usr/bin/env bash
# Run TMDB-backed realistic demo seed on a production Compose host.
# Requires TMDB_API_READ_TOKEN in /etc/ifilm/ifilm.env (never printed).
# Does not enable live Radius. Does not delete real catalog rows.
set -euo pipefail

IFILM_ENV_FILE="${IFILM_ENV_FILE:-/etc/ifilm/ifilm.env}"
COMPOSE_FILE="${COMPOSE_FILE:-/opt/ifilm/current/packaging/compose/docker-compose.production.yml}"
COMPOSE_DIR="$(dirname "$COMPOSE_FILE")"
HOST_CRED_FILE="${HOST_CRED_FILE:-/root/ifilm-demo-credentials.txt}"
CONTAINER_CRED_FILE="${CONTAINER_CRED_FILE:-/data/artwork/.demo/credentials.txt}"

if [[ ! -f "$IFILM_ENV_FILE" ]]; then
  echo "Missing env file: $IFILM_ENV_FILE" >&2
  exit 1
fi
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing compose file: $COMPOSE_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
# shellcheck disable=SC1090
. "$IFILM_ENV_FILE"
set +a

if [[ "${TMDB_ENABLED:-false}" != "true" && "${TMDB_ENABLED:-0}" != "1" ]]; then
  echo "TMDB_ENABLED must be true in ${IFILM_ENV_FILE}" >&2
  exit 1
fi
if [[ -z "${TMDB_API_READ_TOKEN:-}" ]]; then
  echo "TMDB_API_READ_TOKEN is missing in ${IFILM_ENV_FILE} (set the token; do not commit it)" >&2
  exit 1
fi

DEMO_PUBLIC_BASE_URL="${DEMO_PUBLIC_BASE_URL:-https://${PUBLIC_DOMAIN:-ifilm.af}}"

cd "$COMPOSE_DIR"

echo "==> Recreate API so TMDB_* from ${IFILM_ENV_FILE} are loaded into the container"
# Compose env_file is applied at create-time; editing ifilm.env alone is not enough.
export IFILM_HTTP_BIND="${IFILM_HTTP_BIND:-127.0.0.1}"
export IFILM_HTTP_PORT="${IFILM_HTTP_PORT:-8080}"
docker compose --env-file "$IFILM_ENV_FILE" -f "$COMPOSE_FILE" up -d --force-recreate backend-api
sleep 3

echo "==> Ensure migrations at head"
docker compose --env-file "$IFILM_ENV_FILE" -f "$COMPOSE_FILE" exec -T backend-api \
  sh -c 'set -a; . /run/ifilm/runtime.env; set +a; alembic upgrade head'

echo "==> Running python -m scripts.seed_real_demo"
# Pass TMDB token explicitly: /run/ifilm/runtime.env may omit TMDB_* keys.
docker compose --env-file "$IFILM_ENV_FILE" -f "$COMPOSE_FILE" exec -T \
  -e DEMO_SEED_ALLOW_PROD=true \
  -e DEMO_PUBLIC_BASE_URL="$DEMO_PUBLIC_BASE_URL" \
  -e DEMO_CREDENTIALS_PATH="$CONTAINER_CRED_FILE" \
  -e TMDB_ENABLED=true \
  -e TMDB_API_READ_TOKEN="$TMDB_API_READ_TOKEN" \
  -e TMDB_IMAGE_BASE_URL="${TMDB_IMAGE_BASE_URL:-https://image.tmdb.org/t/p/}" \
  -e TMDB_LANGUAGE="${TMDB_LANGUAGE:-en-US}" \
  -e TMDB_FALLBACK_LANGUAGE="${TMDB_FALLBACK_LANGUAGE:-en-US}" \
  backend-api \
  sh -c 'set -a; . /run/ifilm/runtime.env; set +a; python -m scripts.seed_real_demo --json-report'

if [[ -f /var/lib/ifilm/artwork/.demo/credentials.txt ]]; then
  install -m 600 /var/lib/ifilm/artwork/.demo/credentials.txt "$HOST_CRED_FILE"
  echo "Credentials installed at $HOST_CRED_FILE (mode 600). Passwords not printed."
fi

echo "Real demo seed finished."
