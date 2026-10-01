# Production Architecture Audit — iFilm v1.14.2

**Date:** 2026-08-09  
**Baseline:** production `v1.14.2` (`d90cbe1`) · Alembic head `023_media_tracks_packaging_v1`  
**Scope:** backend, frontend, deployment — read-only audit (no implementation in this document)  
**Companion docs:** `COMPLETE_AUDIT.md`, `FIX_PLAN.md`, `SECURITY_AUDIT.md`

---

## 1. Current architecture

### 1.1 Request path

```
Client (SPA / player)
  → nginx (TLS, reverse proxy)
  → FastAPI (/api/*) + optional SPA static
  → deps auth (admin JWT | subscriber JWT)
  → routes → services → SQLAlchemy → PostgreSQL
  → Redis (optional queue / cache; required when REDIS_REQUIRED=true)

Workers (same backend image, digest-pinned):
  media-processing-worker  → claim SKIP LOCKED → probe | encode_hls
  publishing-worker        → due scheduled entities → publish
  arq worker (legacy)      → UploadJob / EncodingJob / CDN (feature-flagged)
```

### 1.2 Media pipeline (production-intended)

```
Admin upload session → finalize (SHA256, sniff, durable move)
  → probe (ffprobe)
  → media_tracks (optional multi audio/subs)
  → encode-hls → package promote/activate
  → publishing workflow (draft → review → approved → published)
  → POST /playback/sessions → /api/stream/{token}/…
```

Multi-track packaging (v1.14.x): video-only ABR + alternate AAC audio HLS + WebVTT subtitle HLS; single master with `#EXT-X-MEDIA`. Single-track muxed path retained when no tracks configured.

### 1.3 Customer surfaces

| Surface | Implementation |
| --- | --- |
| Home | Aggregated `/api/catalog/home` or `/api/me/home`; batched card serializers |
| Browse | `/api/movies`, `/api/series` with card batching |
| Detail | Movie hero + cast strip + similar; series weaker |
| Player | `/player/movie|episode|asset/:id` — HLS + audio/subtitle selectors + resume |
| Search | `GET /api/search?q=` — ILIKE title/original/director/slug |
| Recs / watchlist / CW / content requests | Present and production-verified on v1.13–v1.14 |

### 1.4 Deployment

- Signed release manifest + GHCR digest-pinned images
- Host dirs under `/var/lib/ifilm/media/{originals,trailers,subtitles,audio,posters,backdrops,packages,temp}`
- `ifilm-update-agent` UDS install / verify / application-only rollback
- Feature flags for uploads/processing/HLS/streaming (prod enables media stack)

---

## 2. Problems (by area)

### Backend

| ID | Problem | Risk | Recommended fix | Priority |
| --- | --- | --- | --- | --- |
| B1 | Dual media pipelines: real HLS jobs vs legacy arq `EncodingJob` that can “complete” without packages | High | Disable/remove legacy encode path in prod compose; gate routes; document single pipeline | Critical |
| B2 | Search serializes each hit via `movie_out`/`series_out` (N+1 playability/credits/i18n) | High | Batch search cards like browse (`movies_card_out`) | Critical |
| B3 | Continue Watching / history N+1 package + content lookups per row | High | Batch active packages + content fetch | Critical |
| B4 | Watchlist serialize N+1 `db.get` per item | High | Batch load movies/series by id | High |
| B5 | Publishing worker sets `status=approved` outside `transition()` on readiness failure | High | Use workflow transition / shared helper | High |
| B6 | Admin movie list uses unbatched `movie_out` | Medium | Reuse card/batch serializers | High |
| B7 | In-process rate limits (not Redis-shared) | Medium | Shared limiter or edge rate limit | Medium |
| B8 | Home shelf fan-out (~8 queries) intentional but above “&lt;2 API calls” product target | Medium | Further aggregate / edge cache | Medium |
| B9 | Missing composite indexes for job claim `(status, priority, queued_at)` and scheduled publish `(status, scheduled_publish_at)` | Medium | Add targeted composites | Medium |
| B10 | Probe not auto-queued after upload finalize | Medium | Optional auto-probe on complete | Medium |
| B11 | Docs drift (`PRODUCTION_READINESS.md` still describes placeholder encoding / old heads) | Low | Refresh docs to v1.14.2 | Low |

