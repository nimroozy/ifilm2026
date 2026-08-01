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

## CI workflow

`.github/workflows/release.yml` runs only on version-tag pushes:

### Job `quality` (no signing secret)

1. Verify tag format
2. Backend quality: ruff, mypy, **full** `pytest -q` (aligned with local), Alembic heads
3. Frontend quality (lint, typecheck, test, build)
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
7. Install **pinned** Syft + Trivy (checksum-verified release tarballs; no mutable install scripts)
8. Generate SBOMs for all shipped app images — **failure fails the release**
9. Run Trivy JSON scans — **CRITICAL and HIGH fail** unless listed in a non-expired `packaging/security/trivy-ignore.json` entry
10. Upload scan reports + SBOMs as workflow artifacts
11. Build `release-manifest.json` with required registry digests and sign with Ed25519 (key never logged)
12. Create GitHub Release including archive, manifest, signature, checksums, SBOMs, and scan JSON

Failed quality, missing digests, scan gate failures, SBOM failures, or missing signing secret abort publishing.

## Manifest image digests

Required keys:

- `backend-api` → `ghcr.io/nimroozy/ifilm2026/backend-api@sha256:...`
- `frontend` → `ghcr.io/nimroozy/ifilm2026/frontend@sha256:...`
- optional worker aliases pointing at the same backend-api digest

Mutable tags (`latest`, branch names) and bare local IDs are rejected.

Production Compose consumes `IFILM_IMAGE_BACKEND_API` / `IFILM_IMAGE_FRONTEND` written from the signed manifest.

## Signing

See `packaging/keys/README.md` for fingerprint, rotation, and administrator secret setup.

- Algorithm: Ed25519 via `openssl pkeyutl` (`-rawin` required on modern OpenSSL)
- Public fingerprint: `8c04b9141a9fe72346edf9e1f6bc27b0fbef3dc728d6e61124fb897e74ac1e26`

## Vulnerability ignore policy

`packaging/security/trivy-ignore.json` entries require:

- `id` (CVE / GHSA)
- `component`
- `justification`
- `owner`
- `expiry` (ISO date)

Expired ignores fail the release. Prefer fixing or upgrading over ignores.

## Local vs CI backend tests

Local and CI both run the full suite from `app/backend`:

```bash
cd app/backend
FRONTEND_DIST= DATABASE_URL=sqlite:// REDIS_REQUIRED=false pytest -q
```

`FRONTEND_DIST` is forced empty in `tests/conftest.py` and Backend CI so SPA mounts cannot mask `/media` exposure tests.

### Documented skips

| Test | Reason |
| --- | --- |
| `tests/test_database_url.py` live connection proof | Opt-in only (`STAGING_DB_URL_TEST=1`); not required for unit CI |
