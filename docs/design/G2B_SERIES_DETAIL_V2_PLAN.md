# G2b — Series Detail Experience V2 (Planning Only)

**Status:** DRAFT PLAN — awaiting human review  
**Baseline:** production `v1.16.0` (G2a Movie Detail V2 healthy)  
**Scope of this PR:** planning artifacts only — **no Series Detail implementation**  
**Do not modify G2a** (`MovieDetailView` / movie detail behavior).

| Related | Link |
|---------|------|
| Parent G2 plan | [`G2_DETAIL_V2_PLAN.md`](./G2_DETAIL_V2_PLAN.md) |
| G2a report | [`G2A_REPORT.md`](./G2A_REPORT.md) |
| Prototypes | [`prototypes/g2b/`](./prototypes/g2b/) |
| Screenshot prototypes | [`screenshots/g2b/`](./screenshots/g2b/) |

---

## 1. Goal

Create **premium streaming-style series pages** that match G2a movie cinematic language while adding season/episode UX, resume-to-episode, cast, and recommendations.

**Reuse — do not duplicate systems:**

| System | Reuse from |
|--------|------------|
| G1 customer design system | tokens, `Header`, `ContentShelf`, `MediaCard`, `MetaChip` / `MetaRow`, `SectionHeader`, `heroSizing`, typography |
| G2a movie hero system | full-bleed backdrop, CTA exclusivity, track chips, overview clamp, trailer affordance patterns from `MovieDetailView` (extract shared pieces in G2b; **do not change movie page**) |
| `media_tracks` | `audio_availability` / `subtitle_availability` on series + episode payloads; `catalogAvailability` / `movieDetailTrackGroups` helpers |
| Watch progress | `GET /me/continue-watching`, `GET/PUT /me/watch-progress/{asset_id}` — map by `series_id` + `episode_id` |
| Recommendations | `GET /catalog/series/{id}/recommendations` (exists, unused on detail today) |
| TMDB credits | persisted `series_cast_credits` — expose on `SeriesOut` (additive API) |
| Localization | EN / FA / PS + existing content i18n; player always LTR |

**Out of scope for G2b implementation train (after this plan):**

- New progress store, rec engine, or credits sync pipeline
- Live TMDB calls from customer pages
- Player redesign (neighbors / autoplayNext already exist)
- G1 homepage changes
- G2a movie detail changes

---

## 2. Current state (v1.16.0)

| Area | Today |
|------|--------|
| Files | Inline `SeriesDetailsPage` in `Browse.tsx` (~565–884); **no** `SeriesDetailView.tsx` |
| Hero | ~40–50vh backdrop + inset poster column (pre-G1 / not cinematic) |
| CTAs | Play = first playable episode in **selected season**; Trailer opens external; My List via `WatchlistButton` |
| Seasons | Native `Select`; client filters episodes |
| Episodes | Frontend loads **all** episodes via `listEpisodes(id)` with no `season` param — backend already supports `?season=` |
| Cast | Missing UI; DB `series_cast_credits` exists; **`SeriesOut` has no `credits`** |
| Recs | Missing UI; `GET /catalog/series/{id}/recommendations` exists |
| Resume | Not on detail page; CW on home only (`WatchProgressDto` has `episode_id`, `series_id`, `season_number`, `episode_number`, `player_path`) |
| Tracks | Series-level chips exist; episode-level availability mostly unused in rows |
| i18n | Many hardcoded EN strings on series page |

---

## 3. Visual direction

Same cinematic language as G2a movies:

- Full-bleed hero backdrop (poster optional desktop accent only — **not** inset card hero)
- Title as hero signal; restrained gold primary CTA
- Metadata chips (year, seasons, rating, genres, age)
- Series-level audio/subtitle chips from truthful availability
- Overview clamp → expand
- Below fold: Episodes → Cast → More Like This
- No hero overlays (badges/stickers), no card clutter in hero
- Cards only where interaction requires (episode rows, cast portraits, shelf cards)

### 3.1 Series hero

| Element | Behavior |
|---------|----------|
| Backdrop | LCP image; responsive srcset; same sizing helpers as movie |
| Title | Localized title; logo_url optional if present (parity with movie when available) |
| Metadata | Year range / release year · season count · episode count · age · rating · genres |
| Primary CTA | Exclusive: **Continue Watching SxxExx** (in progress) · **Watch Again** (completed latest) · **Play** (no progress → first playable) |
| Secondary | My List (`WatchlistButton`) |
| Trailer | See §8 open decision — button and/or muted background policy |
| Progress | Thin gold bar under CTA when series has in-progress episode |
| Player | Navigate to `/player/episode/{id}?series=&season=` — **always LTR** |

