#!/usr/bin/env bash
# iFilm bootstrap installer (small, auditable).
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/nimroozy/ifilm2026/main/install.sh | sudo bash
#
# This script only prepares the host and downloads a *signed* GitHub Release.
# It never executes unverified release artifacts.
set -euo pipefail

IFILM_REPO="${IFILM_REPO:-nimroozy/ifilm2026}"
IFILM_CHANNEL="${IFILM_CHANNEL:-stable}"
IFILM_VERSION="${IFILM_VERSION:-}"          # empty = latest matching channel
IFILM_INSTALL_ROOT="${IFILM_INSTALL_ROOT:-/opt/ifilm}"
IFILM_RELEASE_PUBLIC_KEY_URL="${IFILM_RELEASE_PUBLIC_KEY_URL:-https://raw.githubusercontent.com/${IFILM_REPO}/main/packaging/keys/release-signing.pub}"
MIN_RAM_MB="${IFILM_MIN_RAM_MB:-2048}"
MIN_DISK_GB="${IFILM_MIN_DISK_GB:-20}"
REQUIRED_PORTS="${IFILM_REQUIRED_PORTS:-80 443}"

log() { printf '[ifilm-install] %s\n' "$*"; }
die() { printf '[ifilm-install] ERROR: %s\n' "$*" >&2; exit 1; }

require_root() {
  [[ "$(id -u)" -eq 0 ]] || die "must run as root (use sudo)"
}

detect_platform() {
  OS_ID=""
  OS_VERSION=""
  ARCH="$(uname -m)"
  [[ -f /etc/os-release ]] || die "unsupported: /etc/os-release missing"
  # shellcheck disable=SC1091
  . /etc/os-release
  OS_ID="${ID:-}"
  OS_VERSION="${VERSION_ID:-}"
  case "${OS_ID}-${OS_VERSION}" in
    ubuntu-24.04|ubuntu-22.04|debian-12) ;;
    *)
      die "unsupported OS ${OS_ID} ${OS_VERSION} (supported: Ubuntu 22.04/24.04, Debian 12)"
      ;;
  esac
  case "$ARCH" in
    x86_64|amd64) ARCH=x86_64 ;;
    *) die "unsupported architecture ${ARCH} (supported: x86_64)" ;;
  esac
  log "platform ok: ${OS_ID} ${OS_VERSION} ${ARCH}"
}

check_resources() {
  local mem_kb disk_gb cpus
  mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo)"
  local mem_mb=$((mem_kb / 1024))
  (( mem_mb >= MIN_RAM_MB )) || die "need at least ${MIN_RAM_MB}MB RAM (found ${mem_mb}MB)"
  cpus="$(nproc)"
  (( cpus >= 1 )) || die "CPU detection failed"
  disk_gb="$(df -BG --output=avail / | tail -1 | tr -dc '0-9')"
  (( disk_gb >= MIN_DISK_GB )) || die "need at least ${MIN_DISK_GB}GB free on / (found ${disk_gb}GB)"
  local fstype
  fstype="$(findmnt -no FSTYPE /)"
  case "$fstype" in
    ext4|xfs|btrfs) ;;
    overlay)
      # Cloud/CI disposable hosts often use overlay; allow only with explicit opt-in.
      [[ "${IFILM_ALLOW_OVERLAY_FS:-0}" == "1" ]] \
        || die "unsupported root filesystem overlay (set IFILM_ALLOW_OVERLAY_FS=1 for disposable cloud hosts)"
      ;;
    *) die "unsupported root filesystem ${fstype}" ;;
  esac
  log "resources ok: cpus=${cpus} ram_mb=${mem_mb} disk_gb=${disk_gb} fs=${fstype}"
}

check_network() {
  getent hosts api.github.com >/dev/null || die "DNS lookup failed for api.github.com"
  curl -fsSL --max-time 15 "https://api.github.com" >/dev/null \
    || die "cannot reach https://api.github.com"
  log "network ok"
}

check_ports() {
  local p
  for p in $REQUIRED_PORTS; do
    if command -v ss >/dev/null 2>&1; then
      if ss -ltn "( sport = :$p )" | grep -q ":$p"; then
        die "port ${p}/tcp is already in use"
      fi
    fi
  done
  log "ports ok: ${REQUIRED_PORTS}"
}

install_host_packages() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -y
  apt-get install -y --no-install-recommends \
    ca-certificates curl jq openssl gnupg lsb-release \
    apt-transport-https software-properties-common \
    coreutils findutils grep sed tar gzip
  if ! command -v docker >/dev/null 2>&1; then
    log "installing Docker Engine from Docker's official apt repository"
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL "https://download.docker.com/linux/${OS_ID}/gpg" \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${OS_ID} ${VERSION_CODENAME} stable" \
      > /etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y --no-install-recommends \
      docker-ce docker-ce-cli containerd.io docker-compose-plugin docker-buildx-plugin
  fi
  if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files >/dev/null 2>&1; then
    systemctl enable --now docker
  else
    # Disposable cloud hosts may run Docker without systemd.
    docker info >/dev/null 2>&1 || die "docker daemon not reachable and systemd is unavailable"
  fi
  docker compose version >/dev/null || die "docker compose plugin missing"
  log "host packages ok"
}

