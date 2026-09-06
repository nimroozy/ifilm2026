# CDN Management (CDN-P1)

**Status:** CDN-P1 — management, provisioning, node runtime, routing rules. Customer playback is unchanged.
**Edge playback (CDN-P2):** not implemented. `ENABLE_CDN_EDGE_ROUTING` must stay `false`; startup validation rejects it.

## Architecture

```
Admin (ifilm.af/admin)                     Central iFilm backend
  Settings → Storage / R2  ───────────►  integration_configs (provider=cloudflare_r2, Fernet secrets)
  CDN → Servers / Routing  ───────────►  managed_cdn_nodes · cdn_prefix_routes · cdn_provision_runs
                                                  │
                     python -m app.workers.cdn_provisioning (privileged, opt-in)
                                                  │  SSH (paramiko, pinned host key, argv-only commands)
                                                  ▼
                                    Debian 13 node: ifilm-cdn.service
                                    python -m app.services.cdn_node serve
                                    /health /ready /metrics /v1/obj/{asset}/{pkg}/…
                                                  │  heartbeat every 30 s (node token)
                                                  │  pull-through fills from
                                                  ▼
                              GET /api/cdn/origin/{asset}/{pkg}/{path}  (node token, sha256, size cap)
```

Three independent concerns:

1. **Storage / R2** (`Admin → Settings → Storage / R2`): provider (`cloudflare_r2` | `s3_compatible`), endpoint, bucket, region, object key prefix, credentials. Secrets are Fernet-encrypted with `INTEGRATION_SECRETS_KEY`; APIs return only `credentials_configured`. Blank keys preserve the stored secret; *Replace Secret* sends both keys; *Test Connection* records `reachable`, `bucket_accessible`, `last_test_at`, `last_test_message`. Requires `cdn.secrets` (legacy `settings` admins keep access).
2. **Managed nodes** (`managed_cdn_nodes`, authoritative production registry). `branch_cache_nodes` (Phase 3) stays lab-only and is never consulted for production decisions.
3. **Prefix routes** (`cdn_prefix_routes`) with the routing engine in `app/services/cdn_routing.py`.

The legacy `cdn_sync.py` / `/api/admin/cdn/*` remain quarantined; `ENABLE_CDN_SYNC` stays `false`.

## Flags (all default `false`)

| Flag | Purpose |
|------|---------|
| `ENABLE_CDN_NODE_API` | Node-facing `/api/cdn/*`: authenticated heartbeat + central origin pull |
| `ENABLE_CDN_PROVISIONING` | Privileged provisioning worker (never inside the web container) |
| `ENABLE_CDN_EDGE_ROUTING` | CDN-P2 only. Rejected by startup validation in CDN-P1 |

Related settings: `CDN_CENTRAL_BASE_URL` (https, reachable by nodes), `CDN_MANAGEMENT_CIDRS`, `CDN_SERVE_CIDRS`, `CDN_NODE_SERVE_PORT` (8443), `CDN_NODE_HEARTBEAT_STALE_SECONDS` (90), `CDN_ORIGIN_MAX_OBJECT_BYTES`.

## Permissions

| Permission | Grants |
|------------|--------|
| `cdn.read` | Overview, servers, routes, health, lookups |
| `cdn.manage` | Create/edit/delete servers; drain, undrain, enable, disable |
| `cdn.provision` | Test SSH, pin host key, provision, re-provision, upgrade, clear cache, rotate node token |
| `cdn.routing` | Create/edit/delete prefix rules |
| `cdn.secrets` | Storage / R2 settings and connection test |

`cdn.manage` and bare `cdn` satisfy all of the above; `settings` also satisfies `cdn.secrets`.

## Admin API

- `GET|PUT /api/admin/cdn-management/r2`, `POST …/r2/test`
- `GET …/status`, `GET …/overview`
- `GET|POST …/nodes`, `GET|PATCH|DELETE …/nodes/{id}` (delete needs `?confirm=true`)
- `POST …/nodes/{id}/test-ssh`, `POST …/nodes/{id}/pin-host-key`
- `POST …/nodes/{id}/actions/{provision|reprovision|upgrade|drain|undrain|disable|enable|clear-cache}` (body `{"confirm": true}`)
- `GET …/nodes/{id}/provision-runs`, `POST …/nodes/{id}/heartbeat-token`
- `GET|POST …/routes`, `PATCH|DELETE …/routes/{id}`, `POST …/routes/lookup`

Node-facing (flag `ENABLE_CDN_NODE_API`, headers `Authorization: Bearer <node token>` + `X-Ifilm-Node-Id`):

- `POST /api/cdn/nodes/{id}/heartbeat` → metrics in, desired state (`draining`, limits) out
- `GET|HEAD /api/cdn/origin/{asset_id}/{package_id}/{relative_path}` → package object bytes with `X-Ifilm-Sha256`

