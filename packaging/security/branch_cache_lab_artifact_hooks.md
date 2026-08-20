# Branch-cache lab artifact — SBOM / scan / provenance hooks

Phase 7 does **not** publish `Dockerfile.branch-cache.lab` through
`.github/workflows/release.yml` or `packaging/release/image_refs.py`.

Optional local / CI commands (never required for installer):

```bash
# Build (CI or operator laptop; not installer)
docker build -f app/backend/Dockerfile.branch-cache.lab -t ifilm-branch-cache-lab:local app/backend

# Offline validate (no ports; compose defaults to network_mode:none + validate)
docker compose -f packaging/compose/docker-compose.branch-cache.lab.yml build
docker compose -f packaging/compose/docker-compose.branch-cache.lab.yml run --rm --no-deps branch-cache-lab

# SBOM + vuln hooks (same tools pinned in release.yml when available)
syft ifilm-branch-cache-lab:local -o spdx-json > /tmp/branch-cache.lab.sbom.spdx.json
trivy image --format json -o /tmp/branch-cache.lab.trivy.json ifilm-branch-cache-lab:local
```

Signing/provenance placeholders: if a future non-install channel is approved,
reuse `packaging/release/sign_manifest.py` with an explicit allowlisted image
key — do **not** extend `REQUIRED_IMAGES` without a separate product decision.
