#!/bin/sh
# Staging entrypoint: build safe DB/Redis URLs, fix volume ownership, drop to non-root.
set -eu

mkdir -p \
  /data/media/originals \
  /data/media/temp \
  /data/media/packages \
  /data/media/trailers \
  /data/media/subtitles \
  /data/media/posters \
  /data/media/backdrops \
  /data/artwork \
  /run/ifilm

# Named volumes are root-owned by default. RO mounts may fail chown — ignore.
chown -R ifilm:ifilm /data/media /data/artwork 2>/dev/null || true

# Never use a developer .env baked into the image.
rm -f /app/.env

# Build DATABASE_URL / REDIS_URL from components so passwords with @ : / # % are safe.
# Persist to /run/ifilm/runtime.env so healthchecks and docker exec can source them.
python - <<'PY'
import os
from pathlib import Path

from app.core.db_url import build_postgres_sqlalchemy_url, build_redis_url, validate_database_url

user = os.environ.get("POSTGRES_USER", "").strip()
password = os.environ.get("POSTGRES_PASSWORD", "")
host = os.environ.get("POSTGRES_HOST", "postgres").strip()
port = int(os.environ.get("POSTGRES_PORT", "5432"))
database = os.environ.get("POSTGRES_DB", "").strip()
if not (user and password and database):
    raise SystemExit("POSTGRES_USER, POSTGRES_PASSWORD, and POSTGRES_DB are required")

database_url = build_postgres_sqlalchemy_url(
    user=user, password=password, host=host, port=port, database=database
)
validate_database_url(database_url)

redis_url = build_redis_url(
    host=os.environ.get("REDIS_HOST", "redis").strip(),
    port=int(os.environ.get("REDIS_PORT", "6379")),
    db=int(os.environ.get("REDIS_DB", "0")),
    password=os.environ.get("REDIS_PASSWORD") or None,
)

runtime = Path("/run/ifilm/runtime.env")
runtime.write_text(
    f"DATABASE_URL={database_url}\n"
    f"REDIS_URL={redis_url}\n"
    "APP_ENV=staging\n"
)
runtime.chmod(0o644)
print("Wrote", runtime, "(URL secrets not printed)")
PY

# shellcheck disable=SC1091
set -a
. /run/ifilm/runtime.env
set +a

exec gosu ifilm "$@"
