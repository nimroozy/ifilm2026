#!/usr/bin/env bash
# Enable host-edge Let's Encrypt HTTPS for a production iFilm install.
# Survives app updates: host nginx + /etc/letsencrypt live outside /opt/ifilm/current.
#
# Usage (as root on the VPS):
#   PUBLIC_DOMAIN=ifilm.af CERTBOT_EMAIL=ops@example.com \
#     bash /opt/ifilm/current/packaging/https/enable_https.sh
#
# Prerequisites:
#   - PUBLIC_DOMAIN A record points at this host
#   - ports 80/443 free for host nginx (compose binds 8080 on loopback after cutover)
set -euo pipefail

IFILM_ENV_FILE="${IFILM_ENV_FILE:-/etc/ifilm/ifilm.env}"
COMPOSE_FILE="${COMPOSE_FILE:-/opt/ifilm/current/packaging/compose/docker-compose.production.yml}"
TEMPLATE="${TEMPLATE:-/opt/ifilm/current/packaging/https/host-nginx-ifilm.conf.template}"
SITE_AVAILABLE="${SITE_AVAILABLE:-/etc/nginx/sites-available/ifilm}"
SITE_ENABLED="${SITE_ENABLED:-/etc/nginx/sites-enabled/ifilm}"
WEBROOT="${WEBROOT:-/var/www/certbot}"
CLI_PUBLIC_DOMAIN="${PUBLIC_DOMAIN:-}"
CLI_CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
INCLUDE_WWW="${INCLUDE_WWW:-auto}"  # auto|yes|no
CLI_IFILM_HTTP_PORT="${IFILM_HTTP_PORT:-}"

