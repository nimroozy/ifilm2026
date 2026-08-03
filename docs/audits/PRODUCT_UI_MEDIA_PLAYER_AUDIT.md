# iFilm Product UI / Media Linking / Player Audit

Date: 2026-08-03 (updated)  
Branch: `cursor/professional-ui-media-player-4873`  
PR: https://github.com/nimroozy/ifilm2026/pull/29

## BLOCKER

| ID | Finding | Status |
|----|---------|--------|
| B1 | Movie/episode edit had no media link/detach | **Resolved** — Media card + APIs |
| B2 | No post-upload ownership attach API | **Resolved** |
| B3 | `canPlayFullMovie` ignored real playability | **Resolved** |
| B4 | Watchlist mock-only / no customer API | **Accepted deferred** — mock UI removed; deferred page + disabled action; DB table exists without public API |

## HIGH

| ID | Finding | Status |
|----|---------|--------|
| H1 | Upload owner preselection missing | **Resolved** |
| H2 | Publishing failures without remediation | **Resolved** |
| H3 | Play vs Demo Clip labeling | **Resolved** on details/home |
| H4 | Placeholder admin nav links | **Resolved** |
| H5 | Player next-episode / skip / AirPlay | **Resolved** (AirPlay capability-gated; hardware verification pending) |
| H6 | Subtitle selector stub | **Resolved** — frontend interface detects HLS/native tracks; ingestion deferred |
| H7 | Incomplete children/misleading surfaces | **Resolved** — `/children` is a Family/Animation filtered route (`ChildrenPage`), not generic Movies |
| H8 | Series episode playability gates | **Resolved** |

## MEDIUM / LOW

| ID | Status |
|----|--------|
| M1 Dashboard operational depth | **Deferred** — catalog counts only; full ops metrics (failed jobs, packages, worker health) tracked as a separate issue; no fake charts |
| M5 Design tokens | Resolved — Outfit/Fraunces cinema identity |
| Cast | Deferred — disabled control; secure receiver required |
| Stats overlay | Resolved — Ctrl+Shift+D / Stats button; no URLs/tokens |
| Quality invent badges | Resolved on home cards |

## Watchlist decision (B4)

- `watchlist_items` table exists (migration 001).
- No customer/admin HTTP APIs expose watchlist CRUD.
- This PR **does not** add a watchlist migration/API.
- Production UI: movie details show disabled “Watchlist (soon)”; `/watchlist` shows deferred empty state (no mock titles).

## AirPlay / Cast

- AirPlay: show only when `webkitShowPlaybackTargetPicker` or Remote Playback `prompt` exists.
- Unit coverage for capability detection.
- **Real verification status: Implemented, hardware verification pending**
- Google Cast: disabled; deferred until secure protected-session receiver exists.
- See `docs/media/AIRPLAY_CAST.md`.

## Subtitles

- Frontend detects HLS.js subtitle tracks and native `textTracks`.
- Off option, language labels, preference persistence, keyboard `C`.
- Backend subtitle packaging/ingestion remains deferred — do not claim SRT/ASS upload.

## Explicitly deferred

- CDN, DRM, offline, live Radius, mobile apps
- Secure Google Cast receiver
- Full watchlist API (B4)
- Full subtitle ingestion pipeline
- Major recommendation engine
- Full operational dashboard metrics (M1) — separate issue; do not expand this PR

## Children route (H7)

- Intended behavior: Family / Animation catalog (aligned with home `familyMovies`).
- `/children` renders `ChildrenPage` (`MoviesPage` with `audience="children"`).
- Loads Family + Animation genre queries and merges by id; title uses `t.nav.children`.
- Regression coverage in `catalogDemoUi.test.tsx`.

## Architecture preserved

- Upload, probe, HLS packaging, protected playback sessions
- Publishing eligibility unchanged
- Single-owner `media_assets` constraint
- Admin LTR; public RTL
- Opaque playback tokens; no path/token leakage in UI/stats
