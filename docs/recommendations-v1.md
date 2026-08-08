# Recommendations / What-to-Watch V1

Deterministic, explainable recommendations using existing iFilm signals.
No ML, embeddings, vector DB, collaborative filtering cluster, or external AI APIs.

## Signals

**User behavior (authenticated):** watch history, completion %, Continue Watching,
Watchlist adds, dismissed Continue Watching, completed movies, watched episodes.

**Catalog:** genres, languages, countries, year, rating, collection membership,
cast credits, similar-content overlap (genre/collection), movie/series type,
recency (`published_at` / year), popularity (`views` + rating).

**Not used:** trailer-only page views, TMDB translated language as preference,
unpublished/archived content, admin activity.

## Preference profile

Derived on demand (optionally short-TTL process cache). Fields include preferred
genres, content types, languages, dubbed/subtitle languages, countries, actors,
runtime/year ranges. Signal strengths are configurable (`rec_signal_*` settings).

Suggested strengths: completed / >70% high; 30–70% medium; Watchlist / Continue
Watching medium; dismissed negative; very short playback low/neutral.

## Scoring model (configurable)

| Component | Default weight |
| --- | --- |
| Genre similarity | 30% |
| Watch-history similarity | 20% |
| Cast overlap | 15% |
| Collection overlap | 10% |
| Language preference | 10% |
| Recency | 5% |
| Popularity / rating | 10% |

Each result retains human-readable `reasons` and a short `explanation` for cards.
Internal component scores are admin-debug only.

## Watched / list semantics (Recommended for You)

| Signal | Effect on Recommended for You |
| --- | --- |
| Completed | Hard-excluded (not recommended back immediately) |
| Continue Watching (in progress) | Hard-excluded (belongs on Continue Watching shelf) |
| Watchlisted | Hard-excluded from Recommended (still influences preference weights; My List owns the row) |
| Dismissed CW | Soft downrank only; does **not** delete watch history |

Explicit replay / editorial shelves may still show completed titles when product rules allow.

## Diversity & cross-shelf dedup

**Within one shelf:** unique `content_type:id`; near-tie genre diversification after
two consecutive same-primary-genre picks when score gap ≤ 0.06.

**Across homepage recommendation shelves:** a shared `used` key set suppresses
titles already shown on Recommended / Popular before Because You Watched.
Continue Watching and My List are separate product shelves; backend exclusion
prevents them from flooding Recommended. Editorial / genre catalog rows below may
intentionally overlap for discovery.

**Because You Watched vs Recommended:** BYW candidates skip keys already used by
Recommended/Popular and omit the anchor title. BYW is never padded with Popular.

## Because You Watched

- Anchor seeds prefer completed / high-progress rows (strength ≥ continue-watching).
- Accidental short playback and dismissed rows are not anchors.
- Anchor must still be published/public.
- Candidates: published, entitlement-visible at response time, exclude anchor +
  completed/CW/watchlist sets, meaningful `min_score` threshold.
- If fewer than `BECAUSE_MIN_CANDIDATES` quality matches: **omit the shelf**.

## Cold start

Authenticated user with no history and empty Watchlist:

- `mode=popular`, label **Popular Now** (never **Recommended for You**)
- Deterministic trending → new → top-rated style fallback
- Personalization engages after first meaningful signals (no empty-home gate)

## Mood → genre map (What-to-Watch)

| Mood | Genres |
| --- | --- |
| Exciting | Action, Adventure, Thriller |
| Funny | Comedy |
| Emotional | Drama, Romance |
| Relaxing | Family, Animation, Comedy |
| Suspenseful | Thriller, Crime, Mystery, Horror |
| Family | Family, Animation |

No fake mood metadata is stored on catalog rows.

When exact filters yield &lt; 3 titles, filters relax progressively
(duration → release period → language → subtitles). Response includes `relaxed`
notes and item reasons mention the relaxed match — filters are never silently
ignored, and dub/subtitle availability is never invented.

## API

- `GET /api/me/recommendations`
- `GET /api/me/recommendations/home`
- `GET /api/recommendations/home` (optional auth; anonymous → Popular Now)
- `GET /api/catalog/movies/{id}/recommendations`
- `GET /api/catalog/series/{id}/recommendations`
- `GET|POST /api/recommendations/what-to-watch`
- `GET /api/admin/recommendations/inspect?subscriber_id=`
  (**exact** permission `recommendations.inspect` — not granted by `movies.read`)

Rules: published only, archived/deleted excluded, current item excluded,
duplicates removed, deterministic ordering + stable tie-break, no private fields
or source URL leakage.

## Anonymous fallback

Trending/popular → New Releases → Top Rated → Editorial collections.
Labels use **Popular Now**, never **Recommended for You**.

## Cache

Short-lived **in-process** cache (~45s) keyed:

`u:{subscriber_id}:rec:{catalog_epoch}:{limit}:{content_type}:{genre}:{language}`

Invalidate on: watch progress upsert/complete/delete/clear, Continue Watching
dismiss, Watchlist add/remove/clear. Catalog publish **and** unpublish/archive
call `bump_catalog_feature_epoch()` (global drop).

**Multi-worker:** each instance has its own cache. Correctness does not require
shared invalidation. Stale personalized scores may survive up to TTL on another
worker, but **every response** re-runs `filter_still_public()` so unpublished /
non-visible titles cannot leak from a stale cache entry.

No migration in V1 — profiles are derived, not persisted.

## Privacy

Strict user isolation; no public preference profile; admin inspect is RBAC-gated
(`recommendations.inspect`) debug only (preference weights, candidate reasons,
rank — no session/auth secrets or unrelated profile PII). History is never sent
to external APIs.

## Localization

- UI chrome (shelf titles, What-to-Watch steps, chips, Try Again / Reset): en / fa / ps
- Catalog metadata: existing v1.10 rules (FA localized; PS falls back to EN, never FA)
- Recommendation explanation strings are localized on the client for FA/PS
