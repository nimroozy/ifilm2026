# One-command install

## Exact command

```bash
curl -fsSL https://raw.githubusercontent.com/nimroozy/ifilm2026/main/install.sh | sudo bash
```

Optional overrides:

```bash
curl -fsSL https://raw.githubusercontent.com/nimroozy/ifilm2026/main/install.sh | sudo \
  IFILM_CHANNEL=stable IFILM_VERSION=v1.0.0 bash
```

## Supported systems

- **Verified:** Ubuntu Server 24.04 LTS (x86_64) — see `DISPOSABLE_VERIFICATION.md`
- **Installer accepts (not disposable-verified in PR #14):** Ubuntu Server 22.04 LTS, Debian 12 (x86_64)

Unsupported OS or architecture fails clearly. Overlay root filesystems (common in cloud VMs) require explicit `IFILM_ALLOW_OVERLAY_FS=1`. Do not force the installer on other platforms.

## Prerequisites

- Root privileges
- Internet/DNS access to GitHub and Docker apt repositories
- Free ports 80/443 (override with `IFILM_REQUIRED_PORTS`)
- Minimum ~2 GB RAM and ~20 GB free disk
- Root filesystem `ext4`, `xfs`, or `btrfs`

## What the bootstrap does

`install.sh` remains small and auditable. It:

1. Detects OS/arch and rejects unsupported hosts
2. Checks resources, DNS, and ports
3. Installs Docker Engine + Compose plugin from Docker’s official apt repo
4. Installs `curl`, `jq`, `openssl`, `ca-certificates`, and utilities
5. Downloads the latest **signed** GitHub Release for the channel
6. Verifies manifest signature and archive checksum
7. Extracts atomically under `/opt/ifilm`
8. Runs the verified package installer (`packaging/installer/install_release.sh`)

Unverified artifacts are never executed.

## Directories

| Path | Purpose |
| --- | --- |
| `/opt/ifilm` | Application releases + `current` symlink |
| `/etc/ifilm/ifilm.env` | Secrets and config (mode `600`, root-owned) |
| `/var/lib/ifilm/postgres` | PostgreSQL data |
| `/var/lib/ifilm/redis` | Redis data |
| `/var/lib/ifilm/media/*` | Media originals/packages/temp |
| `/var/lib/ifilm/backups` | Pre-update and ops backups |
| `/var/log/ifilm` | Logs |
| `/run/ifilm/update-agent.sock` | Update-agent Unix socket |

## Secrets

Generated at install time (never stored in git):

- PostgreSQL password
- Redis password
- JWT secret
- Playback token secret
- Update-agent shared secret
- Admin password (prompted or generated)

## Production defaults

- `SUBSCRIBER_IDENTITY_MODE=disabled`
- `RADIUS_ENTITLEMENT_MAPPING_ENABLED=false`
- Fixture authentication forbidden
- No public `MEDIA_ROOT`
- No Cloudflare/CDN/R2/S3 configuration

## Uninstall

```bash
sudo /opt/ifilm/current/packaging/scripts/uninstall.sh
```

Preserves data and backups by default. Destructive deletion requires an explicit typed confirmation phrase.