fetch_release_metadata() {
  local api="https://api.github.com/repos/${IFILM_REPO}/releases"
  local json
  if [[ -n "$IFILM_VERSION" ]]; then
    json="$(curl -fsSL "${api}/tags/${IFILM_VERSION}")"
  else
    json="$(curl -fsSL "${api}?per_page=30")"
    json="$(printf '%s' "$json" | jq -c --arg ch "$IFILM_CHANNEL" '
      [.[] | select(.draft==false)
        | select(($ch=="stable" and .prerelease==false) or ($ch!="stable"))
      ][0] // empty')"
    [[ -n "$json" ]] || die "no GitHub Release found for channel ${IFILM_CHANNEL}"
  fi
  RELEASE_TAG="$(printf '%s' "$json" | jq -r '.tag_name')"
  [[ "$RELEASE_TAG" != "null" && -n "$RELEASE_TAG" ]] || die "failed to resolve release tag"
  log "selected release ${RELEASE_TAG}"
  MANIFEST_URL="$(printf '%s' "$json" | jq -r '.assets[] | select(.name=="release-manifest.json") | .browser_download_url' | head -1)"
  ARCHIVE_URL="$(printf '%s' "$json" | jq -r '.assets[] | select(.name|test("^ifilm-.*\\.tar\\.gz$")) | .browser_download_url' | head -1)"
  SIG_URL="$(printf '%s' "$json" | jq -r '.assets[] | select(.name=="release-manifest.json.sig") | .browser_download_url' | head -1)"
  [[ -n "$MANIFEST_URL" && "$MANIFEST_URL" != "null" ]] || die "release missing release-manifest.json"
  [[ -n "$ARCHIVE_URL" && "$ARCHIVE_URL" != "null" ]] || die "release missing ifilm-*.tar.gz"
  [[ -n "$SIG_URL" && "$SIG_URL" != "null" ]] || die "release missing release-manifest.json.sig"
}

download_and_verify() {
  local work
  work="$(mktemp -d /tmp/ifilm-bootstrap.XXXXXX)"
  trap 'rm -rf "$work"' EXIT
  curl -fsSL "$IFILM_RELEASE_PUBLIC_KEY_URL" -o "$work/release-signing.pub"
  curl -fsSL "$MANIFEST_URL" -o "$work/release-manifest.json"
  curl -fsSL "$SIG_URL" -o "$work/release-manifest.json.sig"
  curl -fsSL "$ARCHIVE_URL" -o "$work/ifilm-release.tar.gz"

  # Verify manifest signature (Ed25519; OpenSSL requires -rawin).
  openssl pkeyutl -verify -pubin -inkey "$work/release-signing.pub" \
    -sigfile "$work/release-manifest.json.sig" \
    -rawin \
    -in "$work/release-manifest.json" \
    >/dev/null 2>&1 \
    || die "release-manifest.json signature verification FAILED — aborting"

  local expected actual
  expected="$(jq -r '.artifacts[] | select(.name|test("\\.tar\\.gz$")) | .sha256' "$work/release-manifest.json" | head -1)"
  [[ -n "$expected" && "$expected" != "null" ]] || die "manifest missing archive sha256"
  actual="$(sha256sum "$work/ifilm-release.tar.gz" | awk '{print $1}')"
  [[ "$expected" == "$actual" ]] || die "archive checksum mismatch (expected ${expected}, got ${actual})"

  log "release signature and checksum verified"
  mkdir -p "${IFILM_INSTALL_ROOT}/releases"
  local dest="${IFILM_INSTALL_ROOT}/releases/${RELEASE_TAG}"
  rm -rf "$dest"
  mkdir -p "$dest"
  tar -xzf "$work/ifilm-release.tar.gz" -C "$dest"
  ln -sfn "$dest" "${IFILM_INSTALL_ROOT}/current"
  cp "$work/release-manifest.json" "${IFILM_INSTALL_ROOT}/current/release-manifest.json"
  chmod -R a+rX "${IFILM_INSTALL_ROOT}/current"
  VERIFIED_INSTALLER="${IFILM_INSTALL_ROOT}/current/packaging/installer/install_release.sh"
  [[ -x "$VERIFIED_INSTALLER" || -f "$VERIFIED_INSTALLER" ]] \
    || die "verified package missing packaging/installer/install_release.sh"
}

run_verified_installer() {
  log "running verified production installer"
  bash "$VERIFIED_INSTALLER"
}

main() {
  require_root
  detect_platform
  check_resources
  check_network
  check_ports
  install_host_packages
  fetch_release_metadata
  download_and_verify
  run_verified_installer
  log "bootstrap complete"
}

main "$@"
