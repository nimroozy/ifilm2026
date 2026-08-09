# G2 — Movie & Series Detail Experience V2

**Status:** PLAN APPROVED — **G2a shipped** (`v1.16.0`); **G2b planning** in [`G2B_SERIES_DETAIL_V2_PLAN.md`](./G2B_SERIES_DETAIL_V2_PLAN.md)  
**Baseline:** production `v1.16.0` (Movie Detail V2 healthy)  
**Do not modify G1.** Do not modify G2a while planning G2b. No Series Detail implementation until G2b plan approval.

### Approved decisions (2026-08-09)

| Topic | Decision |
|-------|----------|
| Split | **G2a** Movie Detail V2 first · **G2b** Series Detail V2 after G2a approval |
| Trailer | Keep cinematic **0–6s backdrop → muted background trailer** when trailer exists; remain backdrop if none; respect `prefers-reduced-motion`; no card autoplay; no audio autoplay; hide YouTube chrome; Play starts real playback |
| Resume | Use existing `user_watch_progress` / continue-watching: incomplete → **Continue Watching** (+ progress); completed → **Watch Again**; no duplicate progress logic |
| Audio/subs | Truthful `media_tracks` availability only (e.g. English · فارسی دوبله · پښتو دوبله / subs English · فارسی · پښتو) |
| Cast | TMDB credits carousel with **portrait**, name, character — not plain text |
| Similar | Existing similar + recommendations where relevant; published only; locale-aware; no fake data |
| RTL | FA/PS RTL on detail chrome; **player always LTR** |
| G2b | **Do not start** until G2a approved |

**Parent design:** [`CUSTOMER_UI_V2.md`](./CUSTOMER_UI_V2.md) (G0)  
**G1 foundation:** tokens, Header V2, `MediaCard`, `ContentShelf`, cinematic hero language  
**Existing product docs:** [`MOVIE_DETAIL_EXPERIENCE_V1.md`](../catalog/MOVIE_DETAIL_EXPERIENCE_V1.md)

---

## 1. Goal

Bring Movie Detail and Series Detail to the same **premium streaming visual system** as G1 homepage:

- Cinematic full-bleed hero
- Restrained gold CTAs
- Truthful audio/subtitle badges from `media_tracks` availability
- Localized EN / FA / PS + RTL
- Cast, similar/recommendations, seasons/episodes, resume progress

**Reuse, do not duplicate:**

| System | Reuse |
|--------|--------|
| `media_tracks` → availability | `audio_availability` / `subtitle_availability` on catalog payloads |
| TMDB credits | Persisted `movie_cast_credits` / `series_cast_credits` |
| Recommendations / similar | `GET /movies/{id}/similar`, `GET /catalog/series/{id}/recommendations` |
| Watch progress | `GET /me/continue-watching`, `GET/PUT /me/watch-progress/{asset_id}` |
| Watchlist | existing `WatchlistButton` + membership API |
| Player | existing `/player/*` — **always LTR** |

---

## 2. Current state (v1.15.0)

### Movie Detail — mostly V1 premium

| Area | Today |
|------|--------|
| Files | `MovieDetailsPage` (`Browse.tsx`) → `MovieDetailView.tsx` |
| Hero | Full-bleed backdrop; **muted YouTube after 6s** (V1 behavior) |
| Actions | Play / Trailer / Coming Soon / My List / Share |
| Meta | Year, runtime, genres, director, ratings |
| Cast | Horizontal from embedded `credits[]` |
| Similar | `ContentShelf` + `MediaCard` via `/movies/{id}/similar` |
| Tracks | Language badges from availability helpers |
| Gaps vs G2 | Visual polish to match G1 tokens; trailer autoplay policy decision; resume CTA not on page |

### Series Detail — pre-G1

| Area | Today |
|------|--------|
| Files | Inline `SeriesDetailsPage` in `Browse.tsx` (no `SeriesDetailView`) |
| Layout | ~40–50vh backdrop + overlapping poster column (inset, not cinematic) |
| Seasons / episodes | Select + list rows; loads **all** episodes up front |
| Cast | **Missing** — DB `series_cast_credits` exists, **not** on `SeriesOut` |
| Similar / recs | **Missing** — rec API exists, unused |
| Progress / resume | **Missing** on page (CW only on home) |
| Design system | Minimal — highest G2 lift |

