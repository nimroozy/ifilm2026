# iFilm Fix Plan

**Baseline:** v1.14.2 (`d90cbe1`)  
**Status:** Awaiting approval before implementation  
**Companion docs:** [`COMPLETE_AUDIT.md`](./COMPLETE_AUDIT.md) · [`PRODUCTION_AUDIT.md`](./PRODUCTION_AUDIT.md) · [`SECURITY_AUDIT.md`](./SECURITY_AUDIT.md)

---

## Approval gate

**Do not start implementation until this plan is explicitly approved.**

After approval, implement in trains (one PR train per approved bucket), never breaking:

- HLS multi-audio / subtitles / packaging  
- Protected streaming / Option A CDN  
- Watch history / continue watching  
- Recommendations / watchlist / content requests  
- Localization EN/FA/PS  
- Deployment / update-agent / rollback  

---

## Priority legend

| Priority | Meaning |
|----------|---------|
| **Critical** | Correctness, security, or production ops risk — fix before large feature trains |
| **High** | Clear product/performance debt blocking Netflix-class UX |
| **Medium** | Important quality improvements; schedule after Critical/High |
| **Low** | Nice-to-have / future platform |

Complexity: **S** (small, localized) · **M** (multi-file, possible migration) · **L** (cross-cutting) · **XL** (platform program)

---

## Critical

### C1 — Retire / quarantine legacy encoding path

| Field | Detail |
|-------|--------|
| **Problem** | Dual pipelines: arq `encode_media_job` + Redis `media_jobs` HLS packaging. Legacy path can confuse ops and create inconsistent states. |
| **Impact** | Failed/orphan jobs; wrong mental model; risk of “encode succeeded” without playable HLS. |
| **Solution** | Document single source of truth (HLS packaging). Disable or hard-gate legacy arq encode in production compose. Add admin media diagnostics that only surface the real pipeline. Migrate any remaining callers. |
| **Files** | `app/backend/worker/tasks.py`, `app/backend/services/queue.py`, `app/backend/services/media_pipeline/*`, `deploy/docker-compose*.yml`, docs |
| **Migration** | Possibly none; optional job-table cleanup script |
| **Complexity** | M |

### C2 — Nginx must not log stream tokens

| Field | Detail |
|-------|--------|
| **Problem** | Access logs may capture `/api/stream/...` query tokens. |
| **Impact** | Credential leakage via log aggregation / backups. |
| **Solution** | Map `$loggable_uri` stripping `token`/`expires`; apply to stream locations; rotate existing logs if tokenful. |
| **Files** | `deploy/nginx/*.conf`, installer templates, ops runbook |
| **Migration** | No DB |
| **Complexity** | S |

### C3 — Search N+1 elimination

| Field | Detail |
|-------|--------|
| **Problem** | Per-result translation + artwork + genres queries. |
| **Impact** | Search latency grows with result count; DB load spikes. |
| **Solution** | Batch-load translations/artwork/genres; single response assembly; add instrumentation (query count before/after). |
| **Files** | `app/backend/routers/catalog.py` (search), catalog services, possibly schema helpers |
| **Migration** | No (indexes optional under H2) |
| **Complexity** | M |

### C4 — Continue-watching / watchlist N+1

| Field | Detail |
|-------|--------|
| **Problem** | Per-row title/artwork/progress enrichment. |
| **Impact** | Home and library endpoints slow under load. |
| **Solution** | Bulk fetch titles + artwork; reuse home-rails patterns; measure SQL count before/after. |
| **Files** | `app/backend/routers/watch.py`, `watchlist.py`, related services |
| **Migration** | No |
| **Complexity** | M |

### C5 — Admin playback least privilege (IDOR hardening)

