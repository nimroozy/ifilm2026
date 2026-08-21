# CDN Management v1

## Architecture

The admin control plane manages three independent concerns:

1. Cloudflare R2 is an optional private hot tier in the existing `object_storage` architecture, and can also publish **public artwork/trailers** when `ENABLE_ARTWORK_CDN_SYNC` is on (see `docs/media/ARTWORK_CDN_R2.md`). Access and secret keys are Fernet-encrypted with `INTEGRATION_SECRETS_KEY`; APIs return only `credentials_configured`, plus non-secret fields `public_base_url` and `artwork_cdn_enabled`.
2. `managed_cdn_nodes` stores Main CDN and Cache inventory, desired cache limits, safe lifecycle state and secret-free health metrics. SSH passwords or private keys are encrypted in a dedicated binary column and never returned.
3. `cdn_prefix_routes` maps canonical IPv4/IPv6 CIDRs to preferred nodes. Selection sorts by prefix length descending, priority ascending, then node name. When no enabled, healthy route applies, the logical default Main CDN is selected.

Protected playback remains in the existing streaming/branch-cache path. Storage credentials are never sent to browsers. Edge delivery continues to use short-lived, package/path-bound signed grants. `ENABLE_CDN_SYNC` remains false in production and `cdn_sync.py` is not used. Full movies are never published to the public artwork CDN base URL.

## API summary

- `GET|PUT /api/admin/cdn-management/r2`
- `GET|POST /api/admin/cdn-management/nodes`
- `PATCH|DELETE /api/admin/cdn-management/nodes/{id}`
- `POST /api/admin/cdn-management/nodes/{id}/test-ssh`
- `POST /api/admin/cdn-management/nodes/{id}/actions/{provision|reprovision|upgrade|drain|disable|clear-cache}`
- `GET /api/admin/cdn-management/nodes/{id}/provision-runs`
- `GET|POST /api/admin/cdn-management/routes`
- `PATCH|DELETE /api/admin/cdn-management/routes/{id}`
- `POST /api/admin/cdn-management/routes/lookup`

Read APIs require `cdn.read`; mutations require `cdn.manage`; R2 settings require `settings`. Delete and operational action endpoints require explicit confirmation.

## Provisioning flow

1. Admin saves a target and an encrypted bootstrap credential.
2. Test SSH performs a bounded reachability probe without exposing credentials.
3. Provision requires an explicitly confirmed SHA-256 SSH host-key pin and creates an auditable queued run. A privileged isolated worker validates DNS/IP (rejecting loopback, link-local, multicast and unspecified targets), verifies the pinned host key and signed release, and invokes `packaging/cdn/install_debian13.sh`.
4. The idempotent Debian 13 script installs minimal packages, creates the non-login `ifilm-cdn` user, writes a root-owned configuration, installs a hardened systemd service and verifies it is active. The one-time enrollment credential is then rotated to key-based authentication.
5. A one-time node heartbeat token is returned once and stored centrally only as a SHA-256 hash. Authenticated heartbeats populate disk, RTT, cache, bandwidth, sync and version fields. Central routing excludes disabled/draining nodes.

## Production hardening still required

This pass intentionally supplies an injectable provisioning runner and queued control-plane workflow with mocked safety tests; it does not run live SSH from the web process. Before production, deploy the executor as a separately privileged worker, upgrade heartbeat bearer tokens to the existing mTLS node-identity protocol, publish a signed branch-cache artifact URL, and add a real Debian 13 staging end-to-end test. Firewall policy must be rendered from the operator-approved management and serving CIDRs rather than guessed by the installer.
