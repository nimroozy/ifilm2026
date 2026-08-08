# Collections V1

Curated content collections for admin editorial shelves and customer browse.

## Scope

- Curated collections of movies and series
- Admin create/edit of collection metadata and membership
- Customer browse: `/collections`, `/collections/:slug`
- Public API: `/api/catalog/collections`, `/api/catalog/collections/{slug}`
- Featured homepage shelves (`is_featured`)
- Deterministic ordering; published-only public filtering
- Idempotent demo seed (`demo_owned`, `demo_seed_version=collections-v1`)

## Out of scope (do not mix)

- Watchlist
- Continue Watching V2
- Request Movie / Content Requests
- What to Watch
- Recommendations roadmap
- CDN / DRM / Offline / Live TV
- Language metadata backfill
- Worker healthcheck fixes

## Data model

Migration: `016_collections_v1` (revises `015_external_media_playability`)

- `collections` — title, slug (unique), descriptions, `collection_type`, status
  (`draft`/`published`/`archived`), visibility, poster/backdrop URLs, sort_order,
  `is_featured`, demo ownership, admin audit ids, timestamps
- `collection_items` — exactly one of `movie_id` / `series_id` (CHECK), unique
  position per collection, partial unique indexes for movie/series membership

Deleting a collection never deletes movies or series.

## Collection types

Explicit enum — not inferred from title:

`editorial`, `franchise`, `seasonal`, `genre_feature`, `regional`, `language`, `staff_pick`

## Publication rules

- Draft / archived collections never appear publicly
- Public items: published, non-archived movies/series only
- Empty collections (zero visible items) hidden publicly
- Deterministic `position` ordering; no duplicates

## Permissions

- `collections.read` / `collections.manage` (aliases via coarse `collections`)

## Query-count notes

Bounded in `tests/test_collections.py::test_collection_query_counts_bounded`:

- Collection index: counts via EXISTS + per-row visible counts (no full item payloads)
- Collection detail: selectinload items + movie/series genre links
- Homepage featured: includes items for shelves; min visible item threshold applied

## Artwork

URL fields (`http`/`https` only). No arbitrary external path traversal. Uploads use
existing CMS artwork infrastructure when present; form accepts URL selection.

## Status

Shipped in **v1.7.0** (PR #48 merged). Migration tip: `016_collections_v1`.
