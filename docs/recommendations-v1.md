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

## API

- `GET /api/me/recommendations`
- `GET /api/me/recommendations/home`
- `GET /api/recommendations/home` (optional auth; anonymous → Popular Now)
- `GET /api/catalog/movies/{id}/recommendations`
- `GET /api/catalog/series/{id}/recommendations`
- `GET|POST /api/recommendations/what-to-watch`
- `GET /api/admin/recommendations/inspect?subscriber_id=` (`movies.read`)

Rules: published only, archived/deleted excluded, current item excluded,
duplicates removed, deterministic ordering + stable tie-break, no private fields
or source URL leakage.

## Anonymous fallback

Trending/popular → New Releases → Top Rated → Editorial collections.
Labels use **Popular Now**, never **Recommended for You**.

## Cache invalidation

Short-lived in-process cache (~45s) keyed per subscriber + params.

Invalidate on: watch progress upsert/complete/delete/clear, Continue Watching
dismiss, Watchlist add/remove/clear. Catalog publish membership changes should
call `bump_catalog_feature_epoch()` (global drop).

No migration in V1 — profiles are derived, not persisted.

## Privacy

Strict user isolation; no public preference profile; admin inspect is RBAC-gated
debug only (no session/auth secrets). History is never sent to external APIs.
