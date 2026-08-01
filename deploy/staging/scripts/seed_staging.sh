#!/usr/bin/env bash
# Optional explicit staging seed (admin + encoding profiles). Never automatic.
# Fixture subscriber credentials come from RADIUS_MOCK_USERS in .env.staging.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/deploy/staging/docker-compose.staging.yml" --env-file "$ROOT/deploy/staging/.env.staging")

if [[ ! -f "$ROOT/deploy/staging/.env.staging" ]]; then
  echo "Missing deploy/staging/.env.staging" >&2
  exit 1
fi

echo "==> Explicit seed_staging (admin + encoding profiles; no demo catalog)"
"${COMPOSE[@]}" exec -T backend-api sh -c 'set -a; . /run/ifilm/runtime.env; set +a; python -m scripts.seed_staging'
echo "Seed complete."
