#!/usr/bin/env bash
# Production installer executed only from a verified release package.
# Interactive wizard + Docker Compose stack under /opt/ifilm.
set -euo pipefail

IFILM_HOME="${IFILM_HOME:-/opt/ifilm}"
IFILM_ETC="${IFILM_ETC:-/etc/ifilm}"
IFILM_VAR="${IFILM_VAR:-/var/lib/ifilm}"
IFILM_LOG="${IFILM_LOG:-/var/log/ifilm}"
ENV_FILE="${IFILM_ETC}/ifilm.env"
COMPOSE_FILE="${IFILM_HOME}/current/packaging/compose/docker-compose.production.yml"
NONINTERACTIVE="${IFILM_NONINTERACTIVE:-0}"

log() { printf '[ifilm] %s\n' "$*"; }
die() { printf '[ifilm] ERROR: %s\n' "$*" >&2; exit 1; }

rand_hex() { openssl rand -hex 32; }
rand_password() { openssl rand -base64 32 | tr -d '/+=' | head -c 40; }

prompt() {
  local var="$1" msg="$2" default="${3:-}"
  if [[ "$NONINTERACTIVE" == "1" ]]; then
    printf -v "$var" '%s' "${!var:-$default}"
    return
  fi
  local reply
  if [[ -n "$default" ]]; then
    read -r -p "${msg} [${default}]: " reply || true
    printf -v "$var" '%s' "${reply:-$default}"
  else
    read -r -p "${msg}: " reply || true
    printf -v "$var" '%s' "$reply"
  fi
}

prompt_secret() {
  local var="$1" msg="$2"
  if [[ "$NONINTERACTIVE" == "1" ]]; then
    [[ -n "${!var:-}" ]] || printf -v "$var" '%s' "$(rand_password)"
    return
  fi
  local reply
  read -r -s -p "${msg}: " reply || true
  echo
  if [[ -z "$reply" ]]; then
    reply="$(rand_password)"
    log "generated ${var}"
  fi
  printf -v "$var" '%s' "$reply"
}

create_dirs() {
  mkdir -p \
    "$IFILM_ETC" \
    "$IFILM_LOG" \
    "$IFILM_VAR/postgres" \
    "$IFILM_VAR/redis" \
    "$IFILM_VAR/media/originals" \
    "$IFILM_VAR/media/packages" \
    "$IFILM_VAR/media/temp" \
    "$IFILM_VAR/media/trailers" \
    "$IFILM_VAR/media/posters" \
    "$IFILM_VAR/media/backdrops" \
    "$IFILM_VAR/media/subtitles" \
    "$IFILM_VAR/artwork" \
    "$IFILM_VAR/backups" \
    "$IFILM_HOME/agent" \
    /run/ifilm
  chmod 755 "$IFILM_ETC" "$IFILM_VAR" "$IFILM_LOG"
}

wizard() {
  PUBLIC_DOMAIN="${PUBLIC_DOMAIN:-}"
  ADMIN_EMAIL="${ADMIN_EMAIL:-}"
  ADMIN_USERNAME="${ADMIN_USERNAME:-admin}"
  ADMIN_PASSWORD="${ADMIN_PASSWORD:-}"
  INSTALL_MODE="${INSTALL_MODE:-production}"
  HTTPS_MODE="${HTTPS_MODE:-disabled}"
  ENABLE_UPLOADS="${ENABLE_UPLOADS:-true}"

  prompt PUBLIC_DOMAIN "Public domain (e.g. ifilm.example.com)" "localhost"
  prompt ADMIN_EMAIL "Administrator email" "admin@${PUBLIC_DOMAIN}"
  prompt ADMIN_USERNAME "Administrator username" "admin"
  prompt_secret ADMIN_PASSWORD "Administrator password (empty = generate)"
  prompt INSTALL_MODE "Installation mode (staging|production)" "production"
  prompt HTTPS_MODE "HTTPS mode (disabled|provided)" "disabled"
  prompt ENABLE_UPLOADS "Enable uploads (true|false)" "true"

  case "$INSTALL_MODE" in
    staging|production) ;;
    *) die "INSTALL_MODE must be staging or production" ;;
  esac
  [[ "${#ADMIN_PASSWORD}" -ge 12 ]] || die "admin password must be at least 12 characters"
}

upsert_env() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    # Replace the whole assignment; values are generated without shell metacharacters.
    sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >>"$ENV_FILE"
  fi
}

read_env_value() {
  local key="$1" file="${2:-$ENV_FILE}"
  [[ -f "$file" ]] || return 0
  # shellcheck disable=SC2162
  local line
  while IFS= read -r line || [[ -n "$line" ]]; do
    case "$line" in
      "${key}="*)
        printf '%s' "${line#"${key}"=}"
        return 0
        ;;
    esac
  done <"$file"
}

