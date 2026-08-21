# Hybrid CDN Phase 8 — mTLS staging-candidate (offline / loopback package)

**Status:** Flag-gated; defaults **OFF**  
**Stacked on:** `cursor/hybrid-cdn-phase7-branch-artifact-hardening-4873` (PR #87)  
**Branch:** `cursor/hybrid-cdn-phase8-mtls-staging-candidate-4873`  
**Dependency order:** #81 → #82 → #83 → #84 → #85 → #86 → #87 → Phase 8

## Boundary

**Implemented in-repo (this PR)**
- Strict `MtLsHttpsOriginFetcher` (TLS 1.3+, mTLS, verify required, no redirects, `trust_env=False`)
- Fixed-origin allowlist + DNS/SSRF guards (`origin_allowlist.py`)
- Non-secret enrollment manifest schema (`enrollment/manifest.py`) + rotation guidance
- Staging readiness gates (`ops/staging_gates.py`) — `live_pilot_ready` / `client_redirect_active` always false
- Generated-test-PKI loopback harness + integration tests
- Separate staging-candidate compose (internal network, no public ports); not referenced by production/installer/release

**Deferred (explicit)**
- Live staging/production activation, VPS deploy, DNS/Cloudflare/R2/MinIO/Ceph access
- Real operator certificates/credentials, public ports, client redirects, live pilot
- Any change that sets `deployment_authorized=true`

## Flags (default false)

| Flag | Purpose |
|------|---------|
| `ENABLE_BRANCH_CACHE_HTTP_MTLS_STAGING_CANDIDATE` | Allows constructing the mTLS origin fetcher (rejected in prod-like env by settings validation) |

Phase 6/7 HTTP/lab flags remain false in production compose and installer.

## Security decisions

| Decision | Rationale |
|----------|-----------|
| TLS verify never optional | Fail closed; no plaintext fallback |
| Loopback mTLS only in test/dev/lab | Prevents test PKI / loopback mode outside lab |
| One fixed HTTPS origin | SSRF: no caller-controlled authority |
| Certs mounted, never generated/baked | Private keys stay operator-controlled |
| Enrollment manifest is fingerprints + paths only | No PEM/private material in git or APIs |
| Staging gates ≠ deployment | Human approval + separate deploy step required |
| Origin access logs | Stable `event=` + `correlation_id=` + truncated one-way `object_ref=` hash only — never raw asset/package/path, host, URL, PEM, grant, or exception text |

## Runbook (package → future deploy)

1. Generate/review operator PKI offline; record fingerprints in enrollment manifest.
2. Mount certs read-only; verify permissions (`client.key` ≤ 0600).
3. Run staging gates + mTLS preflight (loopback CI or reviewed staging endpoint).
4. Canary/shadow only; no client redirects.
5. On success: evidence bundle with secrets redacted → human approval.
6. **Stop.** Live activation is out of scope for this PR.

## Rollback

Keep flags false. Do not reference staging-candidate compose from installer. Drain branch node; purge only dedicated cache volume.

## Remaining deployment inputs (not in this PR)

- Reviewed fixed origin hostname/port and network egress policy
- Operator-issued mTLS CA + client cert/key (fingerprints matching manifest)
- Staging host time sync + disk capacity evidence
- Explicit human approval record for a future deploy change

Phase 9 adds an offline **one-node staging deploy package** (inventory/preflight/render/firewall/canary/rollback plans only) stacked on this PR — still no live apply.