| Field | Detail |
|-------|--------|
| **Problem** | Broad admin playback/session paths may allow cross-title access beyond role intent. |
| **Impact** | Broken access control risk for staff accounts. |
| **Solution** | Scope session create/playback to content the admin is allowed to manage; audit all admin media/stream helpers; add tests for negative cases. |
| **Files** | Admin media/catalog routers, `services/streaming/*`, authz helpers |
| **Migration** | No |
| **Complexity** | M |

---

## High

### H1 — Admin media diagnostics page

| Field | Detail |
|-------|--------|
| **Problem** | No single admin view for asset/probe/package/fail/retry/last-processed. |
| **Impact** | Slow incident response; opaque packaging failures. |
| **Solution** | Admin page + API: asset status, probe status, package status, failed reason, retry, last processing time. Read-only safe by default; retry requires confirm. |
| **Files** | New admin route/page, backend admin media diagnostics endpoints, packaging services |
| **Migration** | No (uses existing tables) |
| **Complexity** | M |

### H2 — Necessary composite indexes only

| Field | Detail |
|-------|--------|
| **Problem** | Missing composites for job claim and scheduled publish; some redundant uniques already covered. |
| **Impact** | Worker contention / scheduled publish scans. |
| **Solution** | Add indexes for `(status, available_at, priority, created_at)` on jobs; `(status, publish_at)` on titles if confirmed by `EXPLAIN`. Benchmark query counts. **Do not** add speculative indexes. |
| **Files** | New Alembic migration, models |
| **Migration** | **Yes** |
| **Complexity** | S |

### H3 — CMS artwork upload pipeline

| Field | Detail |
|-------|--------|
| **Problem** | Artwork is URL-centric; no first-class upload → validate → resize → WebP → thumbs. |
| **Impact** | Inconsistent images; large originals; weak CMS. |
| **Solution** | Movie editor Artwork tab: upload poster/backdrop/logo/gallery; server-side validation, resize, WebP, thumbnails; store as media assets + artwork rows. |
| **Files** | Admin movie editor UI, upload routers, image processing service, artwork models/API |
| **Migration** | Possibly artwork asset FK / storage path fields |
| **Complexity** | L |

### H4 — Movie editor CMS (tabs)

| Field | Detail |
|-------|--------|
| **Problem** | Admin is operational, not a full CMS. |
| **Impact** | Slow content ops; URL-only workflows. |
| **Solution** | Movie editor with tabs: Basic Info, Artwork, Metadata (TMDB refresh/cast/crew/translations/similar), Media (video/audio/subs/packages/encoding), Publishing (draft/review/published/scheduled). |
| **Files** | Admin frontend movie routes/components; admin catalog APIs; TMDB sync services |
| **Migration** | Maybe publishing workflow fields if incomplete |
| **Complexity** | L |

### H5 — Movie detail page V2 (customer)

| Field | Detail |
|-------|--------|
| **Problem** | Detail page not Netflix/Disney+ grade; similar-title waterfall; mobile secondary. |
| **Impact** | Weak conversion to play; poor mobile UX. |
| **Solution** | Hero (backdrop, title, rating, year, duration, genres, play, trailer, watchlist) + overview, A/V availability, cast carousel, director, similar, collections, recommendations. Mobile-first. Batch/aggregate detail API to cut waterfall. |
| **Files** | `TitleDetailPage` / movie route, CSS, backend detail/similar endpoints |
| **Migration** | No |
| **Complexity** | L |

### H6 — People / cast system

| Field | Detail |
|-------|--------|
| **Problem** | Credits denormalized; no `people` table or `/person/{id}`. |
| **Impact** | No cast discovery; duplicate names; weak search by person. |
| **Solution** | Tables `people`, `movie_people`, `series_people`; migrate from JSON credits; customer person page; admin linkage from Metadata tab. |
| **Files** | Models, migration, routers, frontend `/person/:id`, TMDB sync |
| **Migration** | **Yes** (data backfill) |
| **Complexity** | L |

### H7 — Streaming search (FTS + filters)