pgdata_initialized() {
  # Official postgres image initializes only when PGDATA is empty. PG_VERSION
  # is written on first boot and means the password is already fixed in-cluster.
  [[ -f "${IFILM_VAR}/postgres/PG_VERSION" ]]
}

redis_data_present() {
  [[ -f "${IFILM_VAR}/redis/appendonly.aof" || -f "${IFILM_VAR}/redis/dump.rdb" ]]
}

maybe_wipe_existing_data() {
  if [[ "${IFILM_WIPE_DATA:-0}" != "1" ]]; then
    return 0
  fi
  [[ "${IFILM_DELETE_CONFIRM:-}" == "DELETE-IFILM-DATA" ]] \
    || die "refusing data wipe: set IFILM_WIPE_DATA=1 IFILM_DELETE_CONFIRM=DELETE-IFILM-DATA"
  log "wiping existing postgres/redis data directories after typed confirmation"
  if [[ -f "$COMPOSE_FILE" && -f "$ENV_FILE" ]]; then
    docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down || true
  fi
  rm -rf "${IFILM_VAR}/postgres" "${IFILM_VAR}/redis"
  mkdir -p "${IFILM_VAR}/postgres" "${IFILM_VAR}/redis"
}

apply_image_digests_from_manifest() {
  local manifest="${IFILM_HOME}/current/release-manifest.json"
  [[ -f "$manifest" ]] || die "missing release manifest ${manifest}"
  local backend frontend
  backend="$(jq -r '.image_digests["backend-api"] // empty' "$manifest")"
  frontend="$(jq -r '.image_digests.frontend // empty' "$manifest")"
  [[ -n "$backend" && "$backend" == ghcr.io/*/backend-api@sha256:* ]] \
    || die "manifest missing immutable backend-api GHCR digest"
  [[ -n "$frontend" && "$frontend" == ghcr.io/*/frontend@sha256:* ]] \
    || die "manifest missing immutable frontend GHCR digest"
  case "$backend" in
    *:latest|*:main|*:master|*:staging) die "mutable backend image tag rejected" ;;
  esac
  case "$frontend" in
    *:latest|*:main|*:master|*:staging) die "mutable frontend image tag rejected" ;;
  esac
  upsert_env IFILM_IMAGE_BACKEND_API "$backend"
  upsert_env IFILM_IMAGE_FRONTEND "$frontend"
  log "pinned images from signed manifest"
}

