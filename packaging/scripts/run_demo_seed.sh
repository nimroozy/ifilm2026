#!/usr/bin/env bash
# Run demo seed on a production Compose host (demo/staging validation only).
# Does not enable live Radius. Does not print passwords.
set -euo pipefail

IFILM_ENV_FILE="${IFILM_ENV_FILE:-/etc/ifilm/ifilm.env}"
COMPOSE_FILE="${COMPOSE_FILE:-/opt/ifilm/current/packaging/compose/docker-compose.production.yml}"
COMPOSE_DIR="$(dirname "$COMPOSE_FILE")"
HOST_CRED_FILE="${HOST_CRED_FILE:-/root/ifilm-demo-credentials.txt}"
CONTAINER_CRED_FILE="${CONTAINER_CRED_FILE:-/data/artwork/.demo/credentials.txt}"
PUBLIC_BASE_URL="${DEMO_PUBLIC_BASE_URL:-https://ifilm.af}"

if [[ ! -f "$IFILM_ENV_FILE" ]]; then
  echo "Missing env file: $IFILM_ENV_FILE" >&2
  exit 1
fi
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing compose file: $COMPOSE_FILE" >&2
  exit 1
fi

cd "$COMPOSE_DIR"

echo "==> Preflight: postgres / api / media worker"
docker compose --env-file "$IFILM_ENV_FILE" -f "$COMPOSE_FILE" ps
docker compose --env-file "$IFILM_ENV_FILE" -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose --env-file "$IFILM_ENV_FILE" -f "$COMPOSE_FILE" exec -T backend-api \
  sh -c 'set -a; . /run/ifilm/runtime.env; set +a; curl -fsS http://127.0.0.1:8000/api/health/ready >/dev/null'

echo "==> Ensure migrations at head"
docker compose --env-file "$IFILM_ENV_FILE" -f "$COMPOSE_FILE" exec -T backend-api \
  sh -c 'set -a; . /run/ifilm/runtime.env; set +a; alembic upgrade head'

echo "==> Ensure demo identity flags (non-secret) without rewriting existing secrets"
# Append only missing keys; never overwrite JWT/DB/Radius secrets.
ensure_env_key() {
  local key="$1"
  local value="$2"
  if grep -qE "^${key}=" "$IFILM_ENV_FILE"; then
    # Update in place only for demo-related keys.
    case "$key" in
      DEMO_ALLOW_LOCAL_AUTH|SUBSCRIBER_IDENTITY_MODE|ENABLE_UPLOADS|DEMO_PUBLIC_BASE_URL)
        sed -i "s|^${key}=.*|${key}=${value}|" "$IFILM_ENV_FILE"
        ;;
      *)
        ;;
    esac
  else
    printf '%s=%s\n' "$key" "$value" >>"$IFILM_ENV_FILE"
  fi
}
ensure_env_key DEMO_ALLOW_LOCAL_AUTH true
ensure_env_key SUBSCRIBER_IDENTITY_MODE demo
ensure_env_key ENABLE_UPLOADS true
ensure_env_key DEMO_PUBLIC_BASE_URL "$PUBLIC_BASE_URL"

echo "==> Recreate API/workers to pick up demo identity flags (images unchanged)"
docker compose --env-file "$IFILM_ENV_FILE" -f "$COMPOSE_FILE" up -d backend-api media-processing-worker publishing-worker

COMMIT_SHA="$(docker compose --env-file "$IFILM_ENV_FILE" -f "$COMPOSE_FILE" exec -T backend-api \
  sh -c 'set -a; . /run/ifilm/runtime.env 2>/dev/null || true; set +a; printf %s "${APP_COMMIT_SHA:-}"' || true)"

echo "==> Running python -m scripts.seed_demo"
docker compose --env-file "$IFILM_ENV_FILE" -f "$COMPOSE_FILE" exec -T \
  -e DEMO_SEED_ALLOW_PROD=true \
  -e DEMO_PUBLIC_BASE_URL="$PUBLIC_BASE_URL" \
  -e DEMO_SEED_COMMIT_SHA="${COMMIT_SHA}" \
  -e DEMO_CREDENTIALS_PATH="$CONTAINER_CRED_FILE" \
  backend-api \
  sh -c 'set -a; . /run/ifilm/runtime.env; set +a; python -m scripts.seed_demo --json-report'

if [[ -f /var/lib/ifilm/artwork/.demo/credentials.txt ]]; then
  install -m 600 /var/lib/ifilm/artwork/.demo/credentials.txt "$HOST_CRED_FILE"
  echo "Credentials installed at $HOST_CRED_FILE (mode 600). Passwords not printed."
else
  echo "WARNING: container credentials file not found on host artwork volume" >&2
fi

echo "Demo seed finished."
