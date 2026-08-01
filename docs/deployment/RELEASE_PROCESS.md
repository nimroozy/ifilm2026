# Release process

## Versioning

Tags: `vMAJOR.MINOR.PATCH` (optional prerelease suffix, e.g. `v0.1.1-test`).

## Source of truth

GitHub Releases are the only production update source. Do not update production from `main`, PR branches, commit SHAs, or user-provided URLs.

## CI workflow

`.github/workflows/release.yml` on version tags:

1. Verify tag format
2. Backend quality (ruff, mypy, pytest, Alembic heads)
3. Frontend quality (lint, typecheck, test, build)
4. ShellCheck installers
5. Compose validation
6. Build release archive
7. Build images
8. Generate SBOM (best effort)
9. Scan critical vulnerabilities (best effort gate)
10. Generate `release-manifest.json` + SHA-256
11. Sign manifest with `IFILM_RELEASE_SIGNING_KEY` (never logged)
12. Push versioned images
13. Create GitHub Release with artifacts

Failed tests abort publishing.

## Manifest fields

See `packaging/release/build_manifest.py`. Includes version, channel, commit SHA, migration head, minimum version, rollback compatibility, artifact checksums, and image digests.

Mutable tags such as `latest` alone must not be trusted. Pin digests (or version tag + verified digest).

## Signing

- Public key: `packaging/keys/release-signing.pub` (committed)
- Private key: GitHub Actions secret `IFILM_RELEASE_SIGNING_KEY` only
- Algorithm: Ed25519 via `openssl pkeyutl` (`-rawin` required on modern OpenSSL)
- Disposable test releases may be published with `packaging/scripts/build_and_publish_test_release.sh` using `IFILM_RELEASE_SIGNING_KEY_FILE` when the Actions secret cannot be written by the automation token

Never log or commit private key material.