---

## 3. Visual direction

### Shared principles (aligned with G1)

- One composition for hero (not a dashboard)
- Brand/header transparent over hero → solid/blur on scroll
- Gold reserved for Play / active / focus / thin progress
- No card-heavy hero; poster allowed as supporting element on desktop series/movie meta
- Overview max ~42rem; metadata secondary
- No new UI libraries

### Desktop layout — Movie (1440×900)

```
┌─ Header V2 (transparent → blur) ────────────────────────────┐
├─ FULL-BLEED HERO (~72–82vh) ────────────────────────────────┤
│  Backdrop (+ optional trailer policy, see §6)                │
│  Side + bottom scrims (RTL-aware)                            │
│  Logo or display title                                       │
│  Meta chips: year · ★ rating · runtime · genres              │
│  Director line (secondary)                                   │
│  [ Play ] [ My List ] [ Trailer? ]                           │
│  Audio / Subtitle badge row (truthful)                       │
│  Short overview (clamp → expand)                             │
├─ Cast carousel (ContentShelf-style rail) ───────────────────┤
├─ More Like This (MediaCard V2 shelf) ───────────────────────┤
└─ Footer ────────────────────────────────────────────────────┘
```

### Desktop layout — Series (1440×900)

```
┌─ Header V2 ─────────────────────────────────────────────────┐
├─ FULL-BLEED HERO ───────────────────────────────────────────┤
│  Backdrop + optional desktop poster (2:3) beside text block  │
│  Title · year · ★ · season count · genres                    │
│  [ Resume S1 · E3 ] or [ Play ]   [ My List ]  [ Trailer? ]  │
│  Audio / Subtitle badges                                     │
│  Overview                                                    │
├─ Episodes ──────────────────────────────────────────────────┤
│  Season control (select; segmented optional if ≤5 seasons)   │
│  Landscape rows: thumb 16:9 · E# · title · dur · progress    │
│  Play / Resume per episode                                   │
├─ Cast (when API exposes credits) ───────────────────────────┤
├─ More Like This (series recommendations) ───────────────────┤
└─ Footer ────────────────────────────────────────────────────┘
```

### Mobile layout (390×844)

```
┌─ Logo · search · lang · profile ─┐
├─ Hero ~58–68vh (backdrop only) ──┤
│  Title                           │
│  Meta (wrap 1–2 lines)           │
│  [ Play/Resume ] [ My List ]     │  ← compact; Trailer secondary
│  Track chips (scroll if needed)  │
│  Overview clamp                  │
├─ Cast rail (snap) ───────────────┤
├─ Episodes (series) ──────────────┤
│  Season select full width        │
│  Thumb + title stacked rows      │
├─ More Like This ─────────────────┤
├─ Bottom nav ─────────────────────┤
└──────────────────────────────────┘
```

**Mobile rules:** no giant empty voids; poster column **hidden** (backdrop is the visual plane); episode thumb ≥120px; bottom nav clearance; FA/PS labels must fit.

---

## 4. Component plan (implementation train — not this PR)

| Component | Action |
|-----------|--------|
| `MovieDetailView.tsx` | Restyle to G1 tokens; tighten hero/CTA/badge hierarchy; wire resume if progress exists |
| `SeriesDetailView.tsx` (**new**) | Extract from `Browse.tsx`; cinematic hero; episode list; cast/similar |
| `EpisodeRow` / `SeasonPicker` | New small design-system or detail-local components; 16:9 thumb + thin gold progress |
| `CastRail` | Shared extract from movie cast (reuse on series) |
| `ContentShelf` + `MediaCard` | Reuse for More Like This |
| `WatchlistButton` | Reuse as-is |
| Player routes | Unchanged; keep `dir=ltr` |

---

## 5. RTL behavior (FA / PS)

