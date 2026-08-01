# Disposable verification record (PR #14)

This document records the disposable-host verification for the installer and
self-update system. **No secrets are included.**

## Host

| Field | Value |
| --- | --- |
| Role | Disposable cloud agent VM (isolated from staging Compose project) |
| OS | Ubuntu 24.04.4 LTS |
| Kernel | 6.12.94+ |
| Arch | x86_64 |
| CPUs | 4 |
| RAM | ~16 GiB |
| Free disk | ~165–186 GiB |
| Root FS | overlay (allowed only with `IFILM_ALLOW_OVERLAY_FS=1`) |
| Init | no systemd PID 1 (Docker already running) |
| HTTP port | `18080` (staging left on `8080`) |
| Connectivity | outbound HTTPS to GitHub |
| Firewall | host netfilter not readable in this environment |

Staging containers/volumes were **not** used for data. Disposable paths:

- `/opt/ifilm`
- `/etc/ifilm/ifilm.env` (mode `600`)
- `/var/lib/ifilm/*`

## Signing

- Scheme: Ed25519 (`openssl pkeyutl` with `-rawin`)
- Public key committed: `packaging/keys/release-signing.pub`
- Private key: temporary test key held only in a mode-`600` temp file during publish; **not** committed; **not** printed; shredded after verification
- GitHub Actions secret `IFILM_RELEASE_SIGNING_KEY`: **could not be written** by the agent token (`403 Resource not accessible by integration`). Releases were signed locally with the same cryptographic material that secret would hold. A repo admin should store the production/signing key as that secret for CI publish.

Rejection matrix exercised (tooling tests + bad published release):

- unsigned / modified manifests
- wrong public key
- modified artifacts / checksum mismatch (`v0.1.2-badtest`)
- mismatched image digest detection
- stale `minimum_version` policy check

## Releases

| Tag | URL | Result |
| --- | --- | --- |
| `v0.1.0-test` | https://github.com/nimroozy/ifilm2026/releases/tag/v0.1.0-test | Clean install baseline |
| `v0.1.1-test` | https://github.com/nimroozy/ifilm2026/releases/tag/v0.1.1-test | Successful update + migration `012_system_update_notes` |
| `v0.1.2-badtest` | https://github.com/nimroozy/ifilm2026/releases/tag/v0.1.2-badtest | Intentional checksum mismatch → `verification_failed` |
| `v0.1.3-failhealth` | https://github.com/nimroozy/ifilm2026/releases/tag/v0.1.3-failhealth | Intentional health failure → automatic `rolled_back` |

Assets verified by downloading from GitHub Releases (not the working tree).

## Bootstrap command used

`main` does not yet contain `install.sh` (pre-merge). Disposable bootstrap used the PR branch / commit-pinned raw URL:

```bash
curl -fsSL https://raw.githubusercontent.com/nimroozy/ifilm2026/<commit>/install.sh -o /tmp/ifilm-install.sh
sudo env \
  IFILM_VERSION=v0.1.0-test \
  IFILM_CHANNEL=staging \
  IFILM_HTTP_PORT=18080 \
  IFILM_REQUIRED_PORTS=18080 \
  IFILM_ALLOW_OVERLAY_FS=1 \
  IFILM_ALLOW_PRERELEASE_CHANNEL=1 \
  IFILM_RELEASE_PUBLIC_KEY_URL=https://raw.githubusercontent.com/nimroozy/ifilm2026/deployment/installer-updater/packaging/keys/release-signing.pub \
  IFILM_NONINTERACTIVE=1 \
  INSTALL_MODE=staging \
  PUBLIC_DOMAIN=localhost \
  ADMIN_EMAIL=admin@disposable.test \
  ADMIN_USERNAME=admin \
  ADMIN_PASSWORD='***' \
  ENABLE_UPLOADS=true \
  bash /tmp/ifilm-install.sh
```

**Deviation:** public one-liner points at `main`; until merge, disposable verification used the feature-branch/commit raw URL. Release artifacts still came only from GitHub Releases.

## Results

### Clean install (`v0.1.0-test`)
- Signature + checksum verification passed
- Paths `/opt/ifilm`, `/etc/ifilm`, `/var/lib/ifilm` created
- Secrets file mode `600`
- Migrations through `011_system_updates` once
- Admin bootstrap OK
- Health ready OK
- Version reported `0.1.0-test`

