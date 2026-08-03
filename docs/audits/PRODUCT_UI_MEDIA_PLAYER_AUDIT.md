# iFilm Product UI / Media Linking / Player Audit

Date: 2026-08-03  
Branch: `cursor/professional-ui-media-player-4873`  
Scope: product-quality audit prior to UI/UX upgrade and media-linking work.

## BLOCKER

| ID | Finding | Evidence |
|----|---------|----------|
| B1 | Movie/episode edit pages have no media link/detach workflow | `MovieFormPage.tsx`, `EpisodeFormPage.tsx` — PublishingPanel only |
| B2 | No post-upload ownership attach API | Owners set only at `POST /admin/media/sessions` create time |
| B3 | `canPlayFullMovie` ignores real playability | `catalogPresentation.ts` returns `!demoOwned` only |
| B4 | Watchlist is mock/local-only | No watchlist API; UI implies persistence |

## HIGH

| ID | Finding |
|----|---------|
| H1 | Upload UI never sends `movie_id`/`episode_id`; no `?owner_type=&owner_id=` preselection |
| H2 | PublishingPanel lists readiness failures without remediation CTAs (Upload and Link / Link Existing) |
| H3 | Play vs Demo Clip labeling inconsistent; Play can ignore auth until player |
| H4 | Placeholder admin nav still clickable (CDN, Users, legacy Encoding) |
| H5 | Player missing next-episode / up-next, skip ±10s buttons, AirPlay, stats overlay |
| H6 | Subtitle selector stubbed |
| H7 | `/children` and similar surfaces are incomplete or misleading |
| H8 | Series episode list lacks per-episode playability gates |

## MEDIUM

| ID | Finding |
|----|---------|
| M1 | Admin dashboard is count-only; missing failed jobs, unpublished approved, worker health |
| M2 | Media asset list lacks owner / unassigned / search filters |
| M3 | Continue Watching lacks tombstones / remove for unavailable items |
| M4 | Search lacks genre/year/country filters and keyboard result navigation polish |
| M5 | Design tokens skew cream/gold + Inter (template-adjacent); need original iFilm identity |
| M6 | Customer dark theme forced; light theme undertested |
| M7 | Inconsistent empty/error/loading states across admin tables |
| M8 | PiP not capability-gated in UI |

## LOW

| ID | Finding |
|----|---------|
| L1 | Debug leftovers largely fixed in v1.0.14; verify no new console noise |
| L2 | Terminology mix: “Encoding (legacy)” vs Processing |
| L3 | Quality badges may overstate available renditions |
| L4 | Hero carousel dots a11y could be stronger |

## In scope for this PR

- Media linking (attach/detach) on existing `media_assets` model
- Upload owner preselection
- Publishing readiness remediation CTAs
- Design system tokens + shared primitives polish
- Customer home/cards/details/search upgrades
- Admin shell, dashboard, forms/tables polish
- Protected player upgrade (controls, quality, PiP, resume, next episode, keyboard, stats)
- AirPlay when WebKit APIs permit; document limitations
- Google Cast: disabled future-ready control unless secure receiver path exists
- Tests + CI green

## Explicitly deferred

- CDN, DRM, offline download, mobile apps
- Live Radius
- Full watchlist backend (unless minimal safe API fits)
- Major database redesign / parallel media model
- Claiming AirPlay verified without real Safari/device hardware

## Architecture constraints (preserve)

- Upload, probe, HLS packaging, protected playback sessions
- Publishing eligibility / readiness rules (do not weaken)
- Single-owner constraint on `media_assets`
- Admin LTR English; public RTL preserved
- Opaque playback tokens; no path/token leakage
