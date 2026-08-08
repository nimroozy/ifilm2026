"""Deterministic mood → genre mappings for What-to-Watch (V1).

These are explicit catalog genre name matches — not inferred mood metadata.
Documented for product/QA; do not invent fake mood tags on content rows.
"""

from __future__ import annotations

from typing import Final

# Mood slug → preferred genre names (case-insensitive match against Genre.name).
MOOD_GENRE_MAP: Final[dict[str, tuple[str, ...]]] = {
    "exciting": ("Action", "Adventure", "Thriller"),
    "funny": ("Comedy",),
    "emotional": ("Drama", "Romance"),
    "relaxing": ("Family", "Animation", "Comedy"),
    "suspenseful": ("Thriller", "Crime", "Mystery", "Horror"),
    "family": ("Family", "Animation"),
}

MOOD_LABELS: Final[dict[str, str]] = {
    "exciting": "Exciting",
    "funny": "Funny",
    "emotional": "Emotional",
    "relaxing": "Relaxing",
    "suspenseful": "Suspenseful",
    "family": "Family",
}


def genres_for_mood(mood: str | None) -> list[str]:
    if not mood:
        return []
    key = mood.strip().lower()
    return list(MOOD_GENRE_MAP.get(key, ()))


def is_known_mood(mood: str | None) -> bool:
    if not mood:
        return False
    return mood.strip().lower() in MOOD_GENRE_MAP
