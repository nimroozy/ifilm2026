# Staging-candidate cert mount layout (Phase 8)
# Replace placeholders with operator-provisioned PEMs at runtime.
# Never commit private keys. App does not generate keys.
# Expected live names (bind-mounted read-only):
#   ca-bundle.pem, client.crt, client.key, edge-grant-public.pem

