# Complete Production Audit — iFilm

**Date:** 2026-08-09  
**Production baseline:** **v1.14.2**  
**Commit:** `d90cbe1f76d4cddf2eb3ef9186464f2f78e2c631`  
**Migration head:** `023_media_tracks_packaging_v1`  
**Status:** Audit only — **no implementation until FIX_PLAN approval**

Detail docs:

- `PRODUCTION_AUDIT.md` — architecture / media / DB / UX / deploy  
- `SECURITY_AUDIT.md` — authz, streaming, uploads, secrets  
- `FIX_PLAN.md` — prioritized remediation backlog  

---

## Executive summary

iFilm is a real production streaming stack: digest-pinned deploys, entitlement-gated HLS, multi-audio/subtitle packaging (v1.14.x), publishing workflow, watch history, recommendations, content requests, and EN/FA/PS localization.

It is **not** yet a Netflix-class CMS + discovery product. Gaps cluster around:

1. Admin CMS (artwork upload, media diagnostics, track editing)  
2. Customer discovery (search, people/cast pages, detail polish)  
3. List/search query efficiency (N+1)  
4. Frontend data caching (React Query unused)  
5. Security hardening at the edges (nginx stream logs, Option A URLs, admin least privilege)

**Do not start large feature trains (profiles, TV apps, payments) until Critical/High items in `FIX_PLAN.md` are scheduled.**

---

## Scores (1–10)

| Dimension | Score | Rationale |
| --- | --- | --- |
| **Architecture** | **7.5** | Clear FastAPI + workers + signed updater; dual legacy media path and docs drift prevent 9+ |
| **Security** | **7.0** | Strong packaged-stream design; nginx token logging, Option A URLs, admin least-privilege gaps |
| **Performance** | **6.0** | Browse/home batching exists; search/CW/watchlist N+1 and detail waterfalls hurt; homepage still multi-shelf SQL |
| **UX** | **6.5** | Movie hero + player experience solid; series/search/cast/CMS artwork lag Netflix bar |
| **Scalability** | **6.0** | SKIP LOCKED workers + digests good; local storage only, in-process caches/limiters, no FTS, index claim gaps |
| **Overall** | **6.6** | Production-capable platform; CMS + discovery + perf hardening required before next growth wave |

---

## What works in production today

| Capability | Notes |
| --- | --- |
| Multi-audio / subtitle HLS | Verified on v1.14.2 with `#EXT-X-MEDIA` |
| Protected streaming | Session tokens; no public packages |
| Watch history / CW | Backend + player resume |
| Recommendations / watchlist | Present |
| Content requests | Present |
| Localization EN/FA/PS | Catalog + player LTR |
| Publishing workflow | Draft → review → publish |
| Update-agent deploy | Signed, digests, verify-installation |
| Media mounts incl. audio | Fixed in v1.14.1 |

---

## Phase coverage map

| Phase | Outcome in this audit |
| --- | --- |
| 1 Full code audit | → `PRODUCTION_AUDIT.md` |
| 2 Database review | Indexes/N+1 noted; add only necessary indexes in FIX_PLAN |
| 3 Media pipeline | Healthy post-1.14.2; diagnostics page planned |
| 4 Admin CMS | Gap analysis; implementation deferred |
| 5 Movie detail V2 | Gap vs Netflix; deferred |
| 6 Cast/people | Credits exist; no `people` table / person pages — deferred |
| 7 Search | ILIKE + N+1; FTS + filters planned |
| 8 Localization | Translations exist; admin review workflow incomplete |
| 9 Performance | Measured patterns + targets in FIX_PLAN |
| 10 Security | → `SECURITY_AUDIT.md` |
| 11 TV readiness | Architecture notes only — no apps |
| 12 Roadmap | → prioritized in `FIX_PLAN.md` + §Roadmap below |

---

## Architecture (condensed)

```
nginx → frontend (SPA) + backend-api
                 ├─ media-processing-worker
                 ├─ publishing-worker
                 ├─ postgres / redis
                 └─ update-agent (host)
```

**Canonical media path:** upload → probe → tracks → encode-hls → activate package → publish → playback session → `/api/stream/{token}/`.

**Must not break:** multi-audio/subs, protected streaming, watch history, recommendations, watchlist, content requests, localization, deployment pipeline.

---

