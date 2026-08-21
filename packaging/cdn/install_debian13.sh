#!/bin/sh
# Idempotent Debian 13 bootstrap for an iFilm signed branch-cache node.
set -eu
umask 077

: "${IFILM_CDN_NODE_ID:?missing node id}"
: "${IFILM_CDN_CENTRAL_URL:?missing central URL}"
: "${IFILM_CDN_ENROLLMENT_TOKEN:?missing one-time enrollment token}"
: "${IFILM_CDN_CACHE_LIMIT_BYTES:?missing cache limit}"

case "${IFILM_CDN_CENTRAL_URL}" in https://*) ;; *) echo "central URL must use HTTPS" >&2; exit 2;; esac
case "${IFILM_CDN_CACHE_LIMIT_BYTES}" in *[!0-9]*|'') echo "invalid cache limit" >&2; exit 2;; esac

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y --no-install-recommends ca-certificates curl nftables python3 python3-venv rsync

if ! id ifilm-cdn >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/ifilm-cdn --create-home --shell /usr/sbin/nologin ifilm-cdn
fi
install -d -o ifilm-cdn -g ifilm-cdn -m 0750 /var/lib/ifilm-cdn/cache /var/log/ifilm-cdn
install -d -o root -g ifilm-cdn -m 0750 /etc/ifilm-cdn

tmp_config="$(mktemp)"
trap 'rm -f "$tmp_config"' EXIT
cat >"$tmp_config" <<EOF
IFILM_CDN_NODE_ID=$IFILM_CDN_NODE_ID
IFILM_CDN_CENTRAL_URL=$IFILM_CDN_CENTRAL_URL
IFILM_CDN_CACHE_LIMIT_BYTES=$IFILM_CDN_CACHE_LIMIT_BYTES
IFILM_CDN_ENROLLMENT_TOKEN=$IFILM_CDN_ENROLLMENT_TOKEN
ENABLE_CDN_SYNC=false
EOF
install -o root -g ifilm-cdn -m 0640 "$tmp_config" /etc/ifilm-cdn/node.env

cat >/etc/systemd/system/ifilm-cdn.service <<'EOF'
[Unit]
Description=iFilm signed branch cache
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ifilm-cdn
Group=ifilm-cdn
EnvironmentFile=/etc/ifilm-cdn/node.env
WorkingDirectory=/opt/ifilm-cdn/current/app/backend
ExecStart=/opt/ifilm-cdn/venv/bin/uvicorn app.services.branch_cache.service.asgi:app --host 0.0.0.0 --port 8443
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/ifilm-cdn /var/log/ifilm-cdn /etc/ifilm-cdn

[Install]
WantedBy=multi-user.target
EOF

# The signed release must already have been verified and unpacked by the runner.
test -f /opt/ifilm-cdn/current/app/backend/app/services/branch_cache/service/asgi.py
systemctl daemon-reload
systemctl enable --now nftables ifilm-cdn
systemctl is-active --quiet ifilm-cdn
df -B1 --output=size,avail /var/lib/ifilm-cdn/cache | tail -1
