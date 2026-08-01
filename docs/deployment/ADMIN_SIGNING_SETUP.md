# Administrator: production signing secret setup

**BLOCKER until completed.** PR #14 must not merge until this is done and an Actions-signed candidate release verifies.

## Why

The disposable-test Ed25519 private key was shredded. A new long-lived production keypair was generated. The **public** key is committed at `packaging/keys/release-signing.pub`.

Fingerprint (SHA-256 of DER public key):

```text
8c04b9141a9fe72346edf9e1f6bc27b0fbef3dc728d6e61124fb897e74ac1e26
```

The automation token cannot create Environments or secrets (API 403/404). A human administrator must configure GitHub.

## Steps

1. Create GitHub Environment **`production-release`**
2. Enable **Required reviewers** / manual approval if the repository plan supports it
3. Restrict deployment branches/tags to version tags (`v*`) when the UI allows
4. Add Environment secret **`IFILM_RELEASE_SIGNING_KEY`** containing the full Ed25519 **private key PEM**
5. Confirm the secret is present only in `production-release` (not a global repository secret if avoidable)
6. Push tag `v0.1.4-candidate` (or approve the Release workflow run) and verify:
   - workflow creates + signs the manifest
   - SBOMs attach
   - Trivy gate runs without `continue-on-error`
   - GHCR images are referenced as `@sha256:...`
   - private key PEM never appears in logs

## After configuration

Shred any temporary PEM copies on operator machines (`shred -u`). Do not commit the private key.

See also `packaging/keys/README.md` for rotation and emergency revocation.
