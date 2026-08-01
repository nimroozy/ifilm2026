# Emergency key rotation — 2026-08-01

## Incident

The previous production Ed25519 **private** signing key was exposed and is
**permanently compromised**. It must never be used to sign releases again.

## Revoked identity

| Field | Value |
| --- | --- |
| Algorithm | Ed25519 |
| Revoked public fingerprint (SHA-256 of DER) | `8c04b9141a9fe72346edf9e1f6bc27b0fbef3dc728d6e61124fb897e74ac1e26` |
| Listed in | `packaging/keys/REVOKED_FINGERPRINTS.txt` |
| Bootstrap behavior | `install.sh` hard-rejects this fingerprint |

## Replacement identity

| Field | Value |
| --- | --- |
| Public key file | `packaging/keys/release-signing.pub` |
| Public fingerprint (SHA-256 of DER) | `e7b365230a5b360f417532cba134fdb91eaa73b814163f3175a3f13d28286612` |
| Bootstrap trust anchor | `IFILM_RELEASE_PUBLIC_KEY_SHA256` in `install.sh` |
| Private key | **Not in git.** Administrator sets GitHub Environment secret `IFILM_RELEASE_SIGNING_KEY` (`production-release`) from a secure download only. |

## Why releases signed by the exposed key are rejected

1. Manifest signatures verify against the **current** committed public key; signatures from the revoked private key do not verify.
2. Bootstrap refuses any downloaded public key whose fingerprint is on the revoked list or does not match the embedded trust anchor.
3. Update agent verifies with the installed release’s `packaging/keys/release-signing.pub` from a package that carries the new public key after this rotation lands.

## Required admin steps

1. Delete any local copies of the **old** private key (`shred -u`).
2. Download the **new** private key PEM from the agent artifact package (mode 600). Never paste it into chat/PRs/logs.
3. Replace the Environment secret:

   ```bash
   gh secret set IFILM_RELEASE_SIGNING_KEY \
     --repo nimroozy/ifilm2026 \
     --env production-release \
     < ./IFILM_RELEASE_SIGNING_KEY.pem
   ```

4. Treat prior locally signed / Actions attempts under the revoked fingerprint as untrusted.
5. Re-run tag `v0.1.4-candidate` (or a new candidate) only after the new secret is installed.
6. After a successful Actions-signed release, shred local new-key copies as directed by the agent.

## PR policy

PR #14 remains **Draft** until a workflow-created release signed with the **new** key verifies on a disposable host.
