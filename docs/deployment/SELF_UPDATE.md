# Self-update system

## Overview

Production updates come only from **signed GitHub Releases**. The web application never runs arbitrary root shell commands. Privileged steps run in `ifilm-update-agent` over a Unix domain socket with a typed command protocol.

## Channels

- `stable` (production default)
- `beta`
- `staging`

Prereleases are never auto-selected on the stable channel.

## Admin UI

Route: `/admin/system/updates`

Permissions:

- `system_updates.read`
- `system_updates.manage`

Ordinary catalog admins cannot install updates. Install and rollback require password re-authentication and explicit confirmation.

## API

- `GET /api/admin/system/version`
- `POST /api/admin/system/updates/check`
- `POST /api/admin/system/updates/preflight`
- `POST /api/admin/system/updates/install`
- `GET /api/admin/system/updates/{job_id}`
- `POST /api/admin/system/updates/{job_id}/rollback`
- `GET /api/admin/system/updates/history`

Responses never include secrets, env contents, DB credentials, or signing keys.

## Update state machine

`available → preflight → backing_up → downloading → verifying → draining → installing → migrating → restarting → health_checking → completed`

Failure/recovery states include `preflight_failed`, `backup_failed`, `verification_failed`, `migration_failed`, `health_check_failed`, `rollback_running`, `rolled_back`, `rollback_failed`.

## Preflight

Mandatory checks include signature/checksum validity, upgrade path, disk space, PostgreSQL/Redis health, lock availability, and allowlisted release URLs.

## Backup

Software updates create a validated PostgreSQL custom-format dump plus redacted configuration metadata. Media libraries are not duplicated on every update.

## Maintenance mode

Optional `MAINTENANCE_MODE` can signal customer APIs while admins watch update progress. Active streams should not be terminated unnecessarily when only application containers change.

## Offline / manual update

1. Copy a signed release archive, `release-manifest.json`, and `.sig` to the host.
2. Verify signature with `packaging/keys/release-signing.pub` (`openssl pkeyutl -verify ... -rawin`).
3. Ask the update agent (or ops runbook) to install that verified release.
4. Never point production at an arbitrary Git URL or commit SHA.

## Transactional updates

Install/update/rollback follows a fixed order: lock → verify signed release →
save previous release/env → backup → stage release → atomically write
`IFILM_IMAGE_*` digests from the signed manifest → pull digests → recreate the
`ifilm` Compose project → migrate → health → four-way digest verify → atomic
`/opt/ifilm/current` switch → record completion → unlock.

On failure the agent restores previous env image refs, previous symlink, and
previous services. Candidate digests must never remain after a stable install.

Official verification:

```bash
sudo ifilm-update-agent verify-installation
```

Returns nonzero when symlink, signed digests, compose config, running
containers, migration head, health, or channel disagree.

## Disposable verification

See `DISPOSABLE_VERIFICATION.md` for the full record.

PR #40 physical proof (2026-08-04), final head
`e1b94daf88e1f90f005f98616f38a86c5c5c60cd`:

| Gate | Result |
| --- | --- |
| Signed candidate `v1.2.1-rc.1` | Pass — https://github.com/nimroozy/ifilm2026/releases/tag/v1.2.1-rc.1 |
| Release workflow | Pass — https://github.com/nimroozy/ifilm2026/actions/runs/30891929117 |
| Clean install `v1.2.0` (ext4 + systemd) | Pass |
| Stable → candidate four-way digests | Pass |
| Forced health failure → `rolled_back` | Pass |
| Compose conflict / unrelated container | Pass |
| API restart / stale job authority | Pass |
| Interrupted atomic env write | Pass |
| Real rollback to `v1.2.0` | Pass |
| Admin integrity mismatch block | Pass |
| `verify-installation` after healthy terminals | Pass |

Stable channel continues to ignore the prerelease. Do not merge until human review.