### 3.2 Seasons

| Viewport | Control |
|----------|---------|
| Desktop | Compact **season selector** (select / menu). Optional segmented control **only if ≤5 seasons** and space allows — not default |
| Mobile | **Bottom sheet or full-width dropdown** — not a large horizontal season pill bar |

Avoid Netflix-style wide horizontal season chip rails that dominate the viewport.

Default selected season:

1. Season of continue-watching episode (if any), else  
2. First season with playable episodes, else  
3. First published season

### 3.3 Episode list

Each episode row/card:

| Field | Source |
|-------|--------|
| Thumbnail | `thumbnail_url` (lazy, sized) |
| Episode number | `S{season}E{episode}` label e.g. `S01E01` |
| Title | localized episode title |
| Duration | `duration_minutes` |
| Description | clamp 2–3 lines → expand on row |
| Progress bar | from watch progress for that `episode_id` (thin gold) |
| Audio / subtitle | episode `audio_availability` / `subtitle_availability` when present; else omit (do not invent) |
| Play action | Play / Resume / Watch Again per episode playability |

Must work for `S01E01`, `S01E02`, … across seasons. Only **selected season** episodes in DOM/list fetch.

### 3.4 Resume (design)

| Case | Hero CTA | Episode row |
|------|----------|-------------|
| Incomplete episode progress for this series | **Continue Watching SxxExx** (+ %) | That episode shows Resume + progress |
| Completed last watched | **Watch Again** (same episode) or **Play next** (see below) | Completed mark / Watch Again |
| No progress | **Play** → first playable in default season | Play on rows |
| Episode completed → next | **Design only on detail:** hero may offer “Next: SxxExx” when previous completed; actual autoplay-next remains player responsibility | — |

Reuse existing watch progress APIs only. No new progress tables.

### 3.5 Cast

Same as movie G2a:

- Portrait (or initials fallback)
- Name + character
- Cap ~16
- Lazy images
- Shared `CastRail` / `CastCard` extract preferred (copy pattern from movie without editing movie file until extract is shared)

Crew: show when present in credits payload (same `CastCreditOut` shape); otherwise cast-only.

### 3.6 Recommendations

| Shelf | API |
|-------|-----|
| Similar series (primary) | `GET /catalog/series/{id}/recommendations` |
| Related movies (optional) | Include only if recommendation payload already returns mixed types **or** a clear product rule; otherwise series-only for G2b |
| Deduping | Exclude current series; dedupe by id; published only; locale-aware titles via existing mapping |

Optional parity: `/series/{id}/similar` alias — **not required** if recommendations shelf is sufficient.

---

## 4. Wireframes

### 4.1 Desktop (1440×900)

```
┌─ Header V2 (G1) ──────────────────────────────────────────────────────────┐
├─ FULL-BLEED HERO (~62–72vh) ──────────────────────────────────────────────┤
│  Backdrop (edge-to-edge) + bottom/start scrim                             │
│                                                                           │
│  TITLE                                                                    │
│  year · ★ rating · N seasons · genres · age                               │
│  [ Continue Watching S01E03  42% ]   [ My List ]   [ Trailer ]            │
│  Audio: …   Subtitles: …                                                  │
│  ▬▬▬▬▬▬▬▬▬▬░░░░  progress                                                 │
│  Short overview… More                                                     │
├─ Episodes ────────────────────────────────────────────────────────────────┤
│  Season  ▾  Season 1                                    7 episodes        │
│  ┌──────┬───────────────────────────────────────────────────────────────┐ │
│  │ thumb│ S01E01  Pilot                         58m          [ Play ]   │ │
│  │ 16:9 │ Desc…  Audio/Subs chips  ▬ progress                           │ │
│  └──────┴───────────────────────────────────────────────────────────────┘ │
│  … S01E02 …                                                               │
├─ Cast ────────────────────────────────────────────────────────────────────┤
│  [portrait] [portrait] …  (horizontal rail)                               │
├─ More Like This ──────────────────────────────────────────────────────────┤
│  MediaCard V2 shelf (series)                                              │
└─ Footer ──────────────────────────────────────────────────────────────────┘
```

### 4.2 Mobile (390×844)

