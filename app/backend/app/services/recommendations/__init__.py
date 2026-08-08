"""Deterministic, explainable recommendations (no ML / external AI)."""

from app.services.recommendations.cache import invalidate_user_recommendation_cache
from app.services.recommendations.engine import (
    because_you_watched_shelves,
    home_recommendation_payload,
    inspect_recommendations,
    recommend_for_item,
    recommend_for_user,
    what_to_watch,
)

__all__ = [
    "because_you_watched_shelves",
    "home_recommendation_payload",
    "inspect_recommendations",
    "invalidate_user_recommendation_cache",
    "recommend_for_item",
    "recommend_for_user",
    "what_to_watch",
]
