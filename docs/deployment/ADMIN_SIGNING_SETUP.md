# Administrator: production signing secret setup

Environment: **`production-release`**  
Secret name: **`IFILM_RELEASE_SIGNING_KEY`**

## Emergency rotation (2026-08-01)

The previous production private key was **exposed and is permanently compromised**.

- Revoked fingerprint: `8c04b9141a9fe72346edf9e1f6bc27b0fbef3dc728d6e61124fb897e74ac1e26`
- Current fingerprint: `e7b365230a5b360f417532cba134fdb91eaa73b814163f3175a3f13d28286612`
- Details: `docs/deployment/KEY_ROTATION_EMERGENCY_2026-08-01.md`

**Delete the old Environment secret value and set only the new PEM.**

## Required PEM format

```text
-----BEGIN PRIVATE KEY-----
...base64...
-----END PRIVATE KEY-----
```

Do **not** store the public key, a fingerprint, a filename, or the revoked key.

## Downloadable package (Cursor VM artifact)

The Cursor VM GitHub token cannot write Environment secrets (403). Use:

```text
/opt/cursor/artifacts/signing/download/IFILM_RELEASE_SIGNING_KEY.pem
```

Integrity helpers (no private key body):

```text
/opt/cursor/artifacts/signing/download/INTEGRITY.txt
/opt/cursor/artifacts/signing/download/release-signing.pub
/opt/cursor/artifacts/signing/download/PUBLIC_KEY_SHA256.txt
/opt/cursor/artifacts/signing/download/README_SET_SECRET.txt
```

Expected: PEM **~119 bytes**; public fingerprint  
`e7b365230a5b360f417532cba134fdb91eaa73b814163f3175a3f13d28286612`.

## Set from file on your Mac

```bash
gh secret set IFILM_RELEASE_SIGNING_KEY \
  --repo nimroozy/ifilm2026 \
  --env production-release \
  < ./IFILM_RELEASE_SIGNING_KEY.pem
```

Then tell the agent to re-run `v0.1.4-candidate`.

## Verify without printing the secret

Publish step **Build and sign manifest** must log:

- `signing_key_bytes` around `119`
- `signing_key_has_begin_private=True`
- `signing_key_has_end_private=True`
- `manifest_signed=true`

Logs must never contain PEM body lines.

## Key rotation / emergency revocation

See `packaging/keys/README.md` and `KEY_ROTATION_EMERGENCY_2026-08-01.md`.
