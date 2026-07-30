# Frontend catalog integration

## Data mode

| `VITE_DATA_MODE` | Behavior |
| --- | --- |
| `mock` (default) | Customer catalog reads `src/data/mockData.ts` |
| `api` | Customer catalog calls FastAPI via `src/lib/catalogData.ts` |

In API mode, failures surface as errors with retry. There is **no** silent fallback to mock fixtures.

## Key modules
- `src/lib/dataMode.ts` — mode detection
- `src/lib/api.ts` — typed Axios clients, Envelope support, admin/public APIs
- `src/lib/catalogData.ts` — customer data access switch
- `src/pages/admin/*` — admin routes and forms

## Admin routes
`/admin/login`, `/admin`, `/admin/movies`, `/admin/movies/new`, `/admin/movies/:id/edit`, `/admin/series`, `/admin/series/new`, `/admin/series/:id/edit`, `/admin/series/:id/seasons`, `/admin/seasons/:id/edit`, `/admin/seasons/:id/episodes`, `/admin/episodes/:id/edit`, `/admin/genres`

Upload/encoding/CDN admin tools remain placeholders under `/admin/tools/*` and stay feature-flagged off in the backend.

## Customer pages wired in API mode
Home, Movies, Series, details, Search, genre/featured/trending sections.

Playback is intentionally not connected.
