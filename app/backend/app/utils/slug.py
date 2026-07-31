"""Slug normalization helpers."""

from __future__ import annotations

import re
import unicodedata

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def normalize_slug(value: str) -> str:
    text = unicodedata.normalize("NFKD", (value or "").strip())
    text = text.encode("ascii", "ignore").decode("ascii").lower()
    text = _SLUG_RE.sub("-", text).strip("-")
    return text[:280]


def slug_or_from_title(slug: str | None, title: str) -> str:
    candidate = normalize_slug(slug or "")
    if candidate:
        return candidate
    candidate = normalize_slug(title)
    if not candidate:
        raise ValueError("Unable to derive a valid slug from title")
    return candidate
