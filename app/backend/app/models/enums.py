"""Shared catalog enums / validated status values."""

from __future__ import annotations

# Explicit publishing lifecycle (Phase 9). String-backed VARCHAR storage.
PUBLICATION_STATUSES = (
    "draft",
    "in_review",
    "approved",
    "scheduled",
    "published",
    "unpublished",
    "archived",
)

# Backward-compatible alias used by older imports/schemas.
CATALOG_STATUSES = PUBLICATION_STATUSES
CatalogStatus = str
PublicationStatus = str

PUBLIC_VISIBLE_STATUSES = frozenset({"published"})

ENTITY_TYPES = ("movie", "series", "season", "episode")

SORT_OPTIONS = (
    "newest",
    "oldest",
    "title_asc",
    "title_desc",
    "rating_desc",
    "recently_updated",
)