write_env() {
  local pg_pass redis_pass jwt playback agent
  local reuse_db=0 reuse_redis=0
  local existing_env=""

  maybe_wipe_existing_data

  if [[ -f "$ENV_FILE" ]]; then
    existing_env="$(mktemp)"
    cp -a "$ENV_FILE" "$existing_env"
    chmod 600 "$existing_env"
  fi

  # Postgres (and Redis with requirepass) only apply credentials on first data
  # init. Reinstalls must reuse the existing passwords or wipe data explicitly.
  if pgdata_initialized; then
    pg_pass="$(read_env_value POSTGRES_PASSWORD "${existing_env:-}")"
    [[ -n "$pg_pass" ]] || die \
      "existing PostgreSQL data found at ${IFILM_VAR}/postgres but ${ENV_FILE} has no POSTGRES_PASSWORD. Restore the previous ifilm.env, or wipe data with IFILM_WIPE_DATA=1 IFILM_DELETE_CONFIRM=DELETE-IFILM-DATA and re-run install."
    reuse_db=1
    log "reusing POSTGRES_PASSWORD from existing env (initialized database present)"
  else
    pg_pass="$(rand_password)"
  fi

  if redis_data_present; then
    redis_pass="$(read_env_value REDIS_PASSWORD "${existing_env:-}")"
    [[ -n "$redis_pass" ]] || die \
      "existing Redis data found at ${IFILM_VAR}/redis but ${ENV_FILE} has no REDIS_PASSWORD. Restore the previous ifilm.env, or wipe data with IFILM_WIPE_DATA=1 IFILM_DELETE_CONFIRM=DELETE-IFILM-DATA and re-run install."
    reuse_redis=1
    log "reusing REDIS_PASSWORD from existing env (persistent Redis data present)"
  else
    redis_pass="$(rand_password)"
  fi

  # Preserve app secrets across reinstall when an env already exists so tokens
  # and agent auth keep working; generate only on first install.
  if [[ -n "${existing_env:-}" ]]; then
    jwt="$(read_env_value JWT_SECRET "$existing_env")"
    playback="$(read_env_value PLAYBACK_TOKEN_SECRET "$existing_env")"
    agent="$(read_env_value UPDATE_AGENT_SHARED_SECRET "$existing_env")"
  fi
  [[ -n "${jwt:-}" ]] || jwt="$(rand_hex)"
  [[ -n "${playback:-}" ]] || playback="$(rand_hex)"
  [[ -n "${agent:-}" ]] || agent="$(rand_hex)"

  umask 077
  cat >"$ENV_FILE" <<EOF
# Generated by iFilm installer. Do not commit.
APP_ENV=${INSTALL_MODE}
DEBUG=false
PUBLIC_DOMAIN=${PUBLIC_DOMAIN}
CORS_ORIGINS=["https://${PUBLIC_DOMAIN}","http://${PUBLIC_DOMAIN}","http://localhost","http://127.0.0.1:${IFILM_HTTP_PORT:-8080}"]
CSP_MODE=production

POSTGRES_DB=ifilm
POSTGRES_USER=ifilm
POSTGRES_PASSWORD=${pg_pass}
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=${redis_pass}
REDIS_REQUIRED=true

JWT_SECRET=${jwt}
PLAYBACK_TOKEN_SECRET=${playback}
UPDATE_AGENT_SHARED_SECRET=${agent}
UPDATE_AGENT_SOCKET=/run/ifilm/update-agent.sock
UPDATE_AGENT_SOCKET_MODE=0o666
UPDATE_CHANNEL=stable

ADMIN_BOOTSTRAP_USERNAME=${ADMIN_USERNAME}
ADMIN_BOOTSTRAP_PASSWORD=${ADMIN_PASSWORD}
ADMIN_BOOTSTRAP_EMAIL=${ADMIN_EMAIL}

MEDIA_ROOT=/data/media
ARTWORK_ROOT=/data/artwork
HLS_PUBLIC_BASE_URL=https://${PUBLIC_DOMAIN}/api/stream

ENABLE_UPLOADS=${ENABLE_UPLOADS}
ENABLE_MEDIA_PROCESSING=true
ENABLE_HLS_ENCODING=true
ENABLE_LOCAL_STREAMING=true
ENABLE_WATCH_HISTORY=true
ENABLE_CDN_SYNC=false
ENABLE_ENCODING=false
ENABLE_RADIUS_LOGIN=false

SUBSCRIBER_IDENTITY_MODE=disabled
STAGING_ALLOW_FIXTURE_AUTH=false
RADIUS_ENTITLEMENT_MAPPING_ENABLED=false
RADIUS_ENABLED=false
RADIUS_MODE=live

IFILM_VERSION_FILE=/opt/ifilm/current/release-manifest.json
MAINTENANCE_MODE=false
IFILM_HTTP_PORT=${IFILM_HTTP_PORT:-8080}
IFILM_HTTP_BIND=${IFILM_HTTP_BIND:-0.0.0.0}
HTTPS_MODE=${HTTPS_MODE:-disabled}
APP_VERSION=${IFILM_APP_VERSION:-}
APP_COMMIT_SHA=${IFILM_APP_COMMIT_SHA:-}
IFILM_IMAGE_BACKEND_API=
IFILM_IMAGE_FRONTEND=
EOF

  if [[ -n "${existing_env:-}" ]]; then
    rm -f "$existing_env"
  fi

  if [[ "$INSTALL_MODE" == "staging" ]]; then
    # Staging may later enable fixture via explicit operator edit; keep defaults safe.
    sed -i 's/^APP_ENV=.*/APP_ENV=staging/' "$ENV_FILE"
    # Disposable/test installs may consume prereleases on the staging channel.
    if [[ "${IFILM_ALLOW_PRERELEASE_CHANNEL:-0}" == "1" ]]; then
      sed -i 's/^UPDATE_CHANNEL=.*/UPDATE_CHANNEL=staging/' "$ENV_FILE"
    fi
  fi

  apply_image_digests_from_manifest

  if [[ "$(id -u)" -eq 0 ]]; then
    chown root:root "$ENV_FILE"
  fi
  chmod 600 "$ENV_FILE"
  if [[ "$reuse_db" == "1" || "$reuse_redis" == "1" ]]; then
    log "wrote ${ENV_FILE} (mode 600; preserved existing DB/Redis credentials)"
  else
    log "wrote ${ENV_FILE} (mode 600)"
  fi
}

