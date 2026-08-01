# Release process

## Versioning

Tags: `vMAJOR.MINOR.PATCH` (optional prerelease suffix, e.g. `v0.1.4-candidate`).

## Source of truth

GitHub Releases are the only production update source. Do not update production from `main`, PR branches, commit SHAs, or user-provided URLs.

## Supported platforms (install)

| Platform | Status |
| --- | --- |
| Ubuntu 24.04 LTS x86_64 | **Verified** (disposable proof) |
| Ubuntu 22.04 LTS x86_64 | Experimental — requires `IFILM_ALLOW_UNVERIFIED_OS=1` |
| Debian 12 x86_64 | Experimental — requires `IFILM_ALLOW_UNVERIFIED_OS=1` |

Overlay root filesystems and no-systemd hosts require explicit opt-in and are **not** normal production deployments.

## Signing identity

- Public key: `packaging/keys/release-signing.pub`
- Public fingerprint: `e7b365230a5b360f417532cba134fdb91eaa73b814163f3175a3f13d28286612`
- Revoked fingerprints: `packaging/keys/REVOKED_FINGERPRINTS.txt`
- Private key: Environment secret `IFILM_RELEASE_SIGNING_KEY` (`production-release`) only
- Algorithm: Ed25519 via `openssl pkeyutl` (`-rawin`)

**Emergency rotation 2026-08-01:** previous fingerprint  
`8c04b9141a9fe72346edf9e1f6bc27b0fbef3dc728d6e61124fb897e74ac1e26` is revoked.  
See `KEY_ROTATION_EMERGENCY_2026-08-01.md`.

## CI workflow

`.github/workflows/release.yml` runs only on version-tag pushes:

### Job `quality` (no signing secret)

1. Verify tag format
2. Backend quality: ruff, mypy, **full** `pytest -q` (aligned with local), Alembic heads
3. Frontend quality (pnpm lint/typecheck/test/build)
4. ShellCheck installers
5. Packaging unit tests (release rejection + image digest policy)
6. Compose validation with immutable digest placeholders

### Job `publish` (Environment: `production-release`)

Requires secret `IFILM_RELEASE_SIGNING_KEY` and should require manual approval when configured.

1. Authenticate to GHCR with Actions credentials
2. Build flat release archive
3. Build production images (backend-api + frontend; workers share backend-api)
4. Push version tags to GHCR
5. Resolve **registry** digests (`ghcr.io/...@sha256:...`) — fail if unresolved; never use local image IDs
6. Pull by digest to verify
7. Install **pinned** Syft + Trivy (checksum-verified release tarballs)
8. Generate SBOMs for all shipped app images — **failure fails the release**
9. Run Trivy JSON scans — unapproved CRITICAL fail; HIGH with FixedVersion fail (see `packaging/security/trivy-ignore.json`)
10. Upload scan reports + SBOMs as workflow artifacts
11. Build `release-manifest.json` with required registry digests and sign with Ed25519 (key never logged)
12. Create GitHub Release including archive, manifest, signature, checksums, SBOMs, and scan JSON

Failed quality, missing digests, scan gate failures, SBOM failures, or missing/invalid signing secret abort publishing.

## Manifest image digests

Required keys:

- `backend-api` → `ghcr.io/nimroozy/ifilm2026/backend-api@sha256:...`
- `frontend` → `ghcr.io/nimroozy/ifilm2026/frontend@sha256:...`
- optional worker aliases pointing at the same backend-api digest

Mutable tags (`latest`, branch names) and bare local IDs are rejected.

## Vulnerability ignore policy

`packaging/security/trivy-ignore.json` entries require id, component, justification, owner, expiry. Expired ignores fail the release.

## Local vs CI backend tests

```bash
cd app/backend
FRONTEND_DIST= DATABASE_URL=sqlite:// REDIS_REQUIRED=false pytest -q
```

Documented skip: `tests/test_database_url.py` live proof (`STAGING_DB_URL_TEST=1`).
