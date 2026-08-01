# Administrator: production signing secret setup

Environment: **`production-release`**  
Secret name: **`IFILM_RELEASE_SIGNING_KEY`**

## Current blocker (observed in Actions)

Release run diagnostics (no secret material printed):

```text
signing_key_bytes=19
signing_key_has_begin_private=False
signing_key_has_end_private=False
```

A usable Ed25519 PKCS#8 PEM is ~119 bytes and includes:

```text
-----BEGIN PRIVATE KEY-----
-----END PRIVATE KEY-----
```

**19 bytes matches the filename `release-signing.pub`.** The Environment secret currently looks like a placeholder/path, not the private key PEM. Please delete and re-create it.

## Required PEM format

```text
-----BEGIN PRIVATE KEY-----
...base64...
-----END PRIVATE KEY-----
```

Do **not** store:

- the public key (`release-signing.pub`)
- the fingerprint
- a file path / filename
- a password

Public fingerprint (SHA-256 of DER public key):

```text
8c04b9141a9fe72346edf9e1f6bc27b0fbef3dc728d6e61124fb897e74ac1e26
```

## Re-set from file (recommended)

On a secure admin workstation that has the private key PEM:

```bash
gh secret set IFILM_RELEASE_SIGNING_KEY \
  --repo nimroozy/ifilm2026 \
  --env production-release \
  < /path/to/IFILM_RELEASE_SIGNING_KEY.pem
```

Cloud-agent staged copy on the verification VM (mode 600):

```text
/opt/cursor/artifacts/signing/IFILM_RELEASE_SIGNING_KEY.pem
```

Base64 of that same PEM (artifact only, not in git):

```text
/opt/cursor/artifacts/signing/IFILM_RELEASE_SIGNING_KEY.pem.b64
```

After setting, shred local copies (`shred -u`). Never commit the private key.

## Verify

Re-run / retag `v0.1.4-candidate`. Publish step **Build and sign manifest** must log:

- `signing_key_bytes` around `119` (not `19`)
- `signing_key_has_begin_private=True`
- `signing_key_has_end_private=True`
- `manifest_signed=true`

Logs must never contain PEM body lines.

## Key rotation / emergency revocation

See `packaging/keys/README.md`.