| Field | Detail |
|-------|--------|
| **Problem** | ILIKE-only; no cast/year/language filters; weak multilingual. |
| **Impact** | Poor discovery for EN/FA/PS catalog. |
| **Solution** | PostgreSQL FTS (or equivalent) on title/original/translated; filters genre/year/language; cast via people join; keep response shape stable for SPA. |
| **Files** | Search service/router, migration for `tsvector`/GIN, frontend search UI |
| **Migration** | **Yes** |
| **Complexity** | L |

### H8 — Localization publish workflow

| Field | Detail |
|-------|--------|
| **Problem** | Risk of request-time translation; incomplete field coverage. |
| **Impact** | Inconsistent FA/PS; latency/cost if on-demand ever reintroduced. |
| **Solution** | Enforce pipeline: TMDB EN → translation engine → admin review → published. Cover title, overview, tagline, genres, collections, cast roles. Never translate on customer request. |
| **Files** | Translation services, admin review UI, catalog read paths, workers |
| **Migration** | Maybe translation status enums |
| **Complexity** | L |

### H9 — React Query adoption for catalog reads

| Field | Detail |
|-------|--------|
| **Problem** | React Query installed but unused; ad-hoc fetch + context. |
| **Impact** | Duplicate requests; harder cache invalidation. |
| **Solution** | Migrate home, detail, search, watchlist, CW to React Query with shared keys; keep Auth/Player contexts. |
| **Files** | Frontend hooks/pages, `main.tsx` QueryClient defaults |
| **Migration** | No |
| **Complexity** | M |

### H10 — Home payload / API call budget

| Field | Detail |
|-------|--------|
| **Problem** | Home may exceed &lt;2 API call target; large rails payloads. |
| **Impact** | Slow LCP on mobile. |
| **Solution** | Aggregate home endpoint or parallelize to ≤2 calls; slim DTOs; defer secondary rails; measure payload + LCP. |
| **Files** | Home router/page, DTO shaping |
| **Migration** | No |
| **Complexity** | M |

### H11 — Option A CDN URL exposure policy

| Field | Detail |
|-------|--------|
| **Problem** | Direct CDN URLs for HLS may be shareable without app session. |
| **Impact** | Hotlinking / off-platform viewing (accepted tradeoff today, but undocumented). |
| **Solution** | Document threat model; optional short-lived CDN signed URLs or cookie gate on CDN edge as Phase-2 hardening. |
| **Files** | Streaming service, CDN config, SECURITY docs |
| **Migration** | No |
| **Complexity** | M–L (depending on CDN features) |

### H12 — Upload validation hardening

| Field | Detail |
|-------|--------|
| **Problem** | MIME allowlists improved (v1.14.1) but image/artwork uploads need same rigor (size, magic bytes, path safety). |
| **Impact** | Malicious/oversized uploads; storage abuse. |
| **Solution** | Shared upload validator for media + artwork; reject path traversal; quarantine on probe failure. |
| **Files** | Upload routers, `services/security` validators, artwork pipeline |
| **Migration** | No |
| **Complexity** | M |

---

## Medium

### M1 — Media package state machine documentation + guards

| Field | Detail |
|-------|--------|
| **Problem** | Transitions mostly correct but not centrally documented/tested. |
| **Impact** | Regression risk when adding tracks/features. |
| **Solution** | Explicit state diagram in docs; unit tests for invalid transitions; worker rejects invalid jobs. |
| **Files** | Packaging services, worker claim logic, docs |
| **Migration** | No |
| **Complexity** | M |

### M2 — Orphan file cleanup job

| Field | Detail |
|-------|--------|
| **Problem** | Failed/superseded packages may leave disk orphans. |
| **Impact** | Disk growth on `/data/media`. |
| **Solution** | Scheduled cleanup for unreferenced package dirs + unused uploads after grace period; dry-run mode; mount_health awareness. |
| **Files** | Worker tasks, admin ops endpoint, storage helpers |
| **Migration** | No |
| **Complexity** | M |

