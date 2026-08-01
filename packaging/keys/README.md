# Release signing keys

## Production identity (current)

| Item | Value |
| --- | --- |
| Algorithm | Ed25519 |
| Public key (committed) | `packaging/keys/release-signing.pub` |
| Public key fingerprint (SHA-256 of DER) | `e7b365230a5b360f417532cba134fdb91eaa73b814163f3175a3f13d28286612` |
| Private key location | GitHub Actions Environment secret `IFILM_RELEASE_SIGNING_KEY` in Environment `production-release` only |
| Bootstrap trust anchor | Fingerprint embedded in `install.sh` as `IFILM_RELEASE_PUBLIC_KEY_SHA256` |
| Revoked fingerprints | `packaging/keys/REVOKED_FINGERPRINTS.txt` |

Never commit the private key. Never print key PEM contents in CI logs.

## Emergency key rotation — 2026-08-01

**Status: COMPLETED in repository trust anchors; admin must replace the GitHub Environment secret.**

The previous production Ed25519 private key was **exposed and is permanently compromised**.

| Item | Value |
| --- | --- |
| Revoked fingerprint | `8c04b9141a9fe72346edf9e1f6bc27b0fbef3dc728d6e61124fb897e74ac1e26` |
| Action | Public key replaced; bootstrap fingerprint rotated; revoked list updated |
| Do not use | Any private key material matching the revoked identity |
| Releases signed by revoked key | **Must be rejected** (signature verify against current public key fails; bootstrap rejects revoked fingerprint) |

### Operator actions required

1. **Replace** Environment secret `IFILM_RELEASE_SIGNING_KEY` in `production-release` with the **new** private key PEM only (delete the old secret value first).
2. Treat every GitHub Release / manifest signed under the revoked fingerprint as **untrusted**.
3. Do not install or update from those artifacts.
4. Publish a new Actions-signed candidate only after the new secret is installed.

## Administrator setup

The automation token used by agents cannot write repository/environment secrets (403). An administrator must set `IFILM_RELEASE_SIGNING_KEY` using the new PEM from a secure download (never paste into chat/PRs).

See `docs/deployment/ADMIN_SIGNING_SETUP.md` and `docs/deployment/KEY_ROTATION_EMERGENCY_2026-08-01.md`.

## Planned (non-emergency) rotation

1. Generate a new Ed25519 keypair offline (`openssl genpkey -algorithm Ed25519`)
2. Compute the public DER SHA-256 fingerprint
3. Open a PR that updates `release-signing.pub`, `install.sh` fingerprint, `REVOKED_FINGERPRINTS.txt` (if retiring the previous key), and this README
4. After merge, replace `IFILM_RELEASE_SIGNING_KEY` in `production-release`
5. Publish a new signed release; ensure old fingerprint is listed under revoked if it must never be trusted again

## Emergency revocation checklist

1. Shred all local copies of the compromised private key
2. Remove/replace `IFILM_RELEASE_SIGNING_KEY` immediately
3. Land a PR replacing the committed public key + install.sh fingerprint + revoked list
4. Mark Releases signed by the compromised key as untrusted / delete if appropriate
5. Notify operators to refuse updates until they have the new public key / bootstrap fingerprint