### Sample persistent data
- Admin user
- Genre + movie `Disposable Film`
- Media original + package marker files under `/var/lib/ifilm/media`
- Fixture subscriber skipped (compose initially forced `STAGING_ALLOW_FIXTURE_AUTH=false`; later made overridable — catalog/media used for preservation proof)

### Update (`v0.1.1-test`) via admin API (`/admin/system/updates` backend)
- Check found `0.1.1-test` on staging channel
- Preflight passed (signature, newer version, disk, locks)
- Backup created + `pg_restore -l` OK; secrets redacted in config backup
- Install completed
- Version → `0.1.1-test`; migration head → `012_system_update_notes`
- Movie + media preserved; secrets file unchanged path/mode

### Forced failures
- **A.** `v0.1.2-badtest` → `verification_failed` / `checksum_mismatch`; version remained `0.1.1-test`
- **B.** `v0.1.3-failhealth` → health check failed → automatic `rolled_back` to `0.1.1-test`; movie + media intact

### Restart recovery
- Stale agent lock caused preflight `lock_free` failure (no second concurrent update)
- Clearing lock restored preflight success
- History remained queryable
- Agent restarted without systemd via supervised process

### Uninstall
- Default uninstall removed containers, **preserved** `/var/lib/ifilm` and `/etc/ifilm`
- Destructive delete requires typed `IFILM_DELETE_CONFIRM=DELETE-IFILM-DATA`

## Supported OS matrix (this run)

| Platform | Claim | Evidence |
| --- | --- | --- |
| Ubuntu 24.04 x86_64 | **Verified / supported** | Disposable clean install + update + rollback |
| Ubuntu 22.04 | **Experimental / unverified** | Requires `IFILM_ALLOW_UNVERIFIED_OS=1`; not proven |
| Debian 12 | **Experimental / unverified** | Requires `IFILM_ALLOW_UNVERIFIED_OS=1`; not proven |
| Other OS/arch | Rejected | Installer hard-fail |
| Overlay FS / no-systemd | Explicit opt-in only | Not normal production deployment |

## Emergency key rotation (2026-08-01)

Previous production signing private key was **exposed and permanently compromised**.
Revoked fingerprint: `8c04b9141a9fe72346edf9e1f6bc27b0fbef3dc728d6e61124fb897e74ac1e26`.
Current fingerprint: `e7b365230a5b360f417532cba134fdb91eaa73b814163f3175a3f13d28286612`.
See `KEY_ROTATION_EMERGENCY_2026-08-01.md`. Do not trust artifacts signed under the revoked identity.

## Actions-signed candidate attempt (`v0.1.4-candidate`)

As of post-rotation branch tip (see git history):

| Gate | Result |
| --- | --- |
| Release `quality` job | Pass (backend/frontend/installer/compose) |
| GHCR push + registry digests | Pass |
| SBOM generation | Pass |
| Trivy hard gate | Pass (CRITICAL ignores + actionable HIGH policy) |
| Manifest sign with `production-release` secret | **FAIL** — secret accessible but `signing_key_bytes=19` (not a PEM) |
| GitHub prerelease created | Not yet |
| Disposable install from Actions-signed candidate | Blocked on signing |

Admin must re-set `IFILM_RELEASE_SIGNING_KEY` to the full private key PEM — see `ADMIN_SIGNING_SETUP.md`.

## Limitations / deviations

1. Environment `production-release` exists; secret name present but value is not a usable PEM (19 bytes). Agent token cannot rewrite secrets (403).
2. Bootstrap URL used PR branch/commit for earlier disposable tests, not `main` (pre-merge).
3. Overlay root FS required explicit opt-in.
4. No systemd — update-agent run as supervised process.
5. Port `18080` to avoid colliding with staging on `8080`.
6. Hotfixes applied during early verification committed on the PR branch.
7. Database rollback classification for `012`: **backward-compatible / rollback-safe column**; failhealth test used **application_only** rollback (no DB restore).
8. Trivy policy: unapproved CRITICAL always fail (time-bound ignores for unfixed Debian base); HIGH fail only when `FixedVersion` exists.

## Rollback classification reminder

Automatic rollback restores previous immutable release symlink/images/config.
It does **not** automatically restore PostgreSQL for irreversible migrations.
Manifest field `rollback_compatibility` must be trusted.
