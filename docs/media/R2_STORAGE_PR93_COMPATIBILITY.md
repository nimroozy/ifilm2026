# R2 / Storage compatibility note (PR #93)

**Source reused:** PR #92 tip `bdd4ede5e973485f693f3ca204cf8a6095c6a3d8` (artwork CDN publish path).  
**Future consumer:** PR #93 `claude/ifilm-cdn-admin-settings-cuojh0` (StorageSettingsPage + CDN ops).  
**This milestone does not merge #93 and does not import migration 030.**

## APIs / fields #93 should reuse

| Item | Location | Notes |
|------|----------|-------|
| GET/PUT `/api/admin/cdn-management/r2` | existing | Secret-free DTO; same IntegrationConfig row (`provider=cloudflare_r2`) |
| POST `/api/admin/cdn-management/r2/test` | this branch | Test Connection; returns reachable / bucket_accessible / settings |
| DTO fields | `get_r2()` | `provider`, `object_key_prefix`, `public_base_url`, `artwork_cdn_enabled`, `last_test_*`, `credentials_configured` |
| Secrets | `IntegrationConfig.secret_ciphertext` | Fernet via `INTEGRATION_SECRETS_KEY`; blank PUT preserves |
| Artwork publish | `object_storage/artwork_cdn.py` | Local fallback; CDN URL only after verified upload |
| Frontend aliases | `adminApi.getStorage/updateStorage/testStorage` | Mirror #93 `cdnApi` naming |

## UI controls to move/preserve when #93 rebases

- Prefer **one** page at `/admin/settings/storage` (label: Storage / CDN).
- Keep `/admin/settings/r2` as a redirect (already).
- Preserve from this milestone: Artwork CDN toggle, public base URL, object key prefix, provider select, Test Connection, replace/remove credentials with confirmation, status panel.
- #93 can keep adding CDN node/routing/provisioning under `/admin/cdn/*` without a second storage credentials form.

## Migration / schema overlap

- **No new Alembic revision** in this milestone (still head **029**).
- Storage settings live in existing `integration_configs` JSON + ciphertext.
- #93 migration **030** (`cdn_operations_v1`) is for nodes/provisioning — keep separate; do not require it for artwork CDN.

## Permission overlap

- This branch continues to gate Storage/R2 with admin `settings` (same as pre-#93 R2 page on main).
- #93 introduces finer `cdn.secrets` / `cdn.read` / `cdn.manage`. When rebasing #93, switch Storage routes to `cdn.secrets` and keep customer artwork publish server-side only.

## Config / env overlap

| Env / flag | Role |
|------------|------|
| `ENABLE_ARTWORK_CDN_SYNC` | Host kill-switch for artwork publish (default off) |
| `ARTWORK_CDN_PUBLIC_BASE_URL` | Optional env override for public CDN base |
| `R2_*` / admin IntegrationConfig | Credentials + endpoint/bucket |
| `INTEGRATION_SECRETS_KEY` | Encrypt admin-stored secrets |
| `ENABLE_OBJECT_STORAGE` / `ENABLE_R2_HOT_TIER` | Unrelated origin/hot-tier paths; not required for artwork CDN |

## Cache / key rule

Artwork object keys: `{prefix}/v1/{kind}/{content-addressed-filename}`.  
Replacements mint a new filename/hash locally before switching the DB URL; old objects are not bulk-deleted in this phase.
