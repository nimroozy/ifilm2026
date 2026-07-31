#!/usr/bin/env bash
# Explicit Alembic upgrade for staging. Never uses create_all. Never seeds.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/deploy/staging/docker-compose.staging.yml" --env-file "$ROOT/deploy/staging/.env.staging")

if [[ ! -f "$ROOT/deploy/staging/.env.staging" ]]; then
  echo "Missing deploy/staging/.env.staging — copy from .env.staging.example" >&2
  exit 1
fi

echo "==> Waiting for backend-api health..."
"${COMPOSE[@]}" up -d postgres redis backend-api
"${COMPOSE[@]}" exec -T backend-api python - <<'PY'
import time, urllib.request
for i in range(60):
    try:
        urllib.request.urlopen("http://127.0.0.1:8000/api/health/live", timeout=2)
        raise SystemExit(0)
    except Exception:
        time.sleep(2)
raise SystemExit("backend-api not healthy")
PY

echo "==> alembic upgrade head"
"${COMPOSE[@]}" exec -T backend-api sh -c 'set -a; . /run/ifilm/runtime.env; set +a; alembic upgrade head'
echo "==> alembic current / heads"
"${COMPOSE[@]}" exec -T backend-api sh -c 'set -a; . /run/ifilm/runtime.env; set +a; alembic current'
"${COMPOSE[@]}" exec -T backend-api sh -c 'set -a; . /run/ifilm/runtime.env; set +a; alembic heads'
echo "Migration complete. Demo seed was NOT run."
