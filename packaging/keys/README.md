# Release signing keys

## Production identity

| Item | Value |
| --- | --- |
| Algorithm | Ed25519 |
| Public key (committed) | `packaging/keys/release-signing.pub` |
| Public key fingerprint (SHA-256 of DER) | `8c04b9141a9fe72346edf9e1f6bc27b0fbef3dc728d6e61124fb897e74ac1e26` |
| Private key location | GitHub Actions Environment secret `IFILM_RELEASE_SIGNING_KEY` in Environment `production-release` only |
| Bootstrap trust anchor | Fingerprint embedded in `install.sh` as `IFILM_RELEASE_PUBLIC_KEY_SHA256` |

Never commit the private key. Never print key PEM contents in CI logs.

## Administrator setup (required before any signed production release)

The automation token used by agents cannot create repository environments or secrets (403/404). A repository administrator must:

1. GitHub → Settings → Environments → create **`production-release`**
2. Enable **Required reviewers** (manual approval) when the plan supports it
3. Restrict the Environment to the `Release` workflow / version-tag deployments if available
4. Add Environment secret **`IFILM_RELEASE_SIGNING_KEY`** with the full Ed25519 private key PEM
5. Confirm a workflow run on a version tag successfully signs `release-manifest.json`

Until the secret is configured, do **not** merge PR #14 and do **not** weaken signing.

## Key rotation

1. Generate a new Ed25519 keypair offline (`openssl genpkey -algorithm Ed25519`)
2. Compute the public DER SHA-256 fingerprint
3. Open a PR that updates `release-signing.pub`, `install.sh` fingerprint constant, and this README
4. After merge, replace `IFILM_RELEASE_SIGNING_KEY` in `production-release`
5. Publish a new signed release; revoke trust in the old public key by removing it from `main`

## Emergency revocation

1. Remove or rotate `IFILM_RELEASE_SIGNING_KEY` immediately
2. Delete or mark untrusted any GitHub Releases signed with the compromised key
3. Land a PR replacing the committed public key + install.sh fingerprint
4. Notify operators to refuse updates until they pull the new public key / reinstall bootstrap
