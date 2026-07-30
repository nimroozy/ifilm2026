# iFilm Frontend

Customer-facing streaming UI for the iFilm platform (Vite + React + TypeScript + Tailwind + shadcn/ui).

## Prerequisites

- Node.js 22+
- [pnpm](https://pnpm.io/) 10+

## Setup

```bash
cd app/frontend
cp .env.example .env
pnpm install
```

## Scripts

| Command | Description |
| --- | --- |
| `pnpm dev` | Start the Vite dev server (default port `3000`) |
| `pnpm lint` | ESLint over `src/` |
| `pnpm typecheck` | TypeScript project build (`tsc -b`) |
| `pnpm test` | Unit tests (Vitest) |
| `pnpm build` | Production build to `dist/` |
| `pnpm preview` | Preview the production build |

## Environment

See `.env.example` for supported variables.

- `VITE_API_BASE_URL` — fallback API origin when `/api/config` is unavailable
- `VITE_PORT` — local dev server port
- `BACKEND_PORT` — Vite proxy target for `/api` requests

Runtime config is loaded from `/api/config` when available (`src/lib/config.ts`). Without a backend, the UI uses mock data and defaults.

## Structure

- `src/pages/` — route pages (home, browse, account, admin, player)
- `src/components/` — layout, error boundary, and shared UI
- `src/components/ui/` — shadcn/ui primitives
- `src/data/mockData.ts` — local mock content / translations
- `src/lib/` — config, API client helpers, utilities
- `prerender/` — blog prerender / sitemap helpers

## Notes

- The app currently runs against mock auth/content; no backend is required for local UI work.
- An `ErrorBoundary` wraps the root app tree to catch render failures.
- CI runs install, lint, typecheck, test, and build via `.github/workflows/frontend-ci.yml`.
