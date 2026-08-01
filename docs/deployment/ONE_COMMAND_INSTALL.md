# One-command install

## Exact command (after merge to `main`)

```bash
curl -fsSL https://raw.githubusercontent.com/nimroozy/ifilm2026/main/install.sh | sudo bash
```

Optional overrides:

```bash
curl -fsSL https://raw.githubusercontent.com/nimroozy/ifilm2026/main/install.sh | sudo \
  IFILM_CHANNEL=stable IFILM_VERSION=v1.0.0 bash
```

Prerelease / candidate installs (explicit version):

```bash
curl -fsSL https://raw.githubusercontent.com/nimroozy/ifilm2026/main/install.sh | sudo \
  IFILM_CHANNEL=staging IFILM_VERSION=v0.1.4-candidate \
  IFILM_REQUIRED_PORTS="18080" IFILM_HTTP_PORT=18080 \
  IFILM_ALLOW_OVERLAY_FS=1 IFILM_NONINTERACTIVE=1 bash
```

Until `install.sh` is on `main`, operators verifying a release candidate should use the exact file from the commit/tag planned for merge (not a feature-branch curl URL that executes arbitrary branch code). Prefer downloading that `install.sh` and running it locally after inspection.

## Supported systems

| Platform | Status |
| --- | --- |
| **Ubuntu Server 24.04 LTS (x86_64)** | **Verified** — see `DISPOSABLE_VERIFICATION.md` |
| Ubuntu Server 22.04 LTS (x86_64) | **Experimental / unverified** — requires `IFILM_ALLOW_UNVERIFIED_OS=1` |
| Debian 12 (x86_64) | **Experimental / unverified** — requires `IFILM_ALLOW_UNVERIFIED_OS=1` |

Do not advertise 22.04 or Debian 12 as fully supported until disposable verification exists.

### Explicit non-production opt-ins

- `IFILM_ALLOW_OVERLAY_FS=1` — overlay root filesystem (cloud disposable hosts)
- no-systemd hosts — installer may supervise the update agent as a background process; **not** the normal production path (systemd unit required for production)

## Prerequisites

- Root privileges
- Internet/DNS access to GitHub Releases, GHCR, and Docker apt repositories
- Free ports 80/443 (override with `IFILM_REQUIRED_PORTS`)
- Minimum ~2 GB RAM and ~20 GB free disk
- Root filesystem `ext4`, `xfs`, or `btrfs` (or overlay with opt-in)

## What the bootstrap does

`install.sh` remains small and auditable. It:

1. Detects OS/arch; verified platform is Ubuntu 24.04 only
2. Checks resources, DNS, and ports
3. Installs Docker Engine + Compose plugin from Docker’s official apt repo
4. Installs `curl`, `jq`, `openssl`, `ca-certificates`, and utilities
5. Downloads the latest **signed** GitHub Release for the channel from **`nimroozy/ifilm2026` only**
6. Stable channel selection **excludes prereleases**
7. Verifies the downloaded public key against the **embedded fingerprint** trust anchor
8. Verifies manifest signature and archive checksum
9. Requires immutable GHCR image digests in the signed manifest
10. Extracts under `/opt/ifilm` and runs the verified package installer

It does **not** clone git, execute feature-branch code, or run unverified artifacts.

## Directories

| Path | Purpose |
| --- | --- |
| `/opt/ifilm` | Application releases + `current` symlink |
| `/etc/ifilm/ifilm.env` | Secrets and config (mode `600`, root-owned), including immutable image refs |
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
- Application images pulled only by immutable GHCR digest

## Uninstall

```bash
sudo /opt/ifilm/current/packaging/scripts/uninstall.sh
```

Preserves data and backups by default. Destructive deletion requires an explicit typed confirmation phrase.
