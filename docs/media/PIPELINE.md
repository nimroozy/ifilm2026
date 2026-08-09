# iFilm Media Pipeline (canonical)

**Baseline:** v1.14.2+  
**Status:** Source of truth for Train T0 — platform hardening  
**Related:** `HLS_ENCODING_PIPELINE.md`, `MEDIA_PROCESSING_FOUNDATION.md`, `STREAMING_SERVICE.md`, `UPLOAD_FOUNDATION.md`

---

## Single processing path

Production and staging use **one** media pipeline. There is no second encode path.

```
Upload
  ↓
Asset
  ↓
Probe
  ↓
Track association (optional multi-audio / subtitles)
  ↓
Encode (ffmpeg HLS via media-processing-worker)
  ↓
Package (validate → promote → activate)
  ↓
Publish (catalog workflow)
  ↓
Stream (session-proxied /api/stream/{token}/…)
```

| Step | Implementation |
|------|----------------|
| Upload | `POST /api/admin/media/sessions` → chunk PUT → finalize (`MediaAsset`) |
| Asset | `media_assets` row; durable file under `MEDIA_ROOT/<category>/` |
| Probe | Job `probe` claimed by `media-processing-worker` |
| Track association | `media_tracks` (+ sidecar audio/subtitle assets) |
| Encode | Job `encode_hls` → ABR video + optional alt audio/subs |
| Package | `media_packages` / renditions under `MEDIA_ROOT/packages/` |
| Publish | Publishing worker / admin workflow (`draft` → … → `published`) |
| Stream | `POST /api/playback/sessions` → tokenized HLS delivery |

**Workers (production compose):**

- `media-processing-worker` — probe + encode_hls (canonical)  
- `publishing-worker` — scheduled publish  
- **No** ARQ `EncodingJob` worker in production/staging

---

## Canonical object states

Logical lifecycle for ops and diagnostics (mapped onto existing columns — **no new status column required for T0**):

| Canonical state | Meaning |
|-----------------|---------|
| `uploaded` | Upload finalized; file on disk; not yet usefully probed |
| `probing` | Probe job queued/running/retry_wait |
| `ready` | Probe completed; tracks may be attached; eligible to encode |
| `encoding` | encode_hls job or package in encoding/validating/promoting |
| `packaged` | Active completed HLS package exists |
| `published` | Linked catalog title/episode is published (playable to entitled subscribers) |
| `failed` | Upload, probe, or encode terminal failure (or cancelled where treated as failed for ops) |

### Mapping to stored fields

| Canonical | Typical signals |
|-----------|-----------------|
| `uploaded` | `upload_status ∈ {completed, stored}` and `processing_status ∈ {none}` and `probed_at IS NULL` |
| `probing` | Active `media_processing_jobs` with `job_type=probe` in `queued\|running\|retry_wait`, or `processing_status=processing` during probe |
| `ready` | `probed_at` set; no active encode; no active completed package (or `requires_repackage`) |
| `encoding` | Active `encode_hls` job, or package `status ∈ {pending, encoding, validating, promoting}`, or `processing_status ∈ {queued, processing, retry_wait}` for encode |
| `packaged` | Active `media_packages` with `status=completed` |
| `published` | `packaged` **and** owning movie/episode/series publishing status is published |
| `failed` | `upload_status=failed` or `processing_status=failed` or latest relevant job/package `failed` |

Helper: `app.services.media_processing.lifecycle.canonical_media_state`.

---

## Legacy path (quarantined)

These exist only for historical/dev compatibility and **must not run in production**:

| Legacy | Status |
|--------|--------|
| `UploadJob` / `EncodingJob` models | Retained for DB compat |
| `POST /api/admin/uploads*` | Feature-flagged; **hard-blocked** when `APP_ENV` is `production` or `staging` |
| `POST /api/admin/encoding/*` | Same hard block |
| ARQ `process_encoding_job` | No-ops / refuses outside explicit legacy-dev allow |
| Compose service `worker` (`arq …`) | Opt-in profile `legacy-arq` on local compose; **absent** from production compose |

Flags:

- `ENABLE_ENCODING` — defaults `false`; ignored/blocked in production & staging  
- `ENABLE_MEDIA_PROCESSING` + `ENABLE_HLS_ENCODING` — real pipeline  

If a job “completes” on the legacy path it **does not** create playable HLS packages. Real packages only come from `encode_hls`.

---

## Invariants (must not break)

1. Multi-audio / subtitle packaging (`media_tracks` → `#EXT-X-MEDIA`)  
2. Session-proxied streaming (`/api/stream/{token}/…`) — tokens never in nginx access logs  
3. Shared media mounts (including `audio`) between API and media-processing-worker  
4. Package activate / `requires_repackage` on track changes  
5. Publishing gate before subscriber playability  

---

## Rollback

T0 hardening is flag- and config-level:

- Revert nginx log_format / maps  
- Re-enable legacy only in local `legacy-arq` profile (never production)  
- Role permission seed changes affect **demo fixtures** and documentation; production Super Admin merge remains additive  

---

*End of PIPELINE.md*
