# Catalog test report

## Backend
Commands and results (2026-07-30, branch `catalog/admin-integration`):

```bash
cd app/backend
ruff check app scripts tests          # All checks passed
mypy app scripts                      # Success: no issues found in 58 source files
pytest -q                             # 27 passed (with TEST_DATABASE_URL Postgres + Redis)
DATABASE_URL=postgresql+psycopg2://... alembic upgrade head   # reached 003_catalog_admin
```

Coverage includes unauthorized admin access, movie create/validation/duplicate slug/update/soft-delete/publish, public draft hiding, series/season/episode hierarchy + duplicate numbers, episode publish parent checks, genre create/delete-in-use, pagination/filter/search/sort, plus foundation security/migration/readiness suites.

## Frontend
Commands and results:

```bash
cd app/frontend
pnpm install --frozen-lockfile        # ok
pnpm run lint                         # ok
pnpm run typecheck                    # ok
pnpm run test                         # 23 passed
pnpm run build                        # ok
```

Also: `docker compose config` succeeded.

Coverage includes protected admin route, login failure, movie list/form validation/creation, API error display, series form, season/episode ordering, genre deletion conflict, and API-mode no-mock-fallback.

## Remaining risks
- Artwork is URL metadata only; no virus scanning or upload pipeline
- Episode publish depends on correct admin ordering of parent publish
- Mock customer catalog still used unless `VITE_DATA_MODE=api`
- Media encoding/CDN/Radius remain unfinished and disabled
