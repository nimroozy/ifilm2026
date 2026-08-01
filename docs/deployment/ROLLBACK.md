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

## Disposable proof

`v0.1.3-failhealth` intentionally failed readiness after install; the agent automatically rolled back to `v0.1.1-test` (`rollback_compatibility=application_only`). Media and catalog rows remained intact. See `DISPOSABLE_VERIFICATION.md`.
