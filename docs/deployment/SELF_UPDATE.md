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

## Disposable verification

See `DISPOSABLE_VERIFICATION.md` for the recorded clean install (`v0.1.0-test`), update (`v0.1.1-test`), checksum rejection, and automatic health-failure rollback.