install_agent_unit() {
  install -d -m 0755 "$IFILM_HOME/agent"
  install -m 0755 "$IFILM_HOME/current/packaging/update-agent/agent.py" "$IFILM_HOME/agent/agent.py"
  if [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null 2>&1; then
    install -d -m 0755 /etc/systemd/system
    cat >/etc/systemd/system/ifilm-update-agent.service <<'UNIT'
[Unit]
Description=iFilm update agent (privileged, typed protocol)
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/ifilm/current
EnvironmentFile=/etc/ifilm/ifilm.env
ExecStart=/usr/bin/python3 /opt/ifilm/current/packaging/update-agent/agent.py
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/opt/ifilm /var/lib/ifilm /var/log/ifilm /etc/ifilm /run/ifilm /tmp
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
    systemctl enable --now ifilm-update-agent.service
  else
    log "systemd unavailable — starting update-agent as supervised background process"
    pkill -f '/opt/ifilm/agent/agent.py' 2>/dev/null || true
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
    # Always execute the agent from the verified current release tree so
    # packaging/release helpers (image digest validation) resolve correctly.
    nohup /usr/bin/python3 "$IFILM_HOME/current/packaging/update-agent/agent.py" \
      >>"$IFILM_LOG/update-agent.log" 2>&1 &
    echo $! >"$IFILM_HOME/agent/agent.pid"
    sleep 1
    [[ -S "${UPDATE_AGENT_SOCKET:-/run/ifilm/update-agent.sock}" ]] \
      || die "update-agent socket not created"
  fi
}

verify_pulled_digest() {
  local want="$1"
  local repo digest got
  repo="${want%@*}"
  digest="${want#*@}"
  [[ "$digest" == sha256:* ]] || die "invalid digest ref ${want}"
  got="$(docker image inspect --format='{{index .RepoDigests 0}}' "$want" 2>/dev/null || true)"
  if [[ -z "$got" ]]; then
    got="$(docker image inspect --format='{{index .RepoDigests 0}}' "$repo" 2>/dev/null || true)"
  fi
  [[ "$got" == *"@${digest}" || "$got" == "$want" ]] \
    || die "pulled image digest mismatch for ${want} (got ${got:-none})"
}

start_stack() {
  [[ -f "$COMPOSE_FILE" ]] || die "missing compose file ${COMPOSE_FILE}"
  apply_image_digests_from_manifest
  # Production installs pull immutable digest refs only — never --build.
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" pull
  # shellcheck disable=SC1090,SC1091
  set -a
  # shellcheck disable=SC1090,SC1091
  . "$ENV_FILE"
  set +a
  verify_pulled_digest "${IFILM_IMAGE_BACKEND_API}"
  verify_pulled_digest "${IFILM_IMAGE_FRONTEND}"
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-build
  HTTP_PORT="${IFILM_HTTP_PORT:-8080}"
  log "waiting for backend liveness on :${HTTP_PORT}"
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:${HTTP_PORT}/api/health/live" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  curl -fsS "http://127.0.0.1:${HTTP_PORT}/api/health/live" >/dev/null \
    || die "API liveness check failed"

  # Fail fast with an actionable message if credentials do not match PGDATA.
  if ! docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T postgres \
    sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null && PGPASSWORD="$POSTGRES_PASSWORD" psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "SELECT 1" >/dev/null'; then
    die "PostgreSQL password authentication failed for user ifilm. While ${IFILM_VAR}/postgres is initialized the installer reuses POSTGRES_PASSWORD from ${ENV_FILE} and will not invent a new one. Restore the matching ifilm.env, or wipe with IFILM_WIPE_DATA=1 IFILM_DELETE_CONFIRM=DELETE-IFILM-DATA and re-run."
  fi

  # Migrations before readiness: empty databases are live but not ready until schema exists.
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T backend-api \
    ifilm-alembic upgrade head
  # Explicit admin bootstrap only — never create_all, never unsafe demo seed.
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" exec -T backend-api \
    sh -c 'set -a; . /run/ifilm/runtime.env 2>/dev/null || true; set +a; python -m scripts.seed_production_admin'

  log "waiting for backend readiness on :${HTTP_PORT}"
  for _ in $(seq 1 60); do
    if curl -fsS "http://127.0.0.1:${HTTP_PORT}/api/health/ready" >/dev/null 2>&1; then
      break
    fi
    sleep 2
  done
  curl -fsS "http://127.0.0.1:${HTTP_PORT}/api/health/ready" >/dev/null \
    || die "API readiness check failed"
}

main() {
  [[ "$(id -u)" -eq 0 ]] || die "must run as root"
  create_dirs
  wizard
  write_env
  install_agent_unit
  start_stack
  log "installation complete"
  log "admin UI: http://${PUBLIC_DOMAIN}:8080/admin (or configured HTTPS endpoint)"
  log "secrets stored in ${ENV_FILE} (not printed)"
}

main "$@"
