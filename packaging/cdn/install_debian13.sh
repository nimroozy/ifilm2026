#!/bin/sh
# Manual/offline equivalent of the iFilm CDN provisioning worker for a fresh Debian 13
# server. The admin UI (Admin → CDN → Servers → Provision) performs the same steps over
# SSH; use this only when provisioning must be run by hand on the node itself.
#
# Required environment:
#   IFILM_CDN_NODE_ID          managed node id from Admin → CDN → Servers
#   IFILM_CDN_CENTRAL_URL      https://ifilm.example (central iFilm)
#   IFILM_CDN_NODE_TOKEN       node identity token issued by central (shown once)
#   IFILM_CDN_CACHE_LIMIT_BYTES storage limit for the pull-through cache
#   IFILM_CDN_BUNDLE           path to ifilm-cdn-node-<version>.tar.gz (+ .sha256 beside it)
# Optional:
#   IFILM_CDN_NODE_ROLE (main|cache), IFILM_CDN_SITE_ID, IFILM_CDN_BIND_PORT (8443),
#   IFILM_CDN_EDGE_GRANT_PUBLIC_KEY_FILE (PEM, public key only)
set -eu
umask 077

: "${IFILM_CDN_NODE_ID:?missing node id}"
: "${IFILM_CDN_CENTRAL_URL:?missing central URL}"
: "${IFILM_CDN_NODE_TOKEN:?missing node token}"
: "${IFILM_CDN_CACHE_LIMIT_BYTES:?missing cache limit}"
: "${IFILM_CDN_BUNDLE:?missing node bundle path}"
ROLE="${IFILM_CDN_NODE_ROLE:-cache}"
SITE="${IFILM_CDN_SITE_ID:-default}"
PORT="${IFILM_CDN_BIND_PORT:-8443}"

case "${IFILM_CDN_CENTRAL_URL}" in https://*) ;; *) echo "central URL must use HTTPS" >&2; exit 2;; esac
case "${IFILM_CDN_CACHE_LIMIT_BYTES}" in *[!0-9]*|'') echo "invalid cache limit" >&2; exit 2;; esac
case "${PORT}" in *[!0-9]*|'') echo "invalid port" >&2; exit 2;; esac
case "${ROLE}" in main|cache) ;; *) echo "role must be main or cache" >&2; exit 2;; esac

if [ "$(id -u)" != "0" ]; then echo "run as root" >&2; exit 2; fi
. /etc/os-release
if [ "${ID:-}" != "debian" ] || [ "${VERSION_ID%%.*}" != "13" ]; then
  echo "unsupported OS: ${ID:-?} ${VERSION_ID:-?} (Debian 13 required)" >&2; exit 3
fi
test -f "${IFILM_CDN_BUNDLE}" || { echo "bundle not found" >&2; exit 2; }
test -f "${IFILM_CDN_BUNDLE}.sha256" || { echo "bundle checksum not found" >&2; exit 2; }

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q --no-install-recommends ca-certificates curl nftables python3 python3-venv

if ! id ifilm-cdn >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/ifilm-cdn --no-create-home --shell /usr/sbin/nologin ifilm-cdn
fi
install -d -o ifilm-cdn -g ifilm-cdn -m 0750 /var/lib/ifilm-cdn/cache /var/log/ifilm-cdn
install -d -o root -g ifilm-cdn -m 0750 /etc/ifilm-cdn
install -d -o root -g root -m 0755 /opt/ifilm-cdn /opt/ifilm-cdn/releases

sha256sum -c "${IFILM_CDN_BUNDLE}.sha256"
VERSION="$(tar -xzOf "${IFILM_CDN_BUNDLE}" VERSION | tr -d '\n')"
RELEASE_DIR="/opt/ifilm-cdn/releases/${VERSION}"
install -d -m 0755 "${RELEASE_DIR}"
tar -xzf "${IFILM_CDN_BUNDLE}" -C "${RELEASE_DIR}"
test -x /opt/ifilm-cdn/venv/bin/python || python3 -m venv /opt/ifilm-cdn/venv
/opt/ifilm-cdn/venv/bin/pip install -q --disable-pip-version-check -r "${RELEASE_DIR}/requirements-branch-cache.txt"
ln -sfn "${RELEASE_DIR}" /opt/ifilm-cdn/current
chown -R root:ifilm-cdn "${RELEASE_DIR}"