## Provisioning flow (fresh Debian 13)

1. *Add server*: name, role (`MAIN_CDN` | `CACHE`), host, SSH port/user, bootstrap password or key (encrypted), storage limit, watermarks, priority, serve base URL.
2. *Test SSH*: authenticated probe (bounded timeouts) returning the observed host-key fingerprint, OS release, sudo availability and disk. Nothing is changed on the host.
3. *Pin host key*: explicit confirmation. Provisioning and all later SSH refuse unpinned or changed keys.
4. *Provision*: queues a `cdn_provision_runs` row. The worker claims it (`SKIP LOCKED` on PostgreSQL) and runs idempotent steps: `preflight` (Debian 13, root/sudo, arch, disk) → `packages` → `user_dirs` (`ifilm-cdn`, `/var/lib/ifilm-cdn/cache`, `/etc/ifilm-cdn`) → `bundle` (versioned tarball built from this checkout, SHA-256 verified before extraction, venv + `requirements-branch-cache.txt`) → `config` (`/etc/ifilm-cdn/node.env` 0640 root:ifilm-cdn with a freshly issued node token; edge-grant public key if configured) → `systemd` (hardened unit) → `firewall` (nftables default-deny inbound: SSH from `CDN_MANAGEMENT_CIDRS`, media port from `CDN_SERVE_CIDRS`; checked with `nft -c` before apply) → `start` → `verify` (`/health`, `/ready` over loopback) → `collect` (disk, version) → `rotate_key` (generate ed25519 key, install to `authorized_keys`, verify key login on a fresh connection, only then encrypt the private key centrally and retire the bootstrap credential) → `finalize` (`provision_status=ready`).
5. A failed run records `step`, `error_code`, and a redacted log; the next *Provision* resumes from the failed step. *Re-provision* runs everything again; *Upgrade* re-installs the bundle/config; *Clear Cache* stops, wipes the cache root, restarts.

Secrets (passwords, private keys, node tokens) never appear in argv, run logs, exceptions, DB logs or API responses; every recorded line passes through `redact_log`.

`packaging/cdn/install_debian13.sh` is the manual equivalent for hosts that must be installed by hand.

## Node runtime

`ENABLE_CDN_NODE_SERVICE=true` (set only in `/etc/ifilm-cdn/node.env`) starts `app.services.cdn_node`. It refuses to start with any central secret in the environment, reuses the branch-cache data plane (public-key grant verification, confined cache store, single-flight fills, checksum validation, LRU eviction between the configured watermarks) with `CentralHttpOriginFetcher` (fixed https base, no redirects, no proxy trust, size cap, `X-Ifilm-Sha256` check) and a heartbeat thread. Without an edge-grant public key `/v1/obj/*` answers `503 edge_grants_not_configured`; health, ready and metrics still work so the node can be managed before CDN-P2.

## Routing engine

1. Longest matching CIDR prefix wins. 2. Equal prefix length: lower `priority` number wins, then node name. 3. Ineligible preferred node → next eligible matching rule. 4. → eligible cache in the same branch as the preferred node. 5. → default Main CDN → secondary Main CDN nodes by priority. 6. → central iFilm `/api/stream` (always present, always eligible).

Eligibility: enabled, not draining, `provision_status=ready`, heartbeat within `CDN_NODE_HEARTBEAT_STALE_SECONDS`, no failed health state. The admin routing tester shows the client IP, matched CIDR, selected node and the full chain with reasons. In CDN-P1 the decision is informational only.

## Playback security (unchanged in CDN-P1)

Subscribers still authenticate, pass entitlement checks, and stream through `/api/stream/{token}/…`. No edge URL, grant, or renewal endpoint exists on the customer path. Buckets stay private; nodes pull through central, never from storage directly. CDN-P2 will add the routing decision, short-lived ES256 edge grants (`app/services/branch_cache/grants.py`) and player fallback after CDN-P1 passes staging with one real Debian 13 node.

## Staging checklist for the first real node

1. Set `INTEGRATION_SECRETS_KEY`, `CDN_CENTRAL_BASE_URL=https://<central>`, `ENABLE_CDN_NODE_API=true` on the API; run `docker compose --profile cdn up cdn-provisioning-worker` with `ENABLE_CDN_PROVISIONING=true` and `CDN_MANAGEMENT_CIDRS` including the central egress IP.
2. Add the Debian 13 server, Test SSH, pin the fingerprint after out-of-band verification, Provision.
3. Confirm the node shows `ONLINE` within 60 s, disk/version populated, `Health / Metrics` updating, and the routing tester selecting it for its CIDR.
4. Keep `ENABLE_CDN_EDGE_ROUTING=false`. Do not expose the node media port beyond `CDN_SERVE_CIDRS`.
