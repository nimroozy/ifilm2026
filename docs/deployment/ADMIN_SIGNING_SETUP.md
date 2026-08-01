# Administrator: production signing secret setup

Environment: **`production-release`**  
Secret name: **`IFILM_RELEASE_SIGNING_KEY`**

## Required PEM format

The secret **must** be the full PKCS#8 Ed25519 private key PEM (not the public key, not a fingerprint, not a single-line hash):

```text
-----BEGIN PRIVATE KEY-----
...base64...
-----END PRIVATE KEY-----
```

Public fingerprint (SHA-256 of DER public key) for verification after setup:

```text
8c04b9141a9fe72346edf9e1f6bc27b0fbef3dc728d6e61124fb897e74ac1e26
```

## Recommended: set from file (avoids UI paste corruption)

```bash
# From a secure admin workstation that has the PEM file:
gh secret set IFILM_RELEASE_SIGNING_KEY \
  --repo nimroozy/ifilm2026 \
  --env production-release \
  < /path/to/IFILM_RELEASE_SIGNING_KEY.pem
```

If you previously pasted into the GitHub UI, **delete and re-create** the secret from the PEM file. UI pastes often drop newlines or store the public key by mistake.

Cloud-agent staged copy (this VM only, mode 600):

```text
/opt/cursor/artifacts/signing/IFILM_RELEASE_SIGNING_KEY.pem
```

After setting, shred local copies (`shred -u`). Never commit the private key.

## Verify without printing the secret

1. Push / re-run a version-tag Release workflow (`v0.1.4-candidate`)
2. Confirm job `publish` runs on Environment `production-release`
3. Step **Build and sign manifest** should log:
   - `signing_key_has_begin_private=True`
   - `signing_key_has_end_private=True`
   - `manifest_signed=true`
4. Logs must **not** contain PEM body lines
5. Release assets include `release-manifest.json` + `.sig`

## Key rotation / emergency revocation

See `packaging/keys/README.md`.
