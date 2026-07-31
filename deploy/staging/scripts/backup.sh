#!/usr/bin/env bash
# Archive PostgreSQL + media volumes + env (full + redacted). Never uploads off-host.
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

while IFS= read -r line; do
  case "$line" in
    POSTGRES_USER=*|POSTGRES_DB=*)
      export "$line"
      ;;
  esac
done < <(grep -E '^(POSTGRES_USER|POSTGRES_DB)=' "$ENV_FILE" | sed 's/\r$//')

echo "==> PostgreSQL dump"
"${COMPOSE[@]}" exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc >"$OUT/postgres.dump"
[[ -s "$OUT/postgres.dump" ]] || { echo "empty postgres.dump" >&2; exit 1; }

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
python3 - <<PY
from pathlib import Path
import re
src = Path("$ENV_FILE").read_text()
red = []
for line in src.splitlines():
    if re.match(r'^(POSTGRES_PASSWORD|JWT_SECRET|PLAYBACK_TOKEN_SECRET|ADMIN_BOOTSTRAP_PASSWORD|REDIS_PASSWORD|RADIUS_SECRET)\s*=', line):
        key = line.split("=", 1)[0]
        red.append(f"{key}=REDACTED")
    elif line.startswith("RADIUS_MOCK_USERS="):
        red.append("RADIUS_MOCK_USERS=REDACTED")
    else:
        red.append(line)
Path("$OUT/env.staging.redacted").write_text("\n".join(red) + "\n")
PY
chmod 600 "$OUT/env.staging.full" "$OUT/env.staging.redacted"

cat >"$OUT/MANIFEST.txt" <<EOF
backup_utc=$STAMP
postgres=postgres.dump
originals=media_originals.tar.gz
packages=media_packages.tar.gz
env_full=env.staging.full
env_redacted=env.staging.redacted
EOF

echo "Backup written to $OUT"