| Surface | Behavior |
|---------|----------|
| Page `dir` | `rtl` from locale (existing `CustomerLayout` / `DocumentLangSync`) |
| Hero text block | `text-align: start`; side scrim flips (`surfaces` / `rtl:` gradients) |
| CTA order | Logical start: Play/Resume dominant, then My List |
| Meta separators | Use locale-safe chips (existing `MetaChip`), not hard-coded `/` alone |
| Cast / similar rails | `ContentShelf` RTL scroll + chevrons |
| Season select | Logical padding/chevron |
| Episode rows | Thumb at inline-start; text flows start→end |
| **Player** | Remains **LTR** after navigate to `/player/*` |

Do not rely on `dir=rtl` alone — verify FA/PS screenshots for More menus, language control, and episode progress.

---

## 6. Hero trailer policy (**APPROVED**)

**Homepage G1:** manual hero only — no autoplay slide or trailer.

**Movie Detail G2a (approved):**

1. **0–6 seconds:** cinematic backdrop (LCP image).
2. **After ~6 seconds:** if trailer metadata exists → smooth muted background YouTube transition (`youtube-nocookie`, muted, modest branding, scaled to crop chrome).
3. If no trailer → remain on backdrop.
4. `prefers-reduced-motion` → never auto-transition; backdrop only (Trailer button still available).
5. Manual Trailer button can start/restart muted trailer; Play always navigates to `/player/movie/:id` for real playback.
6. No audio autoplay; no YouTube chrome intentional visibility; no layout shift on transition.

**Series (G2b):** Trailer button when `trailer_key` present; no timed autoplay (confirm at G2b kickoff).

---

## 7. API changes needed

Prefer **additive** fields. No migrations expected for G2 UI if credits already persisted.

### 7.1 Required (small)

| Change | Why |
|--------|-----|
| Expose `credits: CastCreditOut[]` (+ optional `credits_synced_at`) on **`SeriesOut`** via `series_out()` | Series cast carousel; table `series_cast_credits` already exists |
| Frontend: fetch series recommendations `GET /api/catalog/series/{id}/recommendations` (or add `/series/{id}/similar` alias if product wants parity naming) | More Like This shelf |

### 7.2 Optional / nice-to-have

| Change | Why |
|--------|-----|
| `GET /api/series/{id}/episodes?season=` server filter | Avoid downloading all seasons’ episodes |
| Detail bootstrap `GET /api/catalog/movies/{id}/detail-page` bundling movie+similar+credits | Reduce chatty waterfalls — **only if** measured need; otherwise keep 2–3 calls |
| Resume hint on detail: client uses existing `GET /me/continue-watching` filtered by content id **or** lightweight `GET /me/watch-progress/by-content?movie_id=` / `series_id=` | Avoid scanning full CW list — add only if CW list grows large |

### 7.3 Do **not** build

- New credits sync pipeline (use admin TMDB refresh)
- New watchlist or progress stores
- New recommendation engines
- Live TMDB calls from customer detail pages

### 7.4 Existing payloads (sufficient today)

- Movie: `credits`, `audio_availability`, `subtitle_availability`, `director`, genres, artwork, `logo_url`, playable flags  
- Episode: `thumbnail_url`, `duration_minutes`, `playable`, `has_demo_clip`, description  
- Availability badges: already derived in `catalogAvailability.ts`

---

## 8. Performance impact

### Movie (target)

| Metric | Target |
|--------|--------|
| API calls (anon) | ≤ 2 (detail + similar) |
| API calls (auth) | ≤ 4 (+ watchlist membership + optional CW/progress) |
| LCP image | Hero backdrop `eager` + `fetchpriority=high`; sized srcset (no `/original/`) |
| Cast / similar images | `lazy` |
| JS | No new libraries; detail stays lazy route chunk |
| Bundle delta | Aim ≤ +15 KB gzip vs v1.15.0 for shared detail components |

### Series (target)

| Metric | Target |
|--------|--------|
| API calls (anon) | series + seasons + episodes(+season filter if added) + optional recs |
| Avoid | N+1 per episode; fetching unused seasons’ heavy fields |
| Episode thumbs | lazy; only selected season in DOM (already mostly true) |

### Non-goals for G2

