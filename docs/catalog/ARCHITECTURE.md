# Catalog architecture

## Overview

The catalog milestone replaces mock-only admin catalog management with a FastAPI-backed model for movies, series, seasons, episodes, and genres. Customer pages can read published catalog data when `VITE_DATA_MODE=api`.

```
Admin UI  --JWT-->  /api/admin/*  -->  PostgreSQL (Alembic)
Customer UI         /api/movies|series|genres  -->  published rows only
Mock mode           local mockData.ts (no backend required)
```

## Components

| Layer | Responsibility |
| --- | --- |
| SQLAlchemy models | `Movie`, `Series`, `Season`, `Episode`, `Genre` + M2M tables |
| Alembic `003_catalog_admin` | Schema expansion from foundation migrations |
| `services/catalog.py` | Query filters, slug uniqueness, publish rules, serializers |
| Public API | Published, non-deleted catalog reads with pagination/filter/sort |
| Admin API | Authenticated CRUD + publish/unpublish with RBAC |
| Frontend `catalogData` | Mock vs API switch; no silent API→mock fallback |
| Admin pages | `/admin/*` routes with React Hook Form + zod |

## Status model

Catalog entities use `draft | published | archived`.

- Public endpoints return `published` only and exclude `deleted_at IS NOT NULL`.
- Soft delete sets `deleted_at` and `status=archived`.
- Episode publish requires parent season and series to be published.

## Feature flags preserved

Uploads, encoding, CDN sync, and Radius login remain disabled by default. This milestone does not enable them.