### M3 — Duplicate upload / content-hash handling

| Field | Detail |
|-------|--------|
| **Problem** | Duplicate files may create duplicate assets. |
| **Impact** | Wasted storage/encode time. |
| **Solution** | Optional content hash dedupe on ingest; link existing asset when hash matches. |
| **Files** | Upload + asset services |
| **Migration** | Maybe `content_hash` column/index |
| **Complexity** | M |

### M4 — Storage health accuracy

| Field | Detail |
|-------|--------|
| **Problem** | Mount health exists; may not reflect package/orphan pressure. |
| **Impact** | False healthy while disk filling. |
| **Solution** | Extend health with free space thresholds + package dir stats. |
| **Files** | `mount_health`, admin diagnostics |
| **Migration** | No |
| **Complexity** | S |

### M5 — Genre / collection translation completeness

| Field | Detail |
|-------|--------|
| **Problem** | Not all catalog fields equally localized. |
| **Impact** | Mixed-language UI in FA/PS. |
| **Solution** | Inventory missing fields; backfill via translation workflow (H8). |
| **Files** | Translation models, admin CMS, catalog serializers |
| **Migration** | Maybe |
| **Complexity** | M |

### M6 — Player performance instrumentation

| Field | Detail |
|-------|--------|
| **Problem** | Startup/manifest timing not systematically measured. |
| **Impact** | Hard to defend multi-audio regressions. |
| **Solution** | Client metrics: session create → manifest → first frame; optional backend timing logs (no tokens). |
| **Files** | Player, stream session service |
| **Migration** | No |
| **Complexity** | S |

### M7 — Smart TV / leanback architecture prep (no apps)

| Field | Detail |
|-------|--------|
| **Problem** | No focus management / spatial nav / TV design tokens. |
| **Impact** | Future TV apps will fork SPA painfully. |
| **Solution** | Introduce `platform` capability layer, focusable primitives, large-card density tokens, TV-safe player control map — **architecture only**. |
| **Files** | Frontend design system stubs, docs/architecture/TV_READY.md |
| **Migration** | No |
| **Complexity** | M |

### M8 — Secrets / CI inventory refresh

| Field | Detail |
|-------|--------|
| **Problem** | Secrets many; ensure no secret in git; rotate runbooks stale. |
| **Impact** | Ops risk. |
| **Solution** | Document required secrets matrix; verify `.gitignore`; no new plaintext in repo. |
| **Files** | Docs, CI workflows (read-only audit) |
| **Migration** | No |
| **Complexity** | S |

### M9 — Recommendations SQL efficiency pass

| Field | Detail |
|-------|--------|
| **Problem** | Personalized recs may join heavily. |
| **Impact** | Home latency. |
| **Solution** | `EXPLAIN ANALYZE` on prod-like data; add only proven indexes; cache rail TTL. |
| **Files** | Recommendations service, optional migration |
| **Migration** | Maybe |
| **Complexity** | M |

### M10 — Content requests admin UX polish

| Field | Detail |
|-------|--------|
| **Problem** | Feature works; admin triage UX thin vs CMS ambitions. |
| **Impact** | Ops friction. |
| **Solution** | Tie requests into CMS movie create flow when approved. |
| **Files** | Admin requests + movie editor |
| **Migration** | No |
| **Complexity** | S |

---

## Low

### L1 — Profiles / kids / parental (roadmap P1)

| Field | Detail |
|-------|--------|
| **Problem** | Single user surface; no kids profile. |
| **Impact** | Family UX gap vs Netflix. |
| **Solution** | Profile model, kids mode, PIN parental controls — **after** P0 CMS/detail/search/people. |
| **Files** | New domain models, auth, frontend shell |
| **Migration** | **Yes** |
| **Complexity** | XL |

### L2 — Offline downloads (roadmap P1)

