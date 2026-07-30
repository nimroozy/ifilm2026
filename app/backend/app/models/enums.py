"""Shared catalog enums / validated status values."""

from __future__ import annotations

CATALOG_STATUSES = ("draft", "published", "archived")
CatalogStatus = str

SORT_OPTIONS = (
    "newest",
    "oldest",
    "title_asc",
    "title_desc",
    "rating_desc",
    "recently_updated",
)
