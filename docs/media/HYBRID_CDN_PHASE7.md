# Hybrid CDN Phase 7 — hardened CI/lab branch-node artifact

**Status:** Flag-gated; defaults **OFF**  
**Stacked on:** `cursor/hybrid-cdn-phase6-branch-service-candidate-4873` (PR #86)  
**Branch:** `cursor/hybrid-cdn-phase7-branch-artifact-hardening-4873`  
**Dependency order:** #81 → #82 → #83 → #84 → #85 → #86 → Phase 7

## Boundary

**In scope**
- Dedicated `Dockerfile.branch-cache.lab` (multi-stage, non-root UID/GID `10001`, minimal deps)
- Lab ASGI entry `app.services.branch_cache.service.asgi` + `--validate-only` (no socket bind)
- Separate LAB-ONLY compose: `packaging/compose/docker-compose.branch-cache.lab.yml`
  - `network_mode: none`, no ports, read-only root, `cap_drop: ALL`, `no-new-privileges`
  - dedicated cache volume + bounded tmpfs; public key + origin fixtures only
- Static hardening / contract tests in packaging + backend
- SBOM/provenance **hooks documented** (Syft/Trivy/signing placeholders); not added to production release digests

**Deferred**
- Real deployment, production/staging activation, live networking / mTLS sockets (Phase 8 packages mTLS offline; live activation still deferred)
- Node enrollment live issuance, public port, DNS/Cloudflare/R2/MinIO/Ceph, client redirects, live pilot
- Publishing the lab image via `release.yml` / installer digests

## Flags (all default false)

| Flag | Purpose |
|------|---------|
| `ENABLE_BRANCH_CACHE_HTTP_LAB_ARTIFACT` | Entrypoint gate for the lab/CI container (rejected in staging/production) |
| (Phase 6) `ENABLE_BRANCH_CACHE_HTTP_SERVICE` | Must also be true for the lab entry |
| Health/metrics/HTTPS adapter flags | Remain false by default; lab compose keeps them false |

## Artifact contract

| Property | Requirement |
|----------|-------------|
| User | `10001:10001` |
| Bind | `127.0.0.1` only (public bind refused) |
| Network (lab compose) | `network_mode: none`; no `ports:` |
| Secrets | No private signing key, DB/Redis/JWT/Portal/SAS/cloud credentials in env or image |
| Origin | Fixed `BRANCH_CACHE_ORIGIN_ROOT` directory only — no arbitrary URLs |
| Production compose / installer | Unreferenced; flags forced `false` |
| Release digests | Not included (`image_refs.py` unchanged) |

## Hardening guidance

- Drop all capabilities; `no-new-privileges`; read-only root FS; writable cache volume + `/tmp` tmpfs only
- Prefer docker-default seccomp; AppArmor `docker-default` where available
- Resource suggestions (lab compose): 1 CPU, 512Mi memory, 256 PIDs
- Graceful stop: `STOPSIGNAL SIGTERM` → app lifespan starts shutdown/drain
- Immutable digests: when an image is built in CI, record digest locally; do not pin into installer
- SBOM: `syft ifilm-branch-cache-lab:local -o spdx-json > branch-cache.lab.sbom.spdx.json`
- Vuln scan: `trivy image ifilm-branch-cache-lab:local` (CI-optional; not a production gate)
- Provenance/signing: reuse release Ed25519 workflow **only** if product later opts into a non-install digest channel

## Reproducibility

- `requirements-branch-cache.txt` pins the minimal dependency set (no DB/Redis/boto)
- Multi-stage build; no `.env` baked into the image
- Validate-only entry enables offline smoke without host port binds

## Rollback / removal (lab only)

1. Keep all flags false (default).
2. Do not add the lab compose file to installer `up`.
3. Remove local lab image/volume: `docker compose -f packaging/compose/docker-compose.branch-cache.lab.yml down -v` and `docker rmi ifilm-branch-cache-lab:local` if present.
4. Delete only the lab cache volume / test temp roots — never production `MEDIA_ROOT`.

## Threat model (delta)

| Risk | Mitigation |
|------|------------|
| Accidental production activation | Separate compose file; installer/prod flags false; startup rejects prod-like env |
| Credential leakage into branch image | Entrypoint forbids credential env; slim requirements; public key only |
| Host network / docker socket | Contract tests forbid; lab compose uses `network_mode: none` |
| Importing customer DB stack | Lazy `branch_cache` package init; import audit test |

Central `/api/stream/{token}` and Portal/SAS authentication are unchanged.
