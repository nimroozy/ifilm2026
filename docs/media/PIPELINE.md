# iFilm Media Pipeline (canonical)

**Baseline:** v1.14.2+  
**Status:** Source of truth for Train T0 — platform hardening  
**Related:** `HLS_ENCODING_PIPELINE.md`, `MEDIA_PROCESSING_FOUNDATION.md`, `STREAMING_SERVICE.md`, `UPLOAD_FOUNDATION.md`

This document must match runtime behavior. Logical states are derived from existing columns (`canonical_media_state`); T0 adds **no** new status column or migration.

---

## Single processing path

```
Upload
  →
Media Asset
  →
Probe
  →
Track Association
  →
Encode
  →
Package
  →
Publish
  →
Stream
```

| Step | Owner (service / worker) | Runtime entry |
|------|--------------------------|---------------|
| Upload | `backend-api` | `POST /api/admin/media/sessions` → chunk PUT → finalize |
| Media Asset | `backend-api` | `media_assets` row + file under `MEDIA_ROOT/<category>/` |
| Probe | `media-processing-worker` | Job `job_type=probe` (`FOR UPDATE SKIP LOCKED`) |
| Track Association | `backend-api` (admin) | `media_tracks` + optional sidecar assets; may set `requires_repackage` |
| Encode | `media-processing-worker` | Job `job_type=encode_hls` (ffmpeg ABR + alt audio/subs) |
| Package | `media-processing-worker` | `media_packages` validate → promote → activate |
| Publish | `backend-api` + `publishing-worker` | Catalog workflow / due scheduled publish |
| Stream | `backend-api` (+ nginx) | `POST /api/playback/sessions` → `/api/stream/{token}/…` |

**Object storage / hybrid CDN:** Phase 1 foundation + Phase 2 optional origin sync/read-fallback (`docs/media/HYBRID_CDN_FOUNDATION.md`, `docs/media/HYBRID_CDN_PHASE2.md`). Flags default off; encode still promotes local `MEDIA_ROOT` first. Experimental `ENABLE_CDN_SYNC` remains quarantined.

**Compose workers (production / staging):**

| Service | Docker profile | Role |
|---------|----------------|------|
| `media-processing-worker` | **always-on** (no profile; label `ifilm.pipeline.role=canonical`) | probe + encode_hls |
| `publishing-worker` | **always-on** (label `ifilm.pipeline.role=canonical`) | scheduled publish |
| `worker` (ARQ / EncodingJob) | **absent** in prod/staging; local only via profile `legacy-arq` | quarantined legacy |

---

## Canonical states — transitions, failure, retry, owner

| State | Meaning | Allowed transitions | Failure | Retry | Owner |
|-------|---------|---------------------|---------|-------|-------|
| `uploaded` | Finalize complete; on disk; not probed | → `probing`, → `failed` | Upload finalize / virus-sniff / missing file → `failed` | Re-upload new session (no auto-retry of finalize) | `backend-api` |
| `probing` | Probe job `queued` / `running` / `retry_wait` | → `ready`, → `failed`, → `probing` (retry_wait) | Permanent probe errors → `failed`; cancel → cancelled/`failed` for ops | Transient: `retry_wait` with exponential backoff until `max_attempts` (`MEDIA_PROCESSING_*`) | `media-processing-worker` |
| `ready` | `probed_at` set; tracks optional; encode eligible | → `encoding`, → `ready` (track edits), → `failed` | N/A at rest | Admin may re-queue probe/encode | `backend-api` (tracks) |
| `encoding` | `encode_hls` active or package `pending\|encoding\|validating\|promoting` | → `packaged`, → `failed`, → `encoding` (retry_wait) | Permanent encode/validate errors → package + asset `failed` | Transient: same job retry policy as probe | `media-processing-worker` |
| `packaged` | Active completed HLS package | → `published`, → `encoding` (`requires_repackage`), → `failed` | Supersede on replace; disk orphans cleaned later (T2+) | Re-encode creates new package | `media-processing-worker` |
| `published` | Packaged **and** catalog entity published | → `packaged` (unpublish), stream eligible | Publish validation failures stay unpublished | Publishing-worker retries due schedules per its loop | `publishing-worker` / admin publish APIs |
| `failed` | Terminal failure on upload, probe, or encode | → `probing` / `encoding` via admin retry/requeue | Terminal until operator action | Admin retry endpoints / new job | operator + owning worker |

### Job status (probe / encode_hls)

```
queued → running → completed
                 ↘ failed
                 ↘ cancelled
queued|running → retry_wait → (eligible) → running
```

- **Transient** (timeout, worker death, temporary I/O): `retry_wait`, delay `MEDIA_PROCESSING_RETRY_BASE_SECONDS * 2^(attempt-1)`, up to `MEDIA_PROCESSING_MAX_ATTEMPTS`
- **Permanent** (missing file, path escape, corrupt media): immediate `failed`
- **Cancel**: `queued`/`retry_wait` → `cancelled`; `running` → `cancel_requested` then terminate process group

### Package status (encode path)

`pending` → `encoding` → `validating` → `promoting` → `completed` (+ activate)  
Failures / cancel → `failed` / `cancelled` (never left `is_active`)

### Stored-field mapping

| Canonical | Signals |
|-----------|---------|
| `uploaded` | `upload_status ∈ {completed,stored}`, `probed_at IS NULL`, no active probe |
| `probing` | Active probe job in `queued\|running\|retry_wait` |
| `ready` | `probed_at` set; no active encode; no active completed package (or `requires_repackage`) |
| `encoding` | Active `encode_hls` or package in encode/validate/promote |
| `packaged` | Active `media_packages.status=completed` |
| `published` | `packaged` + catalog publish state published |
| `failed` | `upload_status=failed` or `processing_status=failed` or job/package `failed` |

Helper: `app.services.media_processing.lifecycle.canonical_media_state`.

---

## Legacy path (quarantined)

| Legacy | Behavior |
|--------|----------|
| `UploadJob` / `EncodingJob` models | DB compat only |
| `POST /api/admin/uploads*` | Still feature-flagged (`ENABLE_UPLOADS`); **must not** spawn EncodingJob in prod/staging |
| `GET/POST /api/admin/encoding/*` | **Hard-blocked** when `APP_ENV ∈ {production,prod,staging}` → HTTP 503 clear error |
| ARQ `process_encoding_job` | Returns `{ok:false, error:legacy_encoding_blocked}` — never silently “completes” media |
| Compose `worker` (`arq …`) | Local profile `legacy-arq` only; **not defined** in production/staging compose |

Flags:

- `ENABLE_ENCODING` — default `false`; **ignored** when env is production/staging (hard block wins)  
- `ENABLE_MEDIA_PROCESSING` + `ENABLE_HLS_ENCODING` — real pipeline  

Legacy “completed” EncodingJobs **do not** write playable HLS packages.

**Test contract:** submitting a legacy encoding job in production/staging = blocked safely with an explicit error (no package side effects).

---

## Invariants (must not break)

1. Multi-audio / subtitle packaging (`media_tracks` → `#EXT-X-MEDIA`)  
2. Session-proxied streaming — tokens never in nginx access logs  
3. Shared media mounts (including `audio`) between API and media-processing-worker  
4. Package activate / `requires_repackage` on track changes  
5. Publishing gate before subscriber playability  

---

## Rollback

- Redeploy previous digest-pinned release (no DB migration in T0)  
- Keep nginx log redaction even if rolling back app bits when possible  
- Demo role fixtures only; Super Admin merge remains additive  

---

*End of PIPELINE.md*