- Redis/cache train (T1)
- Homepage query reduction
- Changing playback session protocol

---

## 9. Functional preservation

Must not regress:

- Play gating (`published` + playable)
- Demo / Coming Soon labels
- Multi-audio + subtitle selection **in player** (detail only shows truthful badges)
- Watchlist add/remove
- Resume from CW / player dialog
- Localization of titles/descriptions
- Protected streaming

---

## 10. Implementation phases (after plan approval)

| Phase | Scope | Exit |
|-------|-------|------|
| **G2a** | Movie Detail V2 restyle + resume CTA + trailer policy | Desktop/mobile EN/FA screenshots; no HIGH |
| **G2b** | Series Detail V2 + episode UX + cast API expose + recommendations shelf | Same matrix + episode progress |
| **G2c** | Polish: season UX, empty states, a11y, perf check, production verify | Signed release candidate |

Prefer **one PR per phase** with human visual approval. Do not combine with G3 browse/search or T1.

---

## 11. Acceptance checklist (implementation)

### Movie

- [ ] Cinematic full-bleed hero matches G1 language  
- [ ] Poster/meta/director/year/genre readable  
- [ ] Play + My List dominant; Trailer secondary  
- [ ] Localized description EN/FA/PS  
- [ ] Audio/subtitle badges from real availability  
- [ ] Cast carousel from persisted credits  
- [ ] Similar shelf (MediaCard V2)  
- [ ] Player remains LTR  

### Series

- [ ] Same visual system as movie  
- [ ] Season picker  
- [ ] Episode list with thumbnails  
- [ ] Progress / Resume when watch state exists  
- [ ] Audio/subtitle availability on series  
- [ ] Cast when credits present  
- [ ] More Like This from recommendations  

### Cross-cutting

- [ ] FA/PS RTL verified (not dir-only)  
- [ ] 390 / 430 / 1440 screenshots  
- [ ] Bundle roughly stable  
- [ ] No BLOCKER / HIGH  
- [ ] No G1 homepage regressions  

---

## 12. Prototypes & screenshots (this plan PR)

### Prototypes (static HTML, design-only)

| File | Purpose |
|------|---------|
| [`prototypes/detail.html`](./prototypes/detail.html) | Movie Detail V2 (Interstellar fixture) |
| [`prototypes/series-detail.html`](./prototypes/series-detail.html) | Series Detail V2 (Breaking Bad production artwork) |
| [`prototypes/series-data.json`](./prototypes/series-data.json) | Series fixture |
| [`prototypes/prototype.css`](./prototypes/prototype.css) | Shared prototype styles |

Open with `?locale=en|fa|ps`.

### Screenshot set (captured for plan review)

| Shot | Path |
|------|------|
| Movie desktop EN | `screenshots/g2/movie-desktop-en.png` |
| Movie desktop FA | `screenshots/g2/movie-desktop-fa.png` |
| Movie mobile EN | `screenshots/g2/movie-mobile-en.png` |
| Series desktop EN | `screenshots/g2/series-desktop-en.png` |
| Series desktop FA | `screenshots/g2/series-desktop-fa.png` |
| Series mobile EN | `screenshots/g2/series-mobile-en.png` |
| Series mobile FA | `screenshots/g2/series-mobile-fa.png` |

Artifacts also under `/opt/cursor/artifacts/customer-ui-v2-g2/`.

---

## 13. Open questions — resolved / deferred

| # | Question | Resolution |
|---|----------|------------|
| 1 | Trailer policy | **Resolved:** keep 6s muted background trailer (see §6) |
| 2 | Season control | **Deferred to G2b** |
| 3 | Series similar endpoint | **Deferred to G2b** (recommendations OK for now) |
| 4 | Movie resume CTA | **Resolved:** Continue Watching / Watch Again from existing progress |
| 5 | Ship split | **Resolved:** G2a then G2b |

---

## 14. Stop conditions

- After **plan approval:** start **G2a only** (this train).  
- After **G2a Ready:** human visual/production review — **do not start G2b**.  
- No production deploy without explicit approval.  
- Do not modify G1 homepage behavior.

---

*End of G2_DETAIL_V2_PLAN.md*