HIGH=$((IFILM_CDN_CACHE_LIMIT_BYTES * 90 / 100))
LOW=$((IFILM_CDN_CACHE_LIMIT_BYTES * 80 / 100))
tmp_config="$(mktemp)"
trap 'rm -f "$tmp_config"' EXIT
cat >"$tmp_config" <<EOT
ENABLE_CDN_NODE_SERVICE=true
ENABLE_CDN_SYNC=false
IFILM_CDN_NODE_ID=${IFILM_CDN_NODE_ID}
IFILM_CDN_NODE_ROLE=${ROLE}
IFILM_CDN_SITE_ID=${SITE}
IFILM_CDN_CENTRAL_URL=${IFILM_CDN_CENTRAL_URL}
IFILM_CDN_NODE_TOKEN=${IFILM_CDN_NODE_TOKEN}
IFILM_CDN_CACHE_ROOT=/var/lib/ifilm-cdn/cache
IFILM_CDN_CACHE_LIMIT_BYTES=${IFILM_CDN_CACHE_LIMIT_BYTES}
IFILM_CDN_HIGH_WATERMARK_BYTES=${HIGH}
IFILM_CDN_LOW_WATERMARK_BYTES=${LOW}
IFILM_CDN_BIND_HOST=0.0.0.0
IFILM_CDN_BIND_PORT=${PORT}
IFILM_CDN_EDGE_GRANT_PUBLIC_KEY_FILE=/etc/ifilm-cdn/edge-grant-public.pem
IFILM_CDN_SOFTWARE_VERSION=${VERSION}
IFILM_CDN_HEARTBEAT_SECONDS=30
EOT
install -o root -g ifilm-cdn -m 0640 "$tmp_config" /etc/ifilm-cdn/node.env
if [ -n "${IFILM_CDN_EDGE_GRANT_PUBLIC_KEY_FILE:-}" ] && [ -f "${IFILM_CDN_EDGE_GRANT_PUBLIC_KEY_FILE}" ]; then
  if grep -q "PRIVATE KEY" "${IFILM_CDN_EDGE_GRANT_PUBLIC_KEY_FILE}"; then echo "refusing private key" >&2; exit 2; fi
  install -o root -g ifilm-cdn -m 0644 "${IFILM_CDN_EDGE_GRANT_PUBLIC_KEY_FILE}" /etc/ifilm-cdn/edge-grant-public.pem
fi

cat >/etc/systemd/system/ifilm-cdn.service <<EOT
[Unit]
Description=iFilm CDN node (pull-through HLS cache)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=ifilm-cdn
Group=ifilm-cdn
EnvironmentFile=/etc/ifilm-cdn/node.env
WorkingDirectory=/opt/ifilm-cdn/current
ExecStart=/opt/ifilm-cdn/venv/bin/python -m app.services.cdn_node serve
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
ReadWritePaths=/var/lib/ifilm-cdn /var/log/ifilm-cdn
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOT

SSH_PORT="$(ss -tlnp 2>/dev/null | awk '/sshd/ {split($4,a,":"); print a[length(a)]; exit}')"
SSH_PORT="${SSH_PORT:-22}"
cat >/etc/nftables.conf <<EOT
#!/usr/sbin/nft -f
flush ruleset
table inet ifilm_cdn {
  chain input {
    type filter hook input priority 0; policy drop;
    ct state established,related accept
    ct state invalid drop
    iif "lo" accept
    ip protocol icmp accept
    ip6 nexthdr ipv6-icmp accept
    tcp dport ${SSH_PORT} accept
    tcp dport ${PORT} accept
  }
  chain forward { type filter hook forward priority 0; policy drop; }
  chain output { type filter hook output priority 0; policy accept; }
}
EOT
nft -c -f /etc/nftables.conf
nft -f /etc/nftables.conf
systemctl enable nftables

systemctl daemon-reload
systemctl enable --now ifilm-cdn
sleep 2
systemctl is-active --quiet ifilm-cdn
curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/health" >/dev/null
curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/ready" >/dev/null
df -B1 --output=size,used,avail /var/lib/ifilm-cdn/cache | tail -1
echo "ifilm-cdn ${VERSION} installed"
