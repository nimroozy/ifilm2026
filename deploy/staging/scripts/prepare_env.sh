#!/usr/bin/env bash
# Generate deploy/staging/.env.staging from the example with strong secrets.
# Never commits the result. Does not print secret values.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
EXAMPLE="$ROOT/deploy/staging/.env.staging.example"
OUT="$ROOT/deploy/staging/.env.staging"
CREDS="$ROOT/deploy/staging/.env.staging.credentials"

if [[ ! -f "$EXAMPLE" ]]; then
  echo "Missing $EXAMPLE" >&2
  exit 1
fi
if [[ -f "$OUT" && "${FORCE_STAGING_ENV:-}" != "1" ]]; then
  echo "Refusing to overwrite existing $OUT (set FORCE_STAGING_ENV=1 to replace)" >&2
  exit 1
fi

rand_hex() { openssl rand -hex 32; }
# Password includes @ : / # so DATABASE_URL encoding is exercised in staging.
rand_pg_password() {
  printf 'Stg_%s@:%s/#%s' "$(openssl rand -hex 6)" "$(openssl rand -hex 4)" "$(openssl rand -hex 6)"
}
rand_password() {
  openssl rand -base64 24 | tr -d '/+=' | head -c 28
}

export PREPARE_EXAMPLE="$EXAMPLE"
export PREPARE_OUT="$OUT"
export PREPARE_CREDS="$CREDS"
export PREPARE_PG_PASS
export PREPARE_JWT
export PREPARE_PLAYBACK
export PREPARE_ADMIN_PASS
export PREPARE_SUB_PASS
export PREPARE_REDIS_PASS
export PREPARE_RADIUS_PASS
PREPARE_PG_PASS="$(rand_pg_password)"
PREPARE_JWT="$(rand_hex)"
PREPARE_PLAYBACK="$(rand_hex)"
PREPARE_ADMIN_PASS="$(rand_password)Aa1"
PREPARE_SUB_PASS="$(rand_password)Bb2"
PREPARE_REDIS_PASS="$(rand_password)"
PREPARE_RADIUS_PASS="$(rand_password)"

umask 077
python3 <<'PY'
import os
import re
from pathlib import Path

example = Path(os.environ["PREPARE_EXAMPLE"]).read_text()
text = example
text = text.replace(
    "JWT_SECRET=REPLACE_WITH_OPENSSL_RAND_HEX_32",
    "JWT_SECRET=" + os.environ["PREPARE_JWT"],
    1,
)
text = text.replace(
    "PLAYBACK_TOKEN_SECRET=REPLACE_WITH_OPENSSL_RAND_HEX_32",
    "PLAYBACK_TOKEN_SECRET=" + os.environ["PREPARE_PLAYBACK"],
    1,
)
text = text.replace(
    "POSTGRES_PASSWORD=REPLACE_WITH_STRONG_UNIQUE_PASSWORD",
    "POSTGRES_PASSWORD=" + os.environ["PREPARE_PG_PASS"],
    1,
)
text = text.replace(
    "ADMIN_BOOTSTRAP_PASSWORD=REPLACE_WITH_STRONG_ADMIN_PASSWORD_MIN_12",
    "ADMIN_BOOTSTRAP_PASSWORD=" + os.environ["PREPARE_ADMIN_PASS"],
    1,
)
text = text.replace(
    "RADIUS_SECRET=REPLACE_WITH_UNIQUE_RADIUS_PLACEHOLDER_NOT_USED_LIVE",
    "RADIUS_SECRET=" + os.environ["PREPARE_RADIUS_PASS"],
    1,
)
text = text.replace("REPLACE_STAGING_FIXTURE_PASSWORD", os.environ["PREPARE_SUB_PASS"], 1)

# Drop any hand-built URLs — entrypoint constructs them with encoding.
lines = [
    line
    for line in text.splitlines()
    if not line.startswith("DATABASE_URL=") and not line.startswith("REDIS_URL=")
]
text = "\n".join(lines) + "\n"
text = text.replace(
    "REDIS_PASSWORD=REPLACE_WITH_STRONG_REDIS_PASSWORD",
    "REDIS_PASSWORD=" + os.environ["PREPARE_REDIS_PASS"],
    1,
)
if "REPLACE_WITH_STRONG_REDIS_PASSWORD" in text:
    raise SystemExit("REDIS_PASSWORD placeholder not replaced")

out = Path(os.environ["PREPARE_OUT"])
out.write_text(text)
out.chmod(0o600)

creds = Path(os.environ["PREPARE_CREDS"])
creds.write_text(
    "ADMIN_USER=staging_admin\n"
    f"ADMIN_PASS={os.environ['PREPARE_ADMIN_PASS']}\n"
    "SUB_USER=staging_user_001\n"
    f"SUB_PASS={os.environ['PREPARE_SUB_PASS']}\n"
)
creds.chmod(0o600)
print(f"Wrote {out} (secrets not printed)")
print(f"Wrote {creds} for local smoke only (do not commit)")
PY
