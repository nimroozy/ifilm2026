# Phase 7 Repository Audit

**Repository:** `nimroozy/ifilm2026`  
**Branch audited:** `media/streaming-service`  
**Draft PR:** [#7](https://github.com/nimroozy/ifilm2026/pull/7) — `feat: protected HLS streaming service`  
**Base / Phase 6 merge SHA:** `ef7859f75f337614ef8c6420b65108dfc7c348fe` (`feat: add local HLS encoding pipeline`)  
**Audit head (pre-report):** `09800c5f50eb3f2c11cce9bae8ae41ba61386e2c`  
**Audit date:** 2026-07-31  

**Scope rule:** Read-only inspection of tracked source, config, docs, tests, and CI. No Phase 7 implementation. No production-code fixes. Secret values are not printed.

**Tracked files inspected:** **260** (`git ls-files`)  
**Tracked path prefixes / directories:** **42** unique parent directories

---

## 1. Executive summary

Phase 6 delivered a real local HLS encoding pipeline (profiles, packages, renditions, `encode_hls` worker jobs, feature flags). Phase 7 proposes a **protected streaming service** for completed packages. The repository is **capable of supporting Phase 7**, but several **BLOCKER** security and architecture gaps must be addressed as part of (or before) implementation:

1. **Unauthenticated StaticFiles** mounts the entire `MEDIA_ROOT` at `/media`, which can expose `originals/` and `packages/` if paths are known.
2. **Legacy stream routes** still invent placeholder HLS under `media/hls/` and do not use Phase 6 packages.
3. **No explicit “active package” column** — Phase 7 package selection must be defined (newest completed is the natural default).
4. **No playback eligibility service** and weak customer auth (Radius-gated; frontend still mock-friendly).
5. **Docs still claim HLS packaging is deferred** despite Phase 6 merge.

**Verdict:** Phase 7 is **safe to implement after incorporating the compatibility adjustments below**. It is **not** safe to ship protected streaming while StaticFiles continues to serve completed packages anonymously. Do not begin Phase 8.

| Severity | Count |
| --- | ---: |
| BLOCKER | 4 |
| HIGH | 8 |
| MEDIUM | 11 |
| LOW | 9 |
| INFORMATIONAL | 12 |
| Documentation inconsistencies | 14 |

---

## 2. Complete tracked-file inventory (grouped)

### Root (`.`)

| Path | Purpose | Responsibility | Status |
| --- | --- | --- | --- |
| `README.md` | Project overview | Entry docs | **Incomplete / stale** on HLS scope |
| `SECURITY.md` | Security posture | Flags, secrets guidance | **Stale** (missing media-processing/HLS flags) |
| `docker-compose.yml` | Local orchestration | postgres, redis, api, ARQ worker, media-processing-worker | **Active** |
| `.gitignore` | Ignore rules | — | Active |
| `.github/workflows/backend-ci.yml` | Backend CI | ruff, mypy, subset pytest, alembic, migrations, readiness | Active; **incomplete media coverage** |
| `.github/workflows/frontend-ci.yml` | Frontend CI | lint, typecheck, test, build | Active |

### `docs/`

| Path | Purpose | Status |
| --- | --- | --- |
| `docs/catalog/*` | Catalog admin architecture/API/workflows/tests | Active for catalog; **stale** on media admin routes |
| `docs/media/UPLOAD_FOUNDATION.md` | Upload phase | Active; deferred list now partially obsolete |
| `docs/media/MEDIA_PROCESSING_FOUNDATION.md` | Probe phase | Active; HLS deferred section **contradicts** Phase 6 |
| `docs/media/HLS_ENCODING_PIPELINE.md` | Phase 6 HLS encode | **Authoritative** for encoding |
| `docs/backend/PRODUCTION_READINESS.md` | Ops checklist | **Stale** on encoding ladder |
| `docs/backend/THREAT_MODEL.md` | Threat notes | Partially stale (placeholder-only framing) |
| `docs/audits/` | Audits | This report |

### `app/backend/`

| Path | Purpose | Status |
| --- | --- | --- |
| `app/main.py` | FastAPI app, CORS, `/media` StaticFiles, health/ready | Active — StaticFiles is Phase 7 blocker |
| `app/api/router.py` | Route registration | Active |
| `app/api/routes/*` | HTTP endpoints | Mix of catalog, media foundation, **legacy stream/encoding/cdn** |
| `app/core/*` | Config, deps, security, features, runtime | Active |
| `app/models/*` | ORM | Active + **legacy** `media.py` UploadJob/EncodingJob |
| `app/schemas/*` | Pydantic | Active |
| `app/services/media_*` + `media_processing/*` | Upload/probe/encode | Active Phase 4–6 |
| `app/services/hls.py`, `encoding.py`, `uploads.py` (legacy) | Placeholder packaging / old uploads | **Obsolete for Phase 6 packages**; still used by `stream.py` |
| `app/workers/media_processing.py` | Probe/encode worker entry | Active |
| `app/workers/tasks.py` | ARQ placeholders | Parallel legacy worker |
| `alembic/versions/001…006` | Schema | Linear chain; head `006_hls_encoding` |
| `tests/*` | Backend tests | Active; media suites rich locally, **not all run in CI unit step** |
| `.env.example` | Env template | Active; no streaming flags yet |
| `Dockerfile`, `systemd/` | Deploy helpers | Active |

### `app/frontend/`

| Path | Purpose | Status |
| --- | --- | --- |
| `src/App.tsx` | Routes | Active; player is mock |
| `src/lib/api.ts` | Dual HTTP clients | Active; `getStream` unused by Player |
| `src/pages/admin/*` | Catalog + media admin | Active; Encoding/CDN placeholders remain |
| `src/pages/Browse.tsx` (`PlayerPage`) | Customer player chrome | **Incomplete** (mock) |
| `src/pages/Admin.tsx` | Legacy mock admin | **Obsolete** (unrouted) |
| `src/components/ui/*` | shadcn UI kit | Active reusable |
| `__tests__` | Vitest | Active for catalog/upload/processing |

---

## 3. Backend architecture map

| Concern | Location | Notes |
| --- | --- | --- |
| Entrypoint | `app.main:create_app` / `app` | Lifespan validates settings + ensures `media_root()` |
| Router | `app.api.router.api_router` under `settings.api_prefix` (`/api`) | |
| Auth | JWT HS256 (`app.core.security`) | Claims `typ=admin\|subscriber` |
| Admin users | `AdminUser` + `AdminRole.permissions` JSON | `require_permissions` + alias map |
| Subscribers | `Subscriber` | Radius login behind `ENABLE_RADIUS_LOGIN` |
| DI | FastAPI `Depends`; `DbSession`, `CurrentAdmin`, `CurrentSubscriber`, `OptionalSubscriber` | |
| Services | Plain functions/modules; session passed explicitly | Commits inside service functions |
| Exceptions | Per-route `HTTPException`; domain errors in media_processing | No global handlers |
| Middleware | CORS only | No access-log middleware |
| Config validation | `validate_runtime_settings` | Prod JWT/DB/Radius/debug checks; no streaming secret yet |
| Startup/shutdown | Lifespan yield; no teardown workers | |

---

## 4. Frontend architecture map

| Concern | Implementation |
| --- | --- |
| Framework | React + Vite + React Router |
| Admin auth | `tokenStore` + `RequireAdmin` + `adminApi.me()` |
| Customer auth | Mock-friendly `AuthProvider`; optional real JWT |
| API | Axios wrappers; envelope unwrap; `ApiError` |
| Data fetching | TanStack Query on some pages; media pages often manual `useEffect` + poll |
| Feature flags | Status endpoints (`getProcessingStatus`) + UI banners |
| Admin nav | Upload, Processing live; Encoding/CDN/Users “soon” placeholders |
| Reuse for Phase 7 admin sessions | Mirror `MediaProcessingJobsPage` (filters, table, poll, `StatusBadge`, feature-disabled banner) |

---

## 5. Database and migration map

**Linear chain (verified):**

```
001_initial_schema
 → 002_movies_title_idx
 → 003_catalog_administration
 → 004_media_upload
 → 005_media_processing
 → 006_hls_encoding   ← current head
```

| Revision | Adds |
| --- | --- |
| 004 | `media_assets`, `upload_sessions`, completed-checksum unique index |
| 005 | Probe columns; `media_processing_jobs` + events; active-probe unique index |
| 006 | `media_encoding_profiles` (5 seeded rows), `media_packages`, `media_renditions`, active-encode_hls unique index |

**Model ↔ migration:** Phase 6 models align with 006 columns. Package statuses are free-form strings (no DB enum). Seeded profiles are deterministic by `name` uniqueness; UUIDs differ per upgrade (acceptable).

**Phase 7:** `007_streaming_service` must revise `006_hls_encoding` and add `media_playback_sessions` (+ indexes). Round-trip `006→007→006→007` required.

---

## 6. Media upload architecture

| Step | Implementation |
| --- | --- |
| Flag | `ENABLE_UPLOADS` |
| Create session | `POST /api/admin/media/sessions` |
| Chunked upload | Resumable PUT with offset/complete headers |
| Storage | `MEDIA_ROOT/originals/<asset_id>/<file>` relative `storage_path` |
| Validation | MIME sniff, size, checksum; duplicate completed checksum rejection |
| Ownership | Optional `movie_id` / `series_id` / `season_id` / `episode_id` (≤1) |
| Immutability | Probe/encode verify size/checksum; never rewrite original |

---

## 7. Processing-worker architecture

| Concern | Detail |
| --- | --- |
| Entry | `python -m app.workers.media_processing` |
| Claim | PostgreSQL `FOR UPDATE SKIP LOCKED`; SQLite fallback |
| Types | `probe`, `encode_hls` |
| Lifecycle | queued → running → completed \| failed \| cancelled \| retry_wait |
| Retry | Exponential backoff; max attempts |
| Cancel | Process-group SIGTERM/SIGKILL; work-dir cleanup for encode |
| Stale | Heartbeat threshold → retry/fail |
| Binaries | ffprobe required when processing enabled; ffmpeg only if HLS enabled |
| Flags | `ENABLE_MEDIA_PROCESSING`; encode also needs `ENABLE_HLS_ENCODING` |

---

## 8. HLS encoding architecture

| Concern | Detail |
| --- | --- |
| Profiles | 240p–1080p H.264/AAC; never upscale |
| Output | `packages/work/<job_id>/` → validate → atomic rename → `packages/<asset_id>/<package_id>/` |
| Artifacts | `master.m3u8`, `<label>/index.m3u8`, segments |
| Package statuses | pending, encoding, validating, promoting, completed, failed, cancelled |
| Paths | Relative to `MEDIA_ROOT`; incomplete packages hide paths in API |
| Active package | **None** — multiple completed packages allowed; list by `created_at` desc |
| Supersession | Re-encode creates a new package; older completed packages remain |
| Deletion | No package delete API in Phase 6 |

`PACKAGE_ACTIVE_STATUSES` means **in-flight encode**, not “selected for playback”.

---

## 9. Authentication and RBAC map

| Principal | How authenticated | Entitlement today |
| --- | --- | --- |
| Admin | Local password → JWT `typ=admin` | Role permission list |
| Subscriber | Radius (feature-flagged) → JWT `typ=subscriber` | `status==active`; string `package` is ISP plan, **not** media package |
| Anonymous | Allowed on public catalog (published) and **stream/static media** | — |

**Catalog visibility:** `published_only` filters exist for movies/series APIs.  
**Playback eligibility abstraction:** **does not exist**.  
**Phase 7 reuse:** `CurrentSubscriber`, published catalog filters, optional asset↔content FKs.  
**Must introduce:** eligibility service (honest abstraction; no fake subscription engine), streaming feature flag + secret validation, session table.

---

## 10. Docker and filesystem map

| Service | Media mount | Notes |
| --- | --- | --- |
| `api` | `ifilm_media:/data/media` **RW** | Full media root; Phase 7 prefers RO packages |
| `worker` (ARQ) | RW | Legacy |
| `media-processing-worker` | RW (documented intentional) | Writes packages/work |

Layout under `MEDIA_ROOT`: `originals/`, `packages/`, `packages/work/`, `temp/`, legacy `hls/`, artwork dirs.

FFmpeg is installed in the backend image; healthcheck requires ffprobe always and ffmpeg when HLS encoding is enabled.

---

## 11. Logging and security review

| Finding | Severity | Path / symbol | Explanation | Phase 7 impact | Action |
| --- | --- | --- | --- | --- | --- |
| Full `MEDIA_ROOT` StaticFiles | **BLOCKER** | `app/main.py` `StaticFiles` | Anonymous `/media/**` can serve packages/originals | Defeats session auth | Stop serving packages via open StaticFiles; serve only via protected stream (or mount RO packages path **behind auth**) |
| Placeholder stream mutates DB | **BLOCKER** | `stream.get_stream_manifest` | Unauthenticated optional subscriber; writes placeholder HLS | Conflicts with real packages | Do not extend; replace/gate behind flag; never write placeholders when local streaming is the product path |
| Unauthenticated HLS file route | **HIGH** | `stream.serve_hls` | Serves `media/hls/` without auth; weak `startswith` check | Parallel insecure delivery | Deprecate or require session; use `relative_to` |
| Package relative paths in admin API | **HIGH** | `MediaPackageOut.storage_path` / `master_playlist_path` | Paths like `packages/.../master.m3u8` map to StaticFiles URLs | Token bypass if StaticFiles remains | Redact or stop mounting packages publicly |
| No request logging / token redaction middleware | **HIGH** | — | Tokens in URLs risk access-log leakage | Spec requires redaction | Add logging filter; prefer Authorization header or opaque path token carefully |
| Empty `JWT_SECRET` default | **MEDIUM** | `Settings.jwt_secret` | Caught in prod-like validation | Streaming secret must follow same pattern | Add `PLAYBACK_TOKEN_SECRET` validation when streaming enabled |
| CORS `allow_methods/headers=*` | **MEDIUM** | `main.py` | Broad CORS | Token theft via XSS elsewhere | Tighten later; INFORMATIONAL for local streaming |
| No `shell=True` in media processing | **INFORMATIONAL** | `ffmpeg.run_process*` | Argv arrays only | Good pattern to keep | Continue |
| Path helpers for assets/packages | **INFORMATIONAL** | `paths.py`, `package_paths.py` | Symlink/`relative_to` checks | Reuse for segment resolution | Extend for rendition/segment names |
| Legacy ARQ encoding | **LOW** | `encoding.py` / `tasks.py` | Parallel obsolete pipeline | Confusion | Document; do not use for Phase 7 |

---

## 12. Test and CI review

### Backend tests (local organization)

| Suite | Focus |
| --- | --- |
| `test_media_upload.py` | Upload foundation |
| `test_media_processing*.py` | Probe/worker/ffprobe |
| `test_media_hls_encoding.py` | Encode e2e |
| `test_hls_feature_flags.py` | Dual flags |
| `test_migrations_postgres.py` | 005/006 round-trips, heads |
| `test_security.py`, `test_authorization_isolation.py`, `test_publishing_isolation.py` | Authz/publish |
| `test_catalog.py`, `test_config_auth_movies.py`, `test_readiness_integration.py` | Catalog/config/ready |

### Frontend tests

`mediaUpload`, `mediaProcessing`, `adminCatalog`, plus lib/unit tests. Vitest + Testing Library.

### CI commands (actual)

**Backend:** `ruff check` → `mypy` → **partial** pytest (`test_config_auth_movies`, `test_security`) → alembic upgrade scenarios → `test_migrations_postgres` → `test_readiness_integration`.  
**Does not** run full media/HLS suites in the unit step.

**Frontend:** `pnpm lint` → `typecheck` → `test` → `build`.

### Missing for Phase 7

- Session/token/path/range/revocation tests (specified)
- CI job or step running streaming tests with flags + secret
- Frontend playback-session admin tests

---

## 13. Documentation inconsistencies

| # | File | Stale claim | Reality |
| --- | ---: | --- | --- |
| 1 | `README.md` | ABR ladders / HLS packaging “out of scope” | Phase 6 implemented local ABR HLS |
| 2 | `README.md` | Mentions probe only under media | HLS encoding docs exist |
| 3 | `docs/media/MEDIA_PROCESSING_FOUNDATION.md` | Encoding profiles/HLS packaging out of scope / deferred | Implemented in 006 |
| 4 | `docs/media/UPLOAD_FOUNDATION.md` | Encoding/HLS out of scope | Downstream phases landed |
| 5 | `docs/backend/PRODUCTION_READINESS.md` | “Placeholder HLS only; no real ffmpeg ladder” | Real encode worker exists |
| 6 | `docs/backend/PRODUCTION_READINESS.md` | Feature flag list omits media processing / HLS | Flags exist |
| 7 | `docs/backend/THREAT_MODEL.md` | Placeholder-encoding framing only | Real packages also exist |
| 8 | `SECURITY.md` | Flag list omits processing/HLS | Incomplete |
| 9 | `app/backend/README.md` | “placeholder HLS, not real ffmpeg” | Contradicts Phase 6 |
| 10 | `docs/catalog/FRONTEND_INTEGRATION.md` | Upload/encoding admin placeholders; omits media routes | Upload/processing live |
| 11 | Admin nav “Encoding (soon)” | Suggests encode UI missing | Encode HLS on asset detail |
| 12 | `AdminPlaceholderPage` encoding copy | “not enabled yet” | Flagged encode exists |
| 13 | `MediaUploadPage` copy | “Encoding and CDN deferred” | Encoding partially live |
| 14 | `HLS_PUBLIC_BASE_URL` / compose | Points at `/media/hls` public path | Conflicts with protected streaming goal |

**Documentation inconsistency count: 14**

---

## 14. Phase 7 compatibility matrix

| Component | Existing reuse | New work | Conflict / incorrect assumption | Recommended adjustment |
| --- | --- | --- | --- | --- |
| `media_playback_sessions` | UUID/`utcnow` patterns | Model + 007 | — | Store `token_hash` only |
| Migration 007 | Linear alembic chain | New revision from 006 | — | Seed nothing; indexes for hash/expiry/user/asset |
| Token gen/hash/verify | `security.py` JWT patterns | Dedicated playback token (random + HMAC/hash) | Spec “signature comparison” vs hash lookup | Prefer opaque token + SHA-256 hash lookup; HMAC optional |
| Session validation | — | Service | — | Constant-time compare on MAC if used |
| Expiry/revocation | — | Columns + checks | — | Return 410 when expired/revoked |
| Package selection | List by `created_at` | Selection helper | Spec assumes “explicitly active package” | **Add `is_active`/`activated_at` OR document newest-completed rule**; do not invent silent supersession |
| Playback eligibility | Published filters; asset FKs | Abstraction | Spec assumes entitlement rules | Implement interface: published owner content + completed package; stub “entitled if active subscriber” clearly |
| Playlist rewriting | `playlists.py` builders | Rewrite-on-read | Must not mutate stored files | In-memory rewrite to `/api/stream/{token}/...` |
| Path / symlink protection | `package_paths.assert_under_media_root` | Segment resolver | StaticFiles bypass | Disable public package serving |
| Streaming responses | `FileResponse` in legacy stream | Streaming + ranges | Loads via FileResponse (OK for files) | Use `StreamingResponse`/FileResponse with Range |
| HTTP Range | — | Parser + 206/416 | — | Only for `.ts` (or allowed pattern) |
| Audit events | Job events pattern | Lightweight events / throttled `last_accessed_at` | Avoid per-segment DB writes | Throttle; aggregate segment metrics in logs |
| Admin session APIs | processing RBAC style | New routes + perms | No `stream` permission today | Add `streaming.read/manage` or reuse processing carefully |
| Admin UI | Processing jobs page | New page + nav | Encoding placeholder noise | Add Playback sessions nav item |
| Docker RO packages | Full RW media for API | Remount or split volume | API currently RW full root | Prefer API RO full media or RO `packages` only; worker stays RW |
| Config validation | `runtime.py` | Streaming flags + secret | Empty secret OK while disabled | Mirror JWT strength rules when enabled |
| Logging redaction | — | Middleware / uvicorn access filter | Tokens in path | Prefer header token **or** redact path segments |

---

## 15. Blocking issues

1. **BLOCKER** — `app/main.py`: public StaticFiles on full `MEDIA_ROOT`.  
2. **BLOCKER** — No active-package field while Phase 7 spec requires deterministic “active” selection / supersession semantics.  
3. **BLOCKER** — Legacy `stream.py` placeholder pipeline is disconnected from Phase 6 packages and weakly authenticated.  
4. **BLOCKER** — Shipping protected playlists while packages remain anonymously fetchable at `/media/packages/...` (path leakage via admin schemas + StaticFiles).

---

## 16. Non-blocking improvements

- Update README/SECURITY/PRODUCTION_READINESS for Phase 6 accuracy (after approval).  
- Retarget or remove “Encoding (soon)” admin placeholder.  
- Expand Backend CI to run media/HLS tests (or a dedicated job).  
- Strengthen `serve_hls` path checks if kept temporarily.  
- Link media assets to published movies/episodes more systematically for eligibility.  
- Add structured access logging with redaction.  
- Clarify ARQ vs media-processing-worker roles in docs.

---

## 17. Recommended Phase 7 implementation plan

1. **Security groundwork:** remove or narrowly scope StaticFiles (do not expose `packages/` or `originals/` anonymously).  
2. **Schema:** `007_streaming_service` + `media_playback_sessions`; decide active-package strategy (column vs newest-completed).  
3. **Config:** `ENABLE_LOCAL_STREAMING` + playback secret/TTL settings; validate secret only when enabled.  
4. **Services:** token issue/verify, eligibility abstraction, package selection, playlist rewrite, path-safe segment streaming + Range.  
5. **APIs:** session create/list/revoke (subscriber); stream GET endpoints; admin inspection.  
6. **Worker/API Docker:** API media RO; worker RW.  
7. **Admin UI:** sessions list + revoke actions; feature-disabled banner.  
8. **Tests + real playback verification** per PR #7 body.  
9. **Docs:** `docs/media/STREAMING_SERVICE.md`; refresh stale README claims in a follow-up commit if approved.  
10. Keep PR Draft until CI green; no Phase 8.

---

## 18. Files expected to be added

- `app/backend/alembic/versions/007_streaming_service.py`
- `app/backend/app/models/media_playback.py` (or similar)
- `app/backend/app/services/streaming/` (`tokens.py`, `sessions.py`, `eligibility.py`, `package_select.py`, `playlist_rewrite.py`, `segment_path.py`, `range.py`, `audit.py`)
- `app/backend/app/api/routes/streaming.py` (and/or extend without using legacy placeholder writer)
- `app/backend/app/schemas/streaming.py`
- `app/backend/tests/test_streaming_*.py`
- `app/frontend/src/pages/admin/PlaybackSessionsPage.tsx` (+ tests)
- `docs/media/STREAMING_SERVICE.md`
- Env keys in `.env.example` / compose

---

## 19. Files expected to be modified

- `app/main.py` (StaticFiles scope)
- `app/api/router.py`
- `app/core/config.py`, `features.py`, `runtime.py`, `deps.py` (permissions)
- `app/models/__init__.py` (+ possibly `media_encoding.py` if adding `is_active`)
- `docker-compose.yml` (API RO mount; streaming env)
- `app/frontend/src/App.tsx`, `AdminLayout.tsx`, `lib/api.ts`
- Migration tests; CI if streaming tests are included
- Docs listed in §13 (when approved)

---

## 20. Files that must not be changed (Phase 7)

- Historical migrations `001`–`006` contents (except via new 007)
- Original upload binary storage semantics
- Probe/encode correctness paths except intentional shared helpers
- Do not “fix” Phase 6 by rewriting encoding algorithm
- Do not implement player UI, CDN, DRM, watch history, analytics
- Do not delete older packages as supersession

---

## 21. Open questions / unsupported assumptions

1. **Active package:** add DB column vs “newest completed wins”? Spec assumes explicit active — **code lacks it**.  
2. **Eligibility:** is “any active subscriber + published linked content” enough for v1? Asset may lack content FK.  
3. **Token transport:** path segment (`/stream/{token}/...`) vs `Authorization` / query — path tokens risk logs.  
4. **Should legacy `/api/stream/...` and `/api/media/hls/...` be disabled when `ENABLE_LOCAL_STREAMING=true`?** Recommended: yes.  
5. **StaticFiles:** remove entirely vs keep for non-sensitive artwork only?  
6. **Admin vs subscriber session list:** both required in v1?  
7. **IP/UA binding defaults:** keep false as specified?  
8. **Session cache:** in-process TTL OK without Redis?  
9. **CI:** expand backend workflow to run streaming tests always?  
10. **Media asset without published owner:** allow admin-only preview sessions?

---

## Finding index (severity rollup)

### BLOCKER (4)

| ID | Path | Detail |
| --- | --- | --- |
| B1 | `app/main.py` | Public StaticFiles on full media root |
| B2 | `models/media_encoding.py` | No explicit active package for selection/supersession |
| B3 | `api/routes/stream.py` | Placeholder open streaming path unrelated to packages |
| B4 | Admin package path fields + StaticFiles | Path disclosure enables unauthenticated package fetch |

### HIGH (8)

| ID | Path | Detail |
| --- | --- | --- |
| H1 | `stream.serve_hls` | Unauthenticated legacy HLS file serve |
| H2 | — | No playback eligibility abstraction |
| H3 | — | No streaming feature flag / secret settings yet |
| H4 | — | No access-log token redaction |
| H5 | `docker-compose.yml` | API RW full media (spec prefers RO packages) |
| H6 | Docs/README/SECURITY | Stale “HLS deferred / placeholder only” |
| H7 | Backend CI | Full media/HLS pytest not in unit job |
| H8 | Customer `PlayerPage` | Mock only; `getStream` unused |

### MEDIUM / LOW / INFORMATIONAL

See §§11–13 for CORS, dual workers, placeholder admin nav, weak `startswith` checks, missing stream permissions, enum-less status strings, seed UUID non-determinism, etc.

---

## Conclusion

**Phase 7 is safe to implement** once the audit adjustments are accepted—especially **closing anonymous `/media` package access**, defining **active package selection**, and **replacing (not extending) the placeholder stream pipeline**.  

**Do not start implementation until this audit is approved.**  
**Do not mark PR #7 Ready for Review.**  
**Do not begin Phase 8.**

---

## Post-approval resolution (2026-07-31)

Implementation landed on `media/streaming-service` (Draft PR #7). Audit BLOCKERs addressed as follows:

| ID | Resolution |
| --- | --- |
| B1 | Public `StaticFiles` `/media` mount removed; legacy `/media/**` returns 404 |
| B2 | `is_active` / `activated_at` / `superseded_at` + partial unique index in `007_streaming_service` |
| B3 | Legacy placeholder `stream.py` / `write_placeholder_package` removed; single streaming stack |
| B4 | Package filesystem paths redacted from admin package APIs |

HIGH items addressed or deferred:

- H1–H5: protected stream + RO packages mount + eligibility abstraction + streaming flags/secret
- H4: request path token redaction middleware/filter
- H6: README/SECURITY/STREAMING_SERVICE docs updated
- H7: streaming tests added locally (CI expansion still optional)
- H8: customer player remains deferred (Phase 8+)

Deferred (documented, non-blocking for Draft): subscriber entitlement/payment rules, CDN/Cloudflare/R2/S3/DRM, customer player UI.
