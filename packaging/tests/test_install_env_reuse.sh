#!/usr/bin/env bash
# Unit checks for install_release.sh credential-reuse helpers (no Docker).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck disable=SC1091
source /dev/null

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export IFILM_HOME="$TMP/opt"
export IFILM_ETC="$TMP/etc"
export IFILM_VAR="$TMP/var"
export IFILM_LOG="$TMP/log"
export ENV_FILE="$IFILM_ETC/ifilm.env"
export COMPOSE_FILE="$IFILM_HOME/current/packaging/compose/docker-compose.production.yml"
mkdir -p "$IFILM_ETC" "$IFILM_VAR/postgres" "$IFILM_VAR/redis" "$IFILM_HOME/current/packaging/compose"

# Extract helper functions + deps from installer into a test harness.
# shellcheck disable=SC2016
sed -n '/^rand_hex()/,/^write_env()/{ /^write_env()/q; p; }' \
  "$ROOT/packaging/installer/install_release.sh" >"$TMP/helpers.sh"
# Include write_env itself through its closing brace by sourcing full file pieces.
sed -n '/^log()/,/^install_agent_unit()/{ /^install_agent_unit()/q; p; }' \
  "$ROOT/packaging/installer/install_release.sh" >"$TMP/helpers.sh"

# shellcheck disable=SC1091
source "$TMP/helpers.sh"

# --- pgdata detection ---
pgdata_initialized && { echo "expected empty pgdata"; exit 1; }
echo 16 >"$IFILM_VAR/postgres/PG_VERSION"
pgdata_initialized || { echo "expected initialized pgdata"; exit 1; }

# --- reuse password when PGDATA + env exist ---
touch "$IFILM_VAR/redis/appendonly.aof"
cat >"$ENV_FILE" <<'EOF'
POSTGRES_PASSWORD=old-db-secret-value-123456
REDIS_PASSWORD=old-redis-secret-value-1234
JWT_SECRET=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
PLAYBACK_TOKEN_SECRET=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
UPDATE_AGENT_SHARED_SECRET=cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc
EOF
chmod 600 "$ENV_FILE"

PUBLIC_DOMAIN=localhost
ADMIN_EMAIL=admin@localhost
ADMIN_USERNAME=admin
ADMIN_PASSWORD='CandidateAdminPass1!'
INSTALL_MODE=production
ENABLE_UPLOADS=true
IFILM_HTTP_PORT=8080
IFILM_APP_VERSION=1.0.1
IFILM_APP_COMMIT_SHA=deadbeef

# Minimal signed-manifest stub for apply_image_digests_from_manifest
mkdir -p "$IFILM_HOME/current"
cat >"$IFILM_HOME/current/release-manifest.json" <<'EOF'
{
  "image_digests": {
    "backend-api": "ghcr.io/nimroozy/ifilm2026/backend-api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "frontend": "ghcr.io/nimroozy/ifilm2026/frontend@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  }
}
EOF

write_env
got_pg="$(read_env_value POSTGRES_PASSWORD)"
got_redis="$(read_env_value REDIS_PASSWORD)"
got_jwt="$(read_env_value JWT_SECRET)"
[[ "$got_pg" == "old-db-secret-value-123456" ]] || { echo "postgres password not reused: $got_pg"; exit 1; }
[[ "$got_redis" == "old-redis-secret-value-1234" ]] || { echo "redis password not reused: $got_redis"; exit 1; }
[[ "$got_jwt" == "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" ]] || { echo "jwt not reused"; exit 1; }
grep -q 'backend-api@sha256:aaaaaaaa' "$ENV_FILE"

# --- missing password with initialized PGDATA must fail ---
rm -f "$ENV_FILE"
# die() exits the process; run in a subshell so the harness can continue.
if ( write_env ) 2>"$TMP/err.txt"; then
  echo "expected write_env to fail without password"
  exit 1
fi
grep -q 'existing PostgreSQL data' "$TMP/err.txt"

# --- wipe path allows fresh secrets ---
export IFILM_WIPE_DATA=1
export IFILM_DELETE_CONFIRM=DELETE-IFILM-DATA
# recreate a dummy env so wipe's compose down is skipped cleanly
mkdir -p "$(dirname "$COMPOSE_FILE")"
: >"$COMPOSE_FILE"
write_env
new_pg="$(read_env_value POSTGRES_PASSWORD)"
[[ -n "$new_pg" && "$new_pg" != "old-db-secret-value-123456" ]] || { echo "wipe did not generate new password"; exit 1; }
[[ ! -f "$IFILM_VAR/postgres/PG_VERSION" ]] || { echo "wipe left PG_VERSION"; exit 1; }

echo "OK test_install_env_reuse"
