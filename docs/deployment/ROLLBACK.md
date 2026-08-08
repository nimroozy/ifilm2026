# Rollback

## Automatic rollback triggers

- Migration failure
- Core service remains unhealthy
- Readiness does not recover
- Smoke/health failure after install
- Release activation failure

## What rollback restores

- Previous immutable application release (`/opt/ifilm/current` symlink)
- Previous compose/release configuration
- Logs and failed-release diagnostics are preserved
- Media originals and completed packages are never deleted

## Database rollback limitations

Migrations are classified as:

- backward-compatible
- rollback-safe
- requires database restore
- irreversible

The release manifest declares rollback compatibility. Automatic rollback is **not** claimed safe for every schema migration.

If rollback requires database restore, operators must confirm explicitly unless a fully tested automatic recovery policy is enabled.

## Manual rollback

Use Admin → System updates → Roll Back (password + confirmation), or the update-agent `rollback_last_update` command via the admin API. Do not run ad-hoc `docker compose down -v`.

## Media worker shared volumes (PR #51)

This change is **application/compose only** — no Alembic migration and no database schema changes.

**Rollback:** restore the previous immutable release via the update-agent (application_only). Media files under `/var/lib/ifilm/media/*` are retained. After rollback, trailer/subtitle probe may fail again if the previous compose lacked worker category mounts.

**Forward deploy path:** installer and update-agent invoke only
`packaging/compose/docker-compose.production.yml` (never
`docker-compose.media-categories.override.yml`). On activate they delete any
leftover interim override so the released worker mounts (`:ro`) and
`python -m app.workers.media_processing --healthcheck` are authoritative.

## Disposable proof

`v0.1.3-failhealth` intentionally failed readiness after install; the agent automatically rolled back to `v0.1.1-test` (`rollback_compatibility=application_only`). Media and catalog rows remained intact. See `DISPOSABLE_VERIFICATION.md`.
