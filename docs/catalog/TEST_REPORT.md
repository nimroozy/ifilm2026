# Catalog test report

## Backend
Commands:

```bash
cd app/backend
ruff check app scripts tests
mypy app scripts
pytest -q
# with Postgres:
TEST_DATABASE_URL=postgresql+psycopg2://... alembic upgrade head
```

Coverage includes unauthorized admin access, movie create/validation/duplicate slug/update/soft-delete/publish, public draft hiding, series/season/episode hierarchy + duplicate numbers, episode publish parent checks, genre create/delete-in-use, pagination/filter/search/sort, plus foundation security/migration/readiness suites.

## Frontend
Commands:

```bash
cd app/frontend
pnpm install --frozen-lockfile
pnpm run lint
pnpm run typecheck
pnpm run test
pnpm run build
```

Coverage includes protected admin route, login failure, movie list/form validation/creation, API error display, series form, season/episode ordering, genre deletion conflict, and API-mode no-mock-fallback.

## Remaining risks
- Artwork is URL metadata only; no virus scanning or upload pipeline
- Episode publish depends on correct admin ordering of parent publish
- Mock customer catalog still used unless `VITE_DATA_MODE=api`
- Media encoding/CDN/Radius remain unfinished and disabled