| Field | Detail |
|-------|--------|
| **Problem** | No offline. |
| **Impact** | Mobile competitiveness. |
| **Solution** | Download licenses + packaged files for apps — depends on mobile clients. |
| **Files** | New subsystem |
| **Migration** | **Yes** |
| **Complexity** | XL |

### L3 — TV / mobile native apps (roadmap P2)

| Field | Detail |
|-------|--------|
| **Problem** | Web-only. |
| **Impact** | Living-room / store distribution. |
| **Solution** | After M7 architecture prep; separate app trains. |
| **Files** | New repos/apps |
| **Migration** | API versioning likely |
| **Complexity** | XL |

### L4 — Payments / subscriptions (roadmap P2)

| Field | Detail |
|-------|--------|
| **Problem** | Monetization not in scope of current catalog product. |
| **Impact** | Business model. |
| **Solution** | Separate billing domain; do not entangle with media pipeline. |
| **Files** | New billing service |
| **Migration** | **Yes** |
| **Complexity** | XL |

### L5 — Broader OpenAPI / typed client generation

| Field | Detail |
|-------|--------|
| **Problem** | Frontend types partly hand-maintained. |
| **Impact** | Drift. |
| **Solution** | Generate client from OpenAPI for catalog/admin. |
| **Files** | CI, frontend `api/` |
| **Migration** | No |
| **Complexity** | M |

---

## Suggested implementation trains (post-approval)

Execute only after sign-off. Order preserves must-not-break constraints.

| Train | Items | Goal |
|-------|-------|------|
| **T0 — Stabilize** | C1, C2, C5, M1 | Pipeline clarity + security hygiene |
| **T1 — DB/Perf** | C3, C4, H2, H10, M9 | Query counts down; home &lt;2 calls target |
| **T2 — Media CMS** | H1, H3, H4, H12, M2–M4 | Real CMS + diagnostics |
| **T3 — Customer UX** | H5, H9 | Movie detail V2 + React Query |
| **T4 — People + Search** | H6, H7 | Cast pages + FTS search |
| **T5 — i18n** | H8, M5 | Publish-only translations |
| **T6 — Platform prep** | M6, M7, M8 | Metrics + TV architecture |
| **Later** | L1–L5, H11 | Profiles, apps, payments, CDN signing |

---

## Missing Netflix features roadmap (summary)

### P0 (next product trains)

1. CMS artwork upload (H3) + movie editor (H4)  
2. Admin media diagnostics (H1)  
3. Movie detail redesign (H5)  
4. Search improvement (H7)  
5. Cast / people pages (H6)  

### P1

- Profiles  
- Kids mode  
- Parental controls  
- Offline downloads  

### P2

- Android TV / Apple TV / Samsung / LG apps  
- Mobile apps  
- Payments  
- Subscriptions  

---

## Benchmark plan (for T1)

Before/after for each changed endpoint:

| Endpoint | Metrics |
|----------|---------|
| `GET` search | SQL query count, p95 latency, payload bytes |
| Continue watching | SQL query count, p95 |
| Watchlist | SQL query count, p95 |
| Home | API call count from SPA, SQL count, payload, LCP |
| Movie detail | API waterfall depth, image bytes (thumb vs original) |

Record in `docs/audits/benchmarks/` when implementation starts.

---

## Explicit non-goals until approval

- No schema migrations in this PR  
- No CMS/UI redesign code  
- No people table  
- No FTS  
- No TV apps  
- No behavior change to packaging / stream tokens / update-agent  

This PR delivers **audit + plan only**.

---

## Approval checklist

- [ ] Scores in `COMPLETE_AUDIT.md` accepted  
- [ ] Critical/High ordering accepted or reordered  
- [ ] Confirm CDN Option A stance (accept risk vs H11)  
- [ ] Confirm train T0→T6 sequencing  
- [ ] Explicit “approve implementation of train T*” message  

---

*End of FIX_PLAN.md*
