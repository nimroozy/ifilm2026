# Disposable test release notes

## v0.1.0-test
Baseline installer + self-update verification release.

## v0.1.1-test
Harmless application change for upgrade proof:
- Alembic `012_system_update_notes` (nullable `operator_notes`, backward-compatible, rollback-safe column drop)
- packaging VERSION bump
