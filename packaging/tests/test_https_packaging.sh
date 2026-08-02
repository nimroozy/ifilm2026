#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TEMPLATE="$ROOT/packaging/https/host-nginx-ifilm.conf.template"
SCRIPT="$ROOT/packaging/https/enable_https.sh"
COMPOSE="$ROOT/packaging/compose/docker-compose.production.yml"

[[ -f "$TEMPLATE" ]] || { echo "missing template"; exit 1; }
[[ -x "$SCRIPT" ]] || { echo "enable_https.sh not executable"; exit 1; }
grep -q '__PUBLIC_DOMAIN__' "$TEMPLATE"
grep -q 'ssl_certificate' "$TEMPLATE"
grep -q 'X-Forwarded-Proto https' "$TEMPLATE"
grep -q 'IFILM_HTTP_BIND' "$COMPOSE"
grep -q '127.0.0.1' "$COMPOSE"
# render smoke
sed -e 's/__PUBLIC_DOMAIN__/ifilm.af/g' \
    -e 's/__IFILM_HTTP_PORT__/8080/g' \
    -e 's/__WWW_SERVER_NAME__/www.ifilm.af/g' \
    "$TEMPLATE" | grep -q 'server_name ifilm.af www.ifilm.af'
echo "https packaging checks ok"
