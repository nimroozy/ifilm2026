#!/bin/sh
# Branch-cache lab artifact entrypoint (Phase 7).
# Validates env and either:
#   - --validate-only: construct app, exit 0 (CI / network_mode:none)
#   - default: exec uvicorn bound to loopback only (never public by default)
set -eu

MODE="${BRANCH_CACHE_ENTRY_MODE:-serve}"

if [ "$MODE" = "validate" ] || [ "${1:-}" = "--validate-only" ]; then
  exec python -m app.services.branch_cache.service --validate-only
fi

# Default bind is loopback — not a public network listener.
HOST="${BRANCH_CACHE_BIND_HOST:-127.0.0.1}"
PORT="${BRANCH_CACHE_BIND_PORT:-8080}"

case "$HOST" in
  0.0.0.0|::|\[::\])
    echo "refusing public bind host: $HOST (set BRANCH_CACHE_BIND_HOST=127.0.0.1)" >&2
    exit 2
    ;;
esac

exec uvicorn \
  "app.services.branch_cache.service.asgi:create_app" \
  --factory \
  --host "$HOST" \
  --port "$PORT" \
  --proxy-headers \
  --forwarded-allow-ips="127.0.0.1"