## Top risks (Critical / High)

1. Legacy arq encoding path coexists with real HLS pipeline  
2. Search / Continue Watching / watchlist N+1 under load  
3. Admin artwork is URL-only — not a real CMS asset pipeline  
4. Movie detail similar waterfall + unused React Query  
5. Nginx may log raw stream tokens  
6. Option A unprotected CDN URLs in session payloads  
7. Admin playback mint / legacy routes under-permissioned  
8. No first-class admin media diagnostics (retry/failed reason UX)  
9. Search not FTS / multi-locale / cast-aware  
10. No shared People entity for cast pages  

---

## Database review (summary)

| Topic | Finding |
| --- | --- |
| Missing useful indexes | Job claim `(status, priority, queued_at)`; scheduled publish `(status, scheduled_publish_at)` |
| Duplicate / noisy indexes | Many single-column indexes on movies/series — review later, don’t mass-drop |
| Slow / N+1 | Search, CW, watchlist, admin movie list |
| Constraints | Strong uniqueness on checksum, active package, active jobs |
| FTS | Not present — `ILIKE` only |
| People | Denormalized `movie_cast_credits` / `series_cast_credits` only |

**Benchmark requirement (when implementing):** record query counts before/after for home, movies, search, CW.

---

## Media pipeline review (summary)

| Stage | Grade | Notes |
| --- | --- | --- |
| Upload | A- | Dedupe + sniff; audio MIME fixed 1.14.1 |
| Probe | A- | Subtitle-only fixed 1.14.2; not auto-queued |
| Encode/Package | A | Multi-track + muxed; track change → requires_repackage |
| Publish | B+ | Workflow solid; worker status mutation edge |
| Stream | A- | Packaged strong; Option A by design unprotected |
| Ops | C | Need diagnostics page + orphan cleanup visibility |

---

## Frontend / UX review (summary)

| Area | Grade | Notes |
| --- | --- | --- |
| Movie detail | B | Hero good; similar waterfall; cast not linkable |
| Series detail | C+ | Behind movie pattern |
| Search | C | Basic; no filters/FTS/URL state |
| Player | A- | Multi-track + resume + LTR |
| Admin CMS | C | Tabs exist; artwork URL-only; tracks thin |
| Mobile | B | Bottom nav; dense grids |
| TV prep | D | focus-visible only; no spatial nav |

---

## Performance targets (aspirational)

| Surface | Target | Current |
| --- | --- | --- |
| Customer homepage | &lt;2 API calls | 1 aggregate when healthy; else fan-out; multi SQL shelves |
| Movie detail | Minimal waterfall | fetchMovie → then similar |
| Initial JS | Keep lean | ~311KB single bundle (v1.14.2 sample) |
| Images | Never force original | TMDB srcSet OK; local `/artwork` full size |

---

## Localization review

- Locales: EN / FA / PS with content translations table  
- Player labels for dubbed audio are native (not `FA Dub`)  
- Gap: full admin review workflow for machine translations; genre/collection/cast-role completeness varies  
- Rule retained: **never translate on customer request** — publish reviewed rows only  

---

## TV / smart TV readiness (prep only)

Do **not** build apps yet. Prep requirements:

- Spatial navigation / focus rings on shelves  
- 10-foot card sizes  
- Player D-pad map (partially present)  
- Avoid hover-only affordances  

---

## Missing Netflix-class features roadmap

### P0 (near-term after Critical fixes)

- CMS artwork upload (poster/backdrop/logo/gallery) with process pipeline  
- Admin media diagnostics + track editor  
- Movie detail V2 polish (defer similar, cast links)  
- Search improvement (FTS + filters + translations)  
- Cast / people pages  

### P1

- Profiles  
- Kids mode / parental controls  
- Offline downloads  

### P2

- Android TV / Apple TV / Samsung / LG apps  
- Mobile native apps  
- Payments / subscriptions  

---

## Preservation constraints

Any approved implementation must keep green:

- HLS multi-audio + subtitles  
- Protected streaming  
- Watch history / CW  
- Recommendations / watchlist / content requests  
- Localization  
- Deployment / update-agent / digests  

---

## Approval gate

**Next step:** review `FIX_PLAN.md`.  
**Only after explicit approval** start implementation PRs (prefer small trains: Critical perf/security → CMS artwork → detail/search/people).
