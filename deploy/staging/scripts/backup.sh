#!/usr/bin/env bash
# Simplify: archive named docker volumes by project prefix.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ENV_FILE="$ROOT/deploy/staging/.env.staging"
COMPOSE=(docker compose -f "$ROOT/deploy/staging/docker-compose.staging.yml" --env-file "$ENV_FILE")

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${BACKUP_DIR:-$ROOT/deploy/staging/backups}/$STAMP"
mkdir -p "$OUT"
umask 077

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
# shellcheck source=/dev/null
source <(grep -E '^(POSTGRES_|[A-Z0-9_]+=)' "$ENV_FILE" | sed 's/\r$//')
set +a

echo "==> PostgreSQL dump"
"${COMPOSE[@]}" exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc >"$OUT/postgres.dump"

archive_volume() {
  local name_regex=$1 out_name=$2
  local vol
  vol=$(docker volume ls -q | grep -E "$name_regex" | head -1 || true)
  if [[ -z "$vol" ]]; then
    echo "WARN: volume matching /$name_regex/ not found" >&2
    return 0
  fi
  echo "==> Archive volume $vol -> $out_name"
  docker run --rm -v "$vol:/data:ro" -v "$OUT:/out" alpine:3.20 \
    sh -c "tar czf /out/$out_name -C /data ."
}

archive_volume 'staging_media_originals' media_originals.tar.gz
archive_volume 'staging_media_packages' media_packages.tar.gz

cp "$ENV_FILE" "$OUT/env.staging.full"
sed -E \
  -e 's/(PASSWORD|SECRET|TOKEN)=.*/\1=REDACTED/' \
  -e 's/(RADIUS_MOCK_USERS)=.*/\1=REDACTED/' \
  "$ENV_FILE" >"$OUT/env.staging.redacted"
chmod 600 "$OUT/env.staging.full"

cat >"$OUT/MANIFEST.txt" <<EOF
backup_utc=$STAMP
postgres=postgres.dump
originals=media_originals.tar.gz
packages=media_packages.tar.gz
env_full=env.staging.full
env_redacted=env.staging.redacted
EOF

echo "Backup written to $OUT"