```
┌─ Header compact ──────────────────┐
├─ HERO ~58–68vh (backdrop only) ───┤
│  TITLE                            │
│  Meta wrap                        │
│  [ Continue S01E03 ] [ My List ]  │
│  Trailer secondary / icon         │
│  Track chips (scroll-x ok)        │
│  Overview clamp                   │
├─ Episodes ────────────────────────┤
│  [ Season 1 ▾ ]  ← opens sheet    │
│  ┌────┐ S01E01 Pilot              │
│  │thumb│ 58m · progress · Play    │
│  └────┘ desc clamp                │
│  …                                │
├─ Cast rail (snap) ────────────────┤
├─ More Like This ──────────────────┤
├─ Bottom nav clearance ────────────┤
└───────────────────────────────────┘

Mobile season sheet:
┌─────────────────────────┐
│ Select season        ✕  │
│ ○ Season 1 (7 eps)      │
│ ● Season 2 (13 eps)     │
│ ○ Season 3 …            │
└─────────────────────────┘
```

### 4.3 RTL (FA / PS)

| Surface | Rule |
|---------|------|
| Page chrome | `dir=rtl` from locale |
| Hero text / CTAs | logical start; scrim flips |
| Episode thumb | inline-start |
| Season control | chevron/padding logical |
| Cast / shelves | RTL scroll (existing ContentShelf) |
| **Player** | always LTR after navigation |

---

## 5. Component plan (implementation — after plan approval)

| Component | Action |
|-----------|--------|
| `SeriesDetailView.tsx` | **New** — extract from `Browse.tsx`; cinematic hero + sections |
| `SeasonPicker` | Desktop select; mobile sheet/dropdown |
| `EpisodeRow` | Thumb, SxxExx, title, duration, desc, progress, tracks, play |
| `CastRail` | Shared extract preferred; series consumes same as movie |
| `ContentShelf` + `MediaCard` | More Like This |
| `WatchlistButton` | Reuse |
| Hero helpers | Reuse `heroSizing`, trailer helpers, track grouping — share without regressing G2a |
| Player routes | Unchanged; keep `dir=ltr` |

`SeriesDetailsPage` becomes a thin data loader (series, seasons, season-scoped episodes, recs, watch state) → `SeriesDetailView`.

---

## 6. API impact

Prefer **additive** fields. No new migrations expected if credits already persisted.

### 6.1 Required

| Change | Why |
|--------|-----|
| Add `credits: list[CastCreditOut]` (+ optional `credits_synced_at`) to **`SeriesOut`** via `series_out()` | Cast rail; table `series_cast_credits` already exists |
| Frontend: call `GET /api/catalog/series/{id}/recommendations` | More Like This |
| Frontend: call `GET /api/series/{id}/episodes?season={n}` | Avoid loading all seasons on open |

### 6.2 Recommended (small)

| Change | Why |
|--------|-----|
| Ensure CW / progress mapping includes `series=` / `season=` on `player_path` or construct path client-side | Home CW → player neighbors; detail Resume links |
| Filter `GET /me/continue-watching` client-side by `series_id` for hero CTA (same pattern as movie) | Resume without new endpoint |

### 6.3 Optional

| Change | Why |
|--------|-----|
| `/series/{id}/similar` alias | Naming parity with movies |
| Lightweight `GET /me/watch-progress/by-content?series_id=` | Only if CW list scanning becomes costly |
| Episode list fields already sufficient (`thumbnail_url`, `duration_minutes`, availability, playable flags) | — |

### 6.4 Do not build

- Runtime TMDB from customer detail
- New recommendation engine
- New watch progress schema
- Full episode dump bundled into `SeriesOut`
- Detail-page N+1 per episode track queries

### 6.5 Existing endpoints (sufficient)

```
GET /api/series/{id}
GET /api/series/{id}/seasons
GET /api/series/{id}/episodes?season=
GET /api/catalog/series/{id}/recommendations
GET /api/me/continue-watching
GET /api/me/watch-progress/{asset_id}
Watchlist membership APIs
```

---

## 7. Data requirements

| Data | Required for | Notes |
|------|--------------|-------|
| Series artwork | Hero | `backdrop_url`, `poster_url`, optional `logo_url` |
| Trailer metadata | Trailer CTA / optional autoplay | `trailer_key` / provider fields (already on series) |
| Localization | Title/description FA/PS | existing content i18n |
| Seasons | Picker | `season_number`, `episode_count`, title |
| Episodes (season-scoped) | List | number, title, description, duration, thumbnail, playable, availability |
| Series-level availability | Hero chips | from `media_tracks` aggregation |
| Episode-level availability | Row chips | when packaged; omit if empty |
| `series_cast_credits` | Cast | must be **exposed** on API |
| Watch progress | Resume | `episode_id`, `series_id`, season/episode numbers, position, completed |
| Recommendations | Shelf | published series (movies optional) |

Admin/content ops: ensure TMDB series credits refresh has been run for showcase titles before visual QA.

---

## 8. Performance impact

