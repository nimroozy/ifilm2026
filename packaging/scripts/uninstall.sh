#!/usr/bin/env bash
# Safe uninstaller: removes containers/services, preserves data/backups by default.
set -euo pipefail

IFILM_HOME="${IFILM_HOME:-/opt/ifilm}"
IFILM_ETC="${IFILM_ETC:-/etc/ifilm}"
IFILM_VAR="${IFILM_VAR:-/var/lib/ifilm}"
ENV_FILE="${IFILM_ETC}/ifilm.env"
COMPOSE_FILE="${IFILM_HOME}/current/packaging/compose/docker-compose.production.yml"
DELETE_DATA="${IFILM_DELETE_DATA:-0}"
CONFIRM_PHRASE="${IFILM_DELETE_CONFIRM:-}"

log() { printf '[ifilm-uninstall] %s\n' "$*"; }
die() { printf '[ifilm-uninstall] ERROR: %s\n' "$*" >&2; exit 1; }

[[ "$(id -u)" -eq 0 ]] || die "must run as root"

if [[ -f "$COMPOSE_FILE" && -f "$ENV_FILE" ]]; then
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" down || true
fi

if [[ -d /run/systemd/system ]] && command -v systemctl >/dev/null 2>&1; then
  systemctl disable --now ifilm-update-agent.service 2>/dev/null || true
  rm -f /etc/systemd/system/ifilm-update-agent.service
  systemctl daemon-reload || true
else
  if [[ -f "$IFILM_HOME/agent/agent.pid" ]]; then
    kill "$(cat "$IFILM_HOME/agent/agent.pid")" 2>/dev/null || true
    rm -f "$IFILM_HOME/agent/agent.pid"
  fi
fi

log "application containers/services removed"
log "data preserved at ${IFILM_VAR} (default)"
log "config preserved at ${IFILM_ETC} (default)"

if [[ "$DELETE_DATA" == "1" ]]; then
  [[ "$CONFIRM_PHRASE" == "DELETE-IFILM-DATA" ]] \
    || die "refusing data deletion: set IFILM_DELETE_CONFIRM=DELETE-IFILM-DATA"
  rm -rf "$IFILM_VAR" "$IFILM_ETC" "$IFILM_HOME"
  log "data and configuration deleted after typed confirmation"
else
  log "to delete data intentionally: IFILM_DELETE_DATA=1 IFILM_DELETE_CONFIRM=DELETE-IFILM-DATA $0"
fi