### Frontend

| ID | Problem | Risk | Recommended fix | Priority |
| --- | --- | --- | --- | --- |
| F1 | React Query mounted but unused — remount refetch, no shared cache | High | Adopt Query for home/detail/search/browse | Critical |
| F2 | Movie detail waits on similar waterfall before paint | High | Defer similar below fold / parallelize | Critical |
| F3 | Admin artwork is URL-only (“uploads disabled” UX); no resize/WebP/thumbs | High | Artwork upload pipeline + CMS tab | Critical |
| F4 | Admin media tracks UI thin (counts, not track editor) | High | Track editor + package diagnostics | High |
| F5 | Browse `page_size: 100` without infinite scroll | Medium | Paginate / virtualize | High |
| F6 | Search: no URL sync, filters, cast search, FTS | Medium | Search v2 (see FIX_PLAN) | High |
| F7 | Cast strip non-linkable; no `people` entity / `/person/:id` | Medium | People system | High |
| F8 | Series detail lagging movie detail | Medium | Unify detail shell | Medium |
| F9 | Tokens in `localStorage` (XSS-dependent) | Medium | Prefer httpOnly cookies longer-term | Medium |
| F10 | TV/remote not ready (no spatial nav / 10-foot targets) | Low | Focus architecture prep only | Medium |

### Deployment / ops

| ID | Problem | Risk | Recommended fix | Priority |
| --- | --- | --- | --- | --- |
| D1 | Application-only rollback (schema forward-only) | High | Document DB backup restore; test migration downgrade on staging | High |
| D2 | Stale update-agent job can leave lock semantics confusing | Medium | Job TTL / clear stuck `restarting` | Medium |
| D3 | Update-agent socket mode historically permissive | Medium | Tighten socket ACLs | Medium |
| D4 | Nginx still sourced from staging tree in prod compose | Medium | Promote dedicated prod nginx tree | Medium |
| D5 | Audio mount was missing until v1.14.1 — mount contract tests exist; keep green | Low | Preserve compose contract tests | Critical (preserve) |

---

## 3. What must not break

1. Digest-pinned images + signed release manifest  
2. Shared media mounts including **audio** (API ↔ media-processing-worker)  
3. Packages: API RO / worker RW  
4. Session-tokenized `/api/stream/` only — no public originals/packages  
5. Multi-audio / subtitle HLS + legacy single-track muxed path  
6. Watch history / CW / recommendations / watchlist / content requests  
7. EN/FA/PS localization + player forced LTR  
8. Publishing workflow + readiness gates  
9. Worker healthchecks that do **not** curl API `:8000`  
10. Update-agent verify / rollback path  

---

## 4. Media pipeline health (post–v1.14.2)

| Stage | Status |
| --- | --- |
| Upload | Solid (dedupe, sniff, categories including audio) |
| Probe | Solid for A/V + subtitle-only (v1.14.2) |
| Encode / package | Solid multi-track + muxed fallback |
| Publish | Solid matrix; worker edge case B5 |
| Stream | Solid packaged HLS; Option A external is unprotected by design |
| Ops UX | Weak — no first-class admin diagnostics page for asset/package/retry |

---

## 5. Database observations

**Strong:** checksum uniqueness, one active HLS package, active job uniqueness, watch progress uniqueness, translation lookup index, playback `token_hash` unique.

**Gaps:** claim/schedule composites (B9); search uses `ILIKE` (no FTS/GIN); single-column index sprawl on movies/series; cast credits denormalized per title (no shared `people` table).

---

## 6. Priority summary

| Priority | Themes |
| --- | --- |
| Critical | Legacy pipeline isolation; search/CW/watchlist N+1; React Query + detail waterfall; artwork upload CMS |
| High | Publishing worker transition; admin media diagnostics; search v2; people system; browse pagination |
| Medium | Indexes; rate-limit sharing; series detail parity; TV prep; nginx/prod polish |
| Low | Docs sync; stub admin pages cleanup |

**Next:** see `FIX_PLAN.md` for itemized solutions. Do not start large feature trains until Critical items are scheduled.
