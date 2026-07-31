#!/usr/bin/env bash
# Optional explicit staging seed (admin + fixture subscriber mirror). Never automatic.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
COMPOSE=(docker compose -f "$ROOT/deploy/staging/docker-compose.staging.yml" --env-file "$ROOT/deploy/staging/.env.staging")

if [[ ! -f "$ROOT/deploy/staging/.env.staging" ]]; then
  echo "Missing deploy/staging/.env.staging" >&2
  exit 1
fi

echo "==> Explicit seed_dev (requires ADMIN_BOOTSTRAP_PASSWORD in env file)"
"${COMPOSE[@]}" exec -T backend-api python -m scripts.seed_dev
echo "Seed complete."