| Concern | Plan |
|---------|------|
| Page open | Fetch series + seasons + **one** season’s episodes + recommendations (parallel where safe) |
| Do **not** | Load all episodes for all seasons on first paint |
| Do **not** | Live TMDB |
| Images | Hero backdrop eager + high fetchpriority; episode thumbs + cast + shelf **lazy**; sized srcsets (no `/original/`) |
| Season change | Re-fetch or cache-by-season that season’s episodes only |
| JS | New `SeriesDetailView` lazy route chunk; extract shared cast/hero bits carefully to avoid regressing movie bundle |
| Auth extras | Watchlist membership + CW/progress — same budget class as G2a (≤ ~4–5 calls authenticated) |
| Target (anon) | series + seasons + episodes(season) + recs ≈ **4** calls |

Preserve G2a/G1 lazy-loading discipline.

---

## 9. RTL & player

- Verify FA and PS layouts (hero, season sheet, episode rows, shelves) — not `dir`-only.
- Player remains LTR on `/player/episode/*`.
- Localized strings for Play / Continue / Watch Again / seasons / episodes / cast / More Like This (extend `translations.ts`; remove hardcoded EN on series page).

---

## 10. Open decisions (confirm at kickoff)

| # | Topic | Proposal |
|---|-------|----------|
| 1 | **Series trailer autoplay** | Parent plan suggested **button only, no 6s autoplay**. Align with movie (6s muted) for consistency **or** keep series button-only. **Needs explicit product call.** |
| 2 | Related movies on series page | Default: **series-only** shelf; add movies only if payload/product wants mixed “More Like This” |
| 3 | Next-episode on detail hero | Design affordance only in G2b; player keeps autoplay-next |
| 4 | Season segmented control | Only if ≤5 seasons on desktop; default remains select |

---

## 11. Acceptance checklist (for future implementation PR)

- [ ] Cinematic full-bleed series hero matches G2a language  
- [ ] Play / Continue / Watch Again exclusivity with episode targeting  
- [ ] My List + Trailer behavior per approved policy  
- [ ] Season selector desktop; sheet/dropdown mobile — **no large horizontal season bar**  
- [ ] Episode rows: thumb, SxxExx, title, duration, description, progress, tracks, play  
- [ ] Season-scoped episode fetch (no full dump on open)  
- [ ] Cast from exposed `SeriesOut.credits`  
- [ ] Recommendations shelf; no duplicates; published only  
- [ ] FA/PS RTL verified; player LTR  
- [ ] Lazy images; no TMDB runtime; responsive artwork  
- [ ] G2a movie detail **unchanged**  
- [ ] Desktop/mobile EN + FA (+ PS sample) screenshots  

---

## 12. Prototypes & screenshot prototypes (this PR)

### Prototypes

| File | Purpose |
|------|---------|
| [`prototypes/g2b/series-detail.html`](./prototypes/g2b/series-detail.html) | Interactive static Series Detail V2 (EN/FA, desktop/mobile layout) |
| [`prototypes/g2b/series-data.json`](./prototypes/g2b/series-data.json) | Fixture for labels / episodes |
| [`prototypes/g2b/prototype.css`](./prototypes/g2b/prototype.css) | Shared prototype styles |

Open with `?locale=en|fa` (PS labels noted in plan; EN/FA captured for review).

### Screenshot prototypes

| Shot | Path |
|------|------|
| Desktop EN | `screenshots/g2b/series-desktop-1440-en.png` |
| Desktop FA | `screenshots/g2b/series-desktop-1440-fa.png` |
| Mobile EN | `screenshots/g2b/series-mobile-390-en.png` |
| Mobile FA | `screenshots/g2b/series-mobile-390-fa.png` |
| Mobile season sheet EN | `screenshots/g2b/series-mobile-390-en-season-sheet.png` |

Also copied under `/opt/cursor/artifacts/g2b-plan/` when captured.

---

## 13. Implementation phases (after plan approval — not this PR)

| Phase | Scope |
|-------|-------|
| **G2b-impl** | `SeriesDetailView` + season/episode UX + credits expose + recs + resume CTA |
| **G2b-qa** | EN/FA/PS screenshots, perf check, real-content QA |
| **G2c** (optional polish) | Empty states, a11y pass, production verify |

Prefer one implementation PR after this plan is accepted. **Stop after plan review — no coding until approved.**

---

## 14. Stop conditions

- This PR is **plan + prototypes + screenshots only**.
- Do **not** start Series Detail implementation until human approval of this plan.
- Do **not** modify G2a movie detail.
- Do **not** deploy from this branch.

---

*End of G2B_SERIES_DETAIL_V2_PLAN.md*
