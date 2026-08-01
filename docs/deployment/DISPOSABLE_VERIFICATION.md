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
- Public fingerprint (SHA-256 of DER): `e7b365230a5b360f417532cba134fdb91eaa73b814163f3175a3f13d28286612`
- Private key: Environment secret `IFILM_RELEASE_SIGNING_KEY` in `production-release` for Actions-signed candidates; **not** committed; **not** printed; local PEM copies shredded after verification

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

## Actions-signed candidates (`v0.1.4-candidate` → `v0.1.5-candidate`)

Production Ed25519 key stored in Environment secret `IFILM_RELEASE_SIGNING_KEY`
(`production-release`). Public fingerprint verified:

`e7b365230a5b360f417532cba134fdb91eaa73b814163f3175a3f13d28286612`

| Tag | Release run | Result |
| --- | --- | --- |
| `v0.1.4-candidate` | https://github.com/nimroozy/ifilm2026/actions/runs/30703638647 | Actions-signed success (`manifest_signed=true`) |
| `v0.1.5-candidate` | https://github.com/nimroozy/ifilm2026/actions/runs/30703891825 | Actions-signed success |

Immutable digests:

| Release | backend-api | frontend |
| --- | --- | --- |
| `0.1.4-candidate` | `...@sha256:6a18a77fac4df24baeb400879db648bdc480ff9f7ce00c013c70831348e5041c` | `...@sha256:0e7fc89a5ef6dc0547f21a77d6ce5cee4dc0c198846f27452e816d7f0ee74a0e` |
| `0.1.5-candidate` | `...@sha256:52ea7339d1433e7c2763969f107d810d7e704a7bf80b0fd4a687b7a4de3319af` | `...@sha256:9aca7350b6b321dec7bf5cd8d8d71fd9479bfe728aa5780816e893dd287171a6` |

### Disposable proof (Ubuntu 24.04 overlay, port `18080`)

1. **Clean install** of Actions-signed `v0.1.4-candidate` (bootstrap public key URL still branch-pinned pre-merge). Ready OK; migration head `012_system_update_notes`; env mode `600`; marker row `cand-014-marker`.
2. **Update** via admin API to Actions-signed `v0.1.5-candidate`: preflight signature OK; backup `pg_restore -l` OK; agent job `completed`; live version `0.1.5-candidate`; containers on 0.1.5 digests; marker preserved.
3. **Rollback** via admin API (`application_only`): agent job `rolled_back`; live version `0.1.4-candidate`; previous digests restored; marker preserved; ready OK.

### Fixes found during the Actions-signed proof

- Successful API preflight must record terminal state `preflight_ok` (not active `preflight`) so install is not blocked.
- Update-agent compose subprocesses must refresh `IFILM_IMAGE_*` from `/etc/ifilm/ifilm.env` (process env from `EnvironmentFile` / supervised `set -a` otherwise shadows `--env-file` and leaves stale containers).
- Explicit `docker pull <digest>` + `--force-recreate` for app services; auto-rollback after release-tree mutation failures.
- Backend reconciles active install/rollback jobs after API restart during compose recreate.

## Limitations / deviations

1. Bootstrap URL used PR branch/commit for disposable tests, not `main` (pre-merge).
2. Overlay root FS required explicit opt-in.
3. No systemd — update-agent run as supervised process (`UPDATE_AGENT_SOCKET_MODE=0o666`).
4. Port `18080` to avoid colliding with staging on `8080`.
5. Hotfixes applied during verification committed on the PR branch.
6. Database rollback classification for `012`: **backward-compatible / rollback-safe column**; rollback proof used **application_only** (no DB restore).
7. Trivy policy: unapproved CRITICAL always fail (time-bound ignores for unfixed Debian base); HIGH fail only when `FixedVersion` exists.
8. Admin API HTTP calls that recreate `backend-api` may return `502` while the agent job still finishes successfully; job reconciliation / agent job files are authoritative.

## Rollback classification reminder

Automatic rollback restores previous immutable release symlink/images/config.
It does **not** automatically restore PostgreSQL for irreversible migrations.
Manifest field `rollback_compatibility` must be trusted.
