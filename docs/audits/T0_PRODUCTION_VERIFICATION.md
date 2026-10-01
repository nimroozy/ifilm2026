# T0 Production Verification — v1.14.3

**Date:** 2026-08-09  
**Train:** Platform hardening + security  
**Status:** **PASSED** — T1 may start after this report is accepted  

Artifacts: `/opt/cursor/artifacts/v1143-prod/`

---

## Merge

| Item | Value |
|------|-------|
| PR | [#66](https://github.com/nimroozy/ifilm2026/pull/66) |
| Squash title | `chore: harden media pipeline and security baseline` |
| Merge SHA | `f6fb581a8ae3a9e15f0761aa95bb32c0475bb98b` |
| Mergeable / CI | MERGEABLE · Backend / Frontend / Installer green |
| Review threads | none |
| Migrations | **none** (head remains `023_media_tracks_packaging_v1`) |
| UI changes | **none** |

### Confirmed on `main`

- `docs/media/PIPELINE.md`
- Nginx + app log redaction (`deploy/staging/nginx/*`, `logging_filters.py`)
- Legacy EncodingJob gate (`legacy_encoding.py`, upload/encoding/ARQ)
- RBAC demo fixtures + tests
- Compose worker guards (`test_compose_worker_profiles.py`, labels)

---

## Release

| Item | Value |
|------|-------|
| Version | **v1.14.3** |
| Tag / workflow | https://github.com/nimroozy/ifilm2026/actions/runs/31307669386 |
| Release | https://github.com/nimroozy/ifilm2026/releases/tag/v1.14.3 |
| Commit | `f6fb581a8ae3a9e15f0761aa95bb32c0475bb98b` |
| Migration head | `023_media_tracks_packaging_v1` (unchanged) |
| Channel | `stable` |
| Rollback support | `application_only` → prior **1.14.2** |

### Assets present

- `release-manifest.json` + `.sig` (signed)
- `ifilm-1.14.3.tar.gz`
- `SHA256SUMS`
- `ifilm-1.14.3-backend.sbom.spdx.json` / frontend SBOM
- `backend-trivy.json` / `frontend-trivy.json`

### Digests deployed

| Service | Digest |
|---------|--------|
| backend-api / media-processing / publishing | `sha256:ec2b3d5baf696d21537e8de4f6c803403d31b2c4b40c859e21cbd2666b0ce1da` |
| frontend | `sha256:8c0a2b4d33b74b31b1933a26513e6c79193587b399f7c4919051a58e65608c09` |

---

## Production deploy

Deployed via **ifilm-update-agent** only (`install_verified_release`).

| Check | Result |
|-------|--------|
| Preflight | ok (1.14.2 → 1.14.3, signature verified) |
| Install job | `5514798e5b007d9d` **completed** |
| `verify_installation` | ok · digests consistent · health ready |
| Backup id | `pre-update-20260809T101938Z` |

### Service health (all healthy)

| Service | Status |
|---------|--------|
| backend-api | healthy |
| frontend | healthy |
| nginx | healthy |
| postgres | healthy |
| redis | healthy |
| media-processing-worker | healthy |
| publishing-worker | healthy |

No ARQ / legacy `worker` container running.

---

## Nginx security verification

Controlled playback: movie **39** → `POST /api/playback/sessions` → `GET /api/stream/{token}/master.m3u8` (HTTP **200**).

Access logs (`docker logs ifilm-nginx-1`; file is symlink to stdout):

```
GET /api/stream/[REDACTED]/master.m3u8 HTTP/1.1" 200
```

| Assert | Result |
|--------|--------|
| Path shows `[REDACTED]` | **PASS** |
| Raw playback token absent | **PASS** |
| Query `token=` / `expires=` stripped on test request | **PASS** |
| Running nginx.conf has `$loggable_uri` map | **PASS** |

### Application logs

Tail of `ifilm-backend-api-1` checked for admin password, playback token, `JWT_SECRET=`, `PLAYBACK_TOKEN_SECRET=`, `tmdb_api_key=` → **no hits**.

---

## Legacy pipeline verification

| Check | Result |
|-------|--------|
| `GET /api/admin/encoding/jobs` | **503** — `Legacy EncodingJob path is disabled in production; use media-processing encode_hls (see docs/media/PIPELINE.md)` |
| `POST /api/admin/encoding/jobs/1/retry` | **503** |
| `ENABLE_ENCODING` | `false` |
| `APP_ENV` | `production` |

### Canonical pipeline smoke (new asset)

1. Generated 1s MP4 (`t0tiny.mp4`, 12KB)  
2. Upload session finalize → asset `a5f00d76-ae20-4fbd-9f77-a4989fd3f547`  
3. Probe → `completed` / `probed_at` set  
4. `encode-hls` → active package `completed` (240p, 1 rendition)  

Publish path confirmed via existing published movie **39** (playback session + stream 200). Full catalog publish workflow unchanged (no migration).

---

## RBAC production check

Demo fixture matrix loaded in running image: **ok**.

Ephemeral role users (cleaned after):

| Role | Action | HTTP |
|------|--------|------|
| Catalog Manager | create upload session | **403** |
| Reviewer | create media track | **403** |
| Publisher | delete media asset | **403** |
| Media Manager | list media assets | **200** |
| Super Admin (`admin`) | list media assets | **200** |

---

## Secret scan

| Check | Result |
|-------|--------|
| Frontend CI `scan:build-secrets` | green on PR #66 |
| Release SBOM + Trivy assets published | yes |
| Prod app log secret spot-check | clean |

---

## Rollback procedure

1. Admin System updates → Roll Back (or update-agent `rollback_last_update`) to **1.14.2**  
2. Digests return to prior release; **no DB rollback** required  
3. Prefer keeping nginx log redaction if rolling app only  

`verify_installation` reported `rollback_target`: **1.14.2**.

---

## Remaining risks

1. **Option A external CDN URLs** remain shareable without session (documented; deferred hardening).  
2. **Nginx access.log → stdout** — operators must use `docker logs` (not `tail` inside container on the symlink).  
3. **Production Super Admin** permissions are additive merges; demo least-privilege fixtures apply to demo/seed roles, not automatically rewrite existing custom prod roles.  
4. **Catalog N+1 / Redis caching** still open — scheduled for **T1** only after this verification acceptance.

---

## Gate

| Gate | Status |
|------|--------|
| Pipeline documented | ✓ |
| Legacy processing blocked in prod | ✓ |
| Stream tokens protected in logs | ✓ |
| RBAC verified in prod | ✓ |
| Canonical upload→probe→package | ✓ |
| CI / release / deploy healthy | ✓ |
| No migration / no UI | ✓ |

**T1 (DB + N+1 + Redis cache strategy) may start only after this report is accepted. No CMS / UI trains yet.**

---

*End of T0_PRODUCTION_VERIFICATION.md*