log() { printf '[ifilm-https] %s\n' "$*"; }
die() { printf '[ifilm-https] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "must run as root"
[[ -f "$IFILM_ENV_FILE" ]] || die "missing ${IFILM_ENV_FILE}"
[[ -f "$COMPOSE_FILE" ]] || die "missing ${COMPOSE_FILE}"
[[ -f "$TEMPLATE" ]] || die "missing ${TEMPLATE}"

# shellcheck disable=SC1090
set -a
# shellcheck disable=SC1090
. "$IFILM_ENV_FILE"
set +a

PUBLIC_DOMAIN="${CLI_PUBLIC_DOMAIN:-${PUBLIC_DOMAIN:-}}"
IFILM_HTTP_PORT="${CLI_IFILM_HTTP_PORT:-${IFILM_HTTP_PORT:-8080}}"
CERTBOT_EMAIL="${CLI_CERTBOT_EMAIL:-}"

[[ -n "$PUBLIC_DOMAIN" ]] || die "PUBLIC_DOMAIN is required"
[[ "$PUBLIC_DOMAIN" != "localhost" ]] || die "PUBLIC_DOMAIN must be a real DNS name, not localhost"

if [[ -z "$CERTBOT_EMAIL" ]]; then
  CERTBOT_EMAIL="$(awk -F= '$1=="ADMIN_BOOTSTRAP_EMAIL"{print substr($0,index($0,"=")+1); exit}' "$IFILM_ENV_FILE")"
fi
[[ -n "$CERTBOT_EMAIL" && "$CERTBOT_EMAIL" != *localhost* && "$CERTBOT_EMAIL" == *@* ]] \
  || die "CERTBOT_EMAIL must be a real email (set CERTBOT_EMAIL=ops@example.com)"

log "domain=${PUBLIC_DOMAIN} email=${CERTBOT_EMAIL} backend=127.0.0.1:${IFILM_HTTP_PORT}"

# --- DNS preflight (public resolvers) ---
resolve_a() {
  dig +short "$1" A @8.8.8.8 | head -1
}
HOST_IP="$(curl -fsS --max-time 10 https://ifconfig.me || curl -fsS --max-time 10 https://api.ipify.org || true)"
[[ -n "$HOST_IP" ]] || die "could not determine public IP"
DNS_IP="$(resolve_a "$PUBLIC_DOMAIN")"
[[ -n "$DNS_IP" ]] || die "PUBLIC_DOMAIN ${PUBLIC_DOMAIN} has no A record"
[[ "$DNS_IP" == "$HOST_IP" ]] \
  || die "DNS mismatch: ${PUBLIC_DOMAIN} → ${DNS_IP}, this host → ${HOST_IP}"

WWW_ARGS=()
WWW_SERVER_NAME=""
INCLUDE_WWW_EFFECTIVE=0
if [[ "$INCLUDE_WWW" == "yes" ]] || { [[ "$INCLUDE_WWW" == "auto" ]] && [[ "$(resolve_a "www.${PUBLIC_DOMAIN}")" == "$HOST_IP" ]]; }; then
  WWW_ARGS+=(-d "www.${PUBLIC_DOMAIN}")
  WWW_SERVER_NAME="www.${PUBLIC_DOMAIN}"
  INCLUDE_WWW_EFFECTIVE=1
  log "including www.${PUBLIC_DOMAIN}"
fi

# Fix broken loopback hosts entry that shadows public DNS on this host.
if grep -qE "^127\.0\.1\.1[[:space:]].*[[:space:]]${PUBLIC_DOMAIN}([[:space:]]|\$)" /etc/hosts; then
  log "removing 127.0.1.1 ${PUBLIC_DOMAIN} from /etc/hosts"
  sed -i -E "s/^(127\.0\.1\.1[[:space:]].*)[[:space:]]${PUBLIC_DOMAIN}([[:space:]]|\$)/\1\2/" /etc/hosts
  sed -i -E "s/^(127\.0\.1\.1[[:space:]]+)$/127.0.1.1/" /etc/hosts
fi

# --- packages ---
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq nginx certbot python3-certbot-nginx curl dnsutils

mkdir -p "$WEBROOT" /etc/nginx/sites-available /etc/nginx/sites-enabled
# Disable default site if present
rm -f /etc/nginx/sites-enabled/default

# --- firewall ---
if command -v ufw >/dev/null 2>&1; then
  ufw allow OpenSSH >/dev/null || true
  ufw allow 80/tcp >/dev/null || true
  ufw allow 443/tcp >/dev/null || true
  # Enable non-interactively if inactive
  if ! ufw status | grep -q "Status: active"; then
    ufw --force enable >/dev/null || true
  fi
  log "ufw: OpenSSH/80/443 allowed"
fi

upsert_env() {
  local key="$1" value="$2"
  if grep -qE "^${key}=" "$IFILM_ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${value}|" "$IFILM_ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >>"$IFILM_ENV_FILE"
  fi
}

# --- bind compose nginx to loopback BEFORE publishing 80/443 via host nginx ---
upsert_env IFILM_HTTP_BIND "127.0.0.1"
upsert_env IFILM_HTTP_PORT "$IFILM_HTTP_PORT"
upsert_env HTTPS_MODE "provided"
upsert_env PUBLIC_DOMAIN "$PUBLIC_DOMAIN"
if [[ "$INCLUDE_WWW_EFFECTIVE" -eq 1 ]]; then
  upsert_env CORS_ORIGINS "[\"https://${PUBLIC_DOMAIN}\",\"https://www.${PUBLIC_DOMAIN}\"]"
else
  upsert_env CORS_ORIGINS "[\"https://${PUBLIC_DOMAIN}\"]"
fi
upsert_env HLS_PUBLIC_BASE_URL "https://${PUBLIC_DOMAIN}/api/stream"
upsert_env DEMO_PUBLIC_BASE_URL "https://${PUBLIC_DOMAIN}"
chmod 600 "$IFILM_ENV_FILE"

log "recreating compose nginx on 127.0.0.1:${IFILM_HTTP_PORT}"
cd "$(dirname "$COMPOSE_FILE")"
# Export bind for compose interpolation
export IFILM_HTTP_BIND=127.0.0.1
export IFILM_HTTP_PORT
docker compose --env-file "$IFILM_ENV_FILE" -f "$COMPOSE_FILE" up -d nginx
sleep 2
curl -fsS "http://127.0.0.1:${IFILM_HTTP_PORT}/api/health/live" >/dev/null \
  || die "compose app not healthy on 127.0.0.1:${IFILM_HTTP_PORT}"

render_site() {
  local out="$1"
  sed \
    -e "s/__PUBLIC_DOMAIN__/${PUBLIC_DOMAIN}/g" \
    -e "s/__IFILM_HTTP_PORT__/${IFILM_HTTP_PORT}/g" \
    -e "s/__WWW_SERVER_NAME__/${WWW_SERVER_NAME}/g" \
    "$TEMPLATE" >"$out"
}

# Bootstrap HTTP-only site for ACME webroot (certs may not exist yet)
BOOTSTRAP="$(mktemp)"
cat >"$BOOTSTRAP" <<EOF
server {
  listen 80;
  listen [::]:80;
  server_name ${PUBLIC_DOMAIN} ${WWW_SERVER_NAME};

  location ^~ /.well-known/acme-challenge/ {
    root ${WEBROOT};
    default_type "text/plain";
  }

  location / {
    proxy_pass http://127.0.0.1:${IFILM_HTTP_PORT};
    proxy_set_header Host \$host;
    proxy_set_header X-Real-IP \$remote_addr;
    proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;
  }
}
EOF
install -m 0644 "$BOOTSTRAP" "$SITE_AVAILABLE"
ln -sfn "$SITE_AVAILABLE" "$SITE_ENABLED"
rm -f "$BOOTSTRAP"
nginx -t
systemctl enable --now nginx
systemctl reload nginx

# Obtain / renew certificate
CERT_ARGS=(-d "$PUBLIC_DOMAIN")
if [[ ${#WWW_ARGS[@]} -gt 0 ]]; then
  CERT_ARGS+=("${WWW_ARGS[@]}")
fi
if [[ -d "/etc/letsencrypt/live/${PUBLIC_DOMAIN}" ]]; then
  log "certificate already present; skipping issue"
else
  log "requesting Let's Encrypt certificate"
  certbot certonly \
    --webroot -w "$WEBROOT" \
    --email "$CERTBOT_EMAIL" \
    --agree-tos \
    --no-eff-email \
    --non-interactive \
    "${CERT_ARGS[@]}"
fi

# Install full HTTPS site
render_site "$SITE_AVAILABLE"
# Clean empty www token if www not included (trailing space before ;)
sed -i -E "s/server_name ${PUBLIC_DOMAIN} ;/server_name ${PUBLIC_DOMAIN};/g" "$SITE_AVAILABLE" || true
nginx -t
systemctl reload nginx

# Certbot renew deploy hook to reload nginx
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat >/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh <<'HOOK'
#!/bin/sh
systemctl reload nginx
HOOK
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh

log "running certbot renew dry-run"
certbot renew --dry-run

# Rewrite absolute http://domain:8080 artwork/stream URLs in DB to https://domain
log "rewriting demo absolute URLs to https://${PUBLIC_DOMAIN}"
docker compose --env-file "$IFILM_ENV_FILE" -f "$COMPOSE_FILE" exec -T postgres \
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1' <<SQL
UPDATE movies SET
  poster_url = replace(replace(poster_url, 'http://${PUBLIC_DOMAIN}:8080', 'https://${PUBLIC_DOMAIN}'), 'https://${PUBLIC_DOMAIN}:8080', 'https://${PUBLIC_DOMAIN}'),
  backdrop_url = replace(replace(backdrop_url, 'http://${PUBLIC_DOMAIN}:8080', 'https://${PUBLIC_DOMAIN}'), 'https://${PUBLIC_DOMAIN}:8080', 'https://${PUBLIC_DOMAIN}')
WHERE poster_url LIKE '%${PUBLIC_DOMAIN}%' OR backdrop_url LIKE '%${PUBLIC_DOMAIN}%';

UPDATE series SET
  poster_url = replace(replace(poster_url, 'http://${PUBLIC_DOMAIN}:8080', 'https://${PUBLIC_DOMAIN}'), 'https://${PUBLIC_DOMAIN}:8080', 'https://${PUBLIC_DOMAIN}'),
  backdrop_url = replace(replace(backdrop_url, 'http://${PUBLIC_DOMAIN}:8080', 'https://${PUBLIC_DOMAIN}'), 'https://${PUBLIC_DOMAIN}:8080', 'https://${PUBLIC_DOMAIN}')
WHERE poster_url LIKE '%${PUBLIC_DOMAIN}%' OR backdrop_url LIKE '%${PUBLIC_DOMAIN}%';

UPDATE episodes SET
  thumbnail_url = replace(replace(thumbnail_url, 'http://${PUBLIC_DOMAIN}:8080', 'https://${PUBLIC_DOMAIN}'), 'https://${PUBLIC_DOMAIN}:8080', 'https://${PUBLIC_DOMAIN}')
WHERE thumbnail_url LIKE '%${PUBLIC_DOMAIN}%';
SQL

# Recreate API/workers so env CORS/HLS base apply
docker compose --env-file "$IFILM_ENV_FILE" -f "$COMPOSE_FILE" up -d backend-api media-processing-worker publishing-worker

log "HTTPS enabled for https://${PUBLIC_DOMAIN}"
log "compose nginx bound to 127.0.0.1:${IFILM_HTTP_PORT} (not public)"
log "certificate: /etc/letsencrypt/live/${PUBLIC_DOMAIN}/"
log "renewal: certbot.timer + deploy hook reload-nginx.sh"
