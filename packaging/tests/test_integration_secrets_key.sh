#!/usr/bin/env bash
# Installer INTEGRATION_SECRETS_KEY: valid Fernet generation without host cryptography.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export IFILM_HOME="$TMP/opt"
export IFILM_ETC="$TMP/etc"
export IFILM_VAR="$TMP/var"
export IFILM_LOG="$TMP/log"
export ENV_FILE="$IFILM_ETC/ifilm.env"
export COMPOSE_FILE="$IFILM_HOME/current/packaging/compose/docker-compose.production.yml"
mkdir -p "$IFILM_ETC" "$IFILM_VAR/postgres" "$IFILM_VAR/redis" "$IFILM_HOME/current/packaging/compose"

# Extract installer helpers through write_env (same pattern as test_install_env_reuse.sh).
sed -n '/^log()/,/^install_agent_unit()/{ /^install_agent_unit()/q; p; }' \
  "$ROOT/packaging/installer/install_release.sh" >"$TMP/helpers.sh"
# shellcheck disable=SC1091
source "$TMP/helpers.sh"

# --- no hex fallback in installer for INTEGRATION_SECRETS_KEY ---
if grep -nE 'INTEGRATION_SECRETS_KEY|generate_fernet_key|rand_hex' \
  "$ROOT/packaging/installer/install_release.sh" | grep -E 'INTEGRATION_SECRETS|generate_fernet|integration_key' \
  | grep -q 'rand_hex'; then
  echo "FAIL: INTEGRATION_SECRETS_KEY still falls back to rand_hex"
  exit 1
fi
grep -q 'generate_fernet_key' "$ROOT/packaging/installer/install_release.sh"
! grep -qE 'Fernet\.generate_key|from cryptography' "$ROOT/packaging/installer/install_release.sh" \
  || { echo "FAIL: installer still depends on host cryptography for Fernet key"; exit 1; }

# --- generate_fernet_key produces 32-byte urlsafe-base64 key ---
key1="$(generate_fernet_key)"
[[ -n "$key1" ]] || { echo "FAIL: empty key"; exit 1; }
# Must not look like hex-only (64 hex chars from rand_hex)
[[ ${#key1} -ge 40 && ${#key1} -le 48 ]] || { echo "FAIL: unexpected key length ${#key1}"; exit 1; }
decoded_len="$(printf '%s' "$key1" | tr -- '-_' '+/' | openssl base64 -d -A 2>/dev/null | wc -c | tr -d ' ')"
[[ "$decoded_len" == "32" ]] || { echo "FAIL: decoded length $decoded_len != 32"; exit 1; }

# --- accepted by cryptography.fernet.Fernet when available ---
if python3 -c 'from cryptography.fernet import Fernet' 2>/dev/null; then
  python3 - "$key1" <<'PY'
import sys
from cryptography.fernet import Fernet

key = sys.argv[1]
f = Fernet(key.encode("utf-8"))
token = f.encrypt(b"installer-key-probe")
assert f.decrypt(token) == b"installer-key-probe"
print("fernet_ok")
PY
else
  echo "WARN: host cryptography unavailable — openssl structural checks still passed"
fi

# --- works when python3 has no cryptography (PATH override) ---
mkdir -p "$TMP/bin"
cat >"$TMP/bin/python3" <<'EOF'
#!/usr/bin/env bash
echo "simulated: cryptography not installed" >&2
exit 1
EOF
chmod +x "$TMP/bin/python3"
ORIG_PATH="$PATH"
PATH="$TMP/bin:$PATH" key_no_crypto="$(generate_fernet_key)"
PATH="$ORIG_PATH"
[[ -n "$key_no_crypto" ]] || { echo "FAIL: generate_fernet_key requires python cryptography"; exit 1; }
decoded_len2="$(printf '%s' "$key_no_crypto" | tr -- '-_' '+/' | openssl base64 -d -A 2>/dev/null | wc -c | tr -d ' ')"
[[ "$decoded_len2" == "32" ]] || { echo "FAIL: key without cryptography invalid"; exit 1; }

# --- first install writes INTEGRATION_SECRETS_KEY; mode 600; never printed ---
rm -f "$ENV_FILE"
PUBLIC_DOMAIN=localhost
ADMIN_EMAIL=admin@localhost
ADMIN_USERNAME=admin
ADMIN_PASSWORD='CandidateAdminPass1!'
INSTALL_MODE=production
ENABLE_UPLOADS=true
IFILM_HTTP_PORT=8080
IFILM_APP_VERSION=1.0.1
IFILM_APP_COMMIT_SHA=deadbeef
mkdir -p "$IFILM_HOME/current"
cat >"$IFILM_HOME/current/release-manifest.json" <<'EOF'
{
  "image_digests": {
    "backend-api": "ghcr.io/nimroozy/ifilm2026/backend-api@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "frontend": "ghcr.io/nimroozy/ifilm2026/frontend@sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  }
}
EOF

write_out="$TMP/write1.out"
write_env >"$write_out" 2>"$TMP/write1.err"
got_key="$(read_env_value INTEGRATION_SECRETS_KEY)"
[[ -n "$got_key" ]] || { echo "FAIL: INTEGRATION_SECRETS_KEY missing after first install"; exit 1; }
got_len="$(printf '%s' "$got_key" | tr -- '-_' '+/' | openssl base64 -d -A 2>/dev/null | wc -c | tr -d ' ')"
[[ "$got_len" == "32" ]] || { echo "FAIL: installed key not 32 bytes"; exit 1; }
mode="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || stat -f '%OLp' "$ENV_FILE")"
[[ "$mode" == "600" ]] || { echo "FAIL: ifilm.env mode is $mode, expected 600"; exit 1; }
# Key must not appear in installer stdout/stderr logs
if grep -F "$got_key" "$write_out" "$TMP/write1.err" >/dev/null 2>&1; then
  echo "FAIL: INTEGRATION_SECRETS_KEY value was printed during install"
  exit 1
fi

# Fernet round-trip via backend helper when cryptography is available
PYBIN="python3"
if [[ -x "$ROOT/app/backend/.venv/bin/python" ]]; then
  PYBIN="$ROOT/app/backend/.venv/bin/python"
fi
if "$PYBIN" -c 'from cryptography.fernet import Fernet' 2>/dev/null; then
  export INTEGRATION_SECRETS_KEY="$got_key"
  PYTHONPATH="$ROOT/app/backend${PYTHONPATH:+:$PYTHONPATH}" "$PYBIN" - <<'PY'
from app.services.integration_secrets import decrypt_secret, encrypt_secret
import os

key = os.environ["INTEGRATION_SECRETS_KEY"]
ct = encrypt_secret(plaintext="portal-token-not-real", master_key=key)
assert b"portal-token" not in ct
assert decrypt_secret(ciphertext=ct, master_key=key) == "portal-token-not-real"
print("backend_roundtrip_ok")
PY
fi

# --- upgrade preserves existing key exactly ---
preserved="$got_key"
# Simulate upgrade: PGDATA present + existing env
echo 16 >"$IFILM_VAR/postgres/PG_VERSION"
touch "$IFILM_VAR/redis/appendonly.aof"
write_env >/dev/null 2>&1
got_key2="$(read_env_value INTEGRATION_SECRETS_KEY)"
[[ "$got_key2" == "$preserved" ]] || {
  echo "FAIL: upgrade rotated INTEGRATION_SECRETS_KEY"
  exit 1
}

echo "OK test_integration_secrets_key"
