# Hybrid CDN — one-node staging runbook (Phase 9)

**Mode:** offline plan/render only. No merge, deploy, live network, or credentials.

**Dependency order:** #81 → #82 → #83 → #84 → #85 → #86 → #87 → #88 → Phase 9

## Operator checklist

1. Copy `packaging/compose/one-node-staging-fixtures/inventory.v1.example.json` and replace placeholders (still non-secret).
2. Record immutable image digest, SBOM/provenance refs, origin hostname, pinned IPv4, DNS evidence ID, cert fingerprints, cache device/path, capacity, approval record ID.
3. Run preflight (read-only):

```bash
cd app/backend
python -m app.services.branch_cache.deploy.cli plan --inventory /path/to/inventory.json --out /tmp/preflight.json
```

4. Render artifacts:

```bash
python -m app.services.branch_cache.deploy.cli render --inventory /path/to/inventory.json --out /tmp/staging-render
python -m app.services.branch_cache.deploy.cli drift --inventory /path/to/inventory.json --work /tmp/staging-drift
```

5. Review firewall-egress.plan.md, canary-shadow.plan.json, rollback.plan.json, staging-render-manifest.v1.json.
6. **Stop.** Do not apply firewall rules, do not `docker compose up`, do not enable flags, do not publish ports.

## Go / no-go matrix

| Gate | Go | No-go |
|------|----|-------|
| Inventory schema valid, `environment=staging-candidate` | ✓ | production/unknown fields/mutable tag |
| Immutable digest + fingerprints present | ✓ | missing digest/fingerprints |
| Bind 127.0.0.1, UID 10001, flags false | ✓ | public bind / root / flags true |
| DNS stable and matches pinned IP | ✓ | multi-A / rebinding / mismatch |
| Cert metadata (expiry, EKU, perms) | ✓ | missing/symlink/open key perms |
| Disk/time-sync/FD/PID/memory | ✓ | below inventory limits |
| Operator approval record ID | ✓ | missing/placeholder-only without review |
| Manifest signature | placeholder only | treat as incomplete — refuse apply |
| Client redirect / live pilot | always false | any true value |

## Evidence required (redacted)

- Preflight JSON (`secrets_and_identifiers_redacted`)
- Render manifest SHA-256 + artifact hashes
- DNS evidence ID (not zone dumps with credentials)
- Approval record ID
- Canary bounds (bytes/duration/allowlist) — synthetic only

## Exact remaining live inputs

- Approved staging hostname/IP  
- Server login  
- Operator CA / client cert / key mounts  
- DNS record  
- Cloudflare/R2 account (if ever used)  
- Real credentials  
- Reviewed egress application  
- Future remote-apply mechanism (out of Phase 9)

Portal/SAS and central `/api/stream/{token}` remain unchanged. No Alembic migration in Phase 9.
