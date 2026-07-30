# iFilm 2026

Official repository for the iFilm streaming platform.

## Frontend

The customer UI lives in [`app/frontend`](./app/frontend). See that README for setup, scripts, and environment variables.

```bash
cd app/frontend
pnpm install
pnpm dev
```

## CI

GitHub Actions runs lint, typecheck, tests, and build for the frontend (`.github/workflows/frontend-ci.yml`).
