# Hybrid CDN Phase 9 — one-node staging deploy candidate (plan/render only)

**Status:** Flag-gated; defaults **OFF**; **no remote apply**  
**Stacked on:** `cursor/hybrid-cdn-phase8-mtls-staging-candidate-4873` (PR #88)  
**Branch:** `cursor/hybrid-cdn-phase9-one-node-staging-deploy-candidate-4873`  
**Dependency order:** #81 → #82 → #83 → #84 → #85 → #86 → #87 → #88 → Phase 9

## Boundary

**Implemented in-repo (this PR)**
- Versioned non-secret staging inventory schema `ifilm.branch_node.staging_inventory.v1`
- Read-only preflight/plan CLI (`python -m app.services.branch_cache.deploy.cli plan`)
- Deterministic render of compose override, systemd drop-in, firewall/canary/rollback plans, signed-hash manifest **placeholder**
- Idempotence + drift detection
- Offline canary/shadow plan (0% client redirects)
- Rollback/removal **plan** limited to candidate service + validated staging cache root
- Contract tests proving no production/installer/release linkage

**Deferred (explicit)**
- Remote execution / apply to any host
- Staging hostname/IP approval, server login, real CA/certs, secret mounts
- DNS records, Cloudflare/R2, live origins, Portal/SAS environments
- Automatic firewall application
- Setting `deployment_authorized=true`, `live_pilot_ready=true`, or any client redirect

## Flags (default false)

| Flag | Purpose |
|------|---------|
| `ENABLE_BRANCH_CACHE_ONE_NODE_STAGING_DEPLOY` | Future apply gate — **always rejected** while Phase 9 is plan/render only |
| `ENABLE_BRANCH_CACHE_HTTP_MTLS_STAGING_CANDIDATE` | Phase 8 mTLS fetcher construct (still false in prod/installer) |

## Package layout

| Path | Role |
|------|------|
| `app/backend/app/services/branch_cache/deploy/inventory.py` | Inventory schema + load/write |
| `.../preflight.py` | Read-only go/no-go plan |
| `.../render.py` | Deterministic artifact render |
| `.../firewall_plan.py` | Default-deny egress PLAN (not applied) |
| `.../canary_plan.py` | Synthetic shadow plan |
| `.../rollback_plan.py` | Drain/stop/restore plan (no destructive exec) |
| `.../drift.py` | Double-render + drift gates |
| `.../cli.py` | `plan` / `render` / `drift` |
| `packaging/compose/one-node-staging-fixtures/inventory.v1.example.json` | Placeholder inventory |

## Security decisions

| Decision | Rationale |
|----------|-----------|
| Inventory `extra=forbid` | Reject unknown fields |
| Immutable `sha256:` digest only | No mutable tags |
| Hostname + pinned reviewed IPv4 | Detect DNS rebinding / multi-A |
| Bind `127.0.0.1`, UID 10001 | No public bind / no root |
| Plan never mutates host | Fail closed without apply mechanism |
| Firewall/canary/rollback are documents | Operator review required |
| Signing signature placeholder `REQUIRED:` | Incomplete inputs refuse plan success |

## Remaining live deployment inputs

1. Approved staging hostname/IP and server login  
2. Operator CA + client certificate/key material (mounted; fingerprints match inventory)  
3. Secret mounts under `/run/ifilm/certs`  
4. DNS record + reviewed pin evidence  
5. Cloudflare/R2 (if used) — out of scope until explicitly approved  
6. Real credentials / Portal/SAS — unchanged and unused by this package  
7. Human-reviewed egress application (nftables/ufw)  
8. Separately reviewed remote-apply mechanism (not in Phase 9)

## Rollback

Keep flags false. Do not wire rendered override into production compose or installer. Drain candidate; purge only a **validated** dedicated staging cache root after forensic copy — never executed by tests.
