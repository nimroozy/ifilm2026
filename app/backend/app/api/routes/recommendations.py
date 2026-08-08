"""Recommendation + What-to-Watch API routes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.deps import (
    CurrentSubscriber,
    DbSession,
    OptionalSubscriber,
    require_permissions,
)
from app.models.admin import AdminUser
from app.schemas.recommendations import (
    HomeRecommendationsOut,
    RecommendationInspectOut,
    RecommendationItemOut,
    RecommendationListOut,
    WhatToWatchIn,
    WhatToWatchOut,
)
from app.services.recommendations.engine import (
    home_recommendation_payload,
    inspect_recommendations,
    recommend_for_item,
    recommend_for_user,
    scored_to_public_dict,
    what_to_watch,
)

router = APIRouter(tags=["recommendations"])


def _items_from_scored(items: list) -> list[RecommendationItemOut]:
    return [RecommendationItemOut.model_validate(scored_to_public_dict(i)) for i in items]


@router.get("/me/recommendations", response_model=RecommendationListOut)
def get_my_recommendations(
    db: DbSession,
    user: CurrentSubscriber,
    limit: int = Query(12, ge=1, le=40),
    content_type: Literal["movie", "series", "either"] | None = Query("either"),
    genre: str | None = Query(None),
    language: str | None = Query(None),
) -> RecommendationListOut:
    items, _profile, mode = recommend_for_user(
        db,
        user,
        limit=limit,
        content_type=content_type,
        genre=genre,
        language=language,
    )
    personalized = mode == "personalized"
    return RecommendationListOut(
        mode="personalized" if personalized else "popular",
        personalized=personalized,
        label="Recommended for You" if personalized else "Popular Now",
        count=len(items),
        items=_items_from_scored(items),
    )


@router.get("/me/recommendations/home", response_model=HomeRecommendationsOut)
def get_my_home_recommendations(db: DbSession, user: CurrentSubscriber) -> HomeRecommendationsOut:
    payload = home_recommendation_payload(db, user)
    return HomeRecommendationsOut.model_validate(payload)


@router.get("/recommendations/home", response_model=HomeRecommendationsOut)
def get_home_recommendations(
    db: DbSession,
    user: OptionalSubscriber,
) -> HomeRecommendationsOut:
    """Optional auth: personalized when logged in, truthful anonymous fallback otherwise."""
    payload = home_recommendation_payload(db, user)
    return HomeRecommendationsOut.model_validate(payload)


@router.get("/catalog/movies/{id_or_slug}/recommendations", response_model=RecommendationListOut)
def movie_recommendations(
    id_or_slug: str,
    db: DbSession,
    limit: int = Query(12, ge=1, le=40),
) -> RecommendationListOut:
    from app.services.catalog import resolve_movie

    resolve_movie(db, id_or_slug, published_only=True)
    items = recommend_for_item(db, kind="movie", id_or_slug=id_or_slug, limit=limit)
    return RecommendationListOut(
        mode="item",
        personalized=False,
        label="More Like This",
        count=len(items),
        items=_items_from_scored(items),
    )


@router.get("/catalog/series/{id_or_slug}/recommendations", response_model=RecommendationListOut)
def series_recommendations(
    id_or_slug: str,
    db: DbSession,
    limit: int = Query(12, ge=1, le=40),
) -> RecommendationListOut:
    from app.services.catalog import resolve_series

    resolve_series(db, id_or_slug, published_only=True)
    items = recommend_for_item(db, kind="series", id_or_slug=id_or_slug, limit=limit)
    return RecommendationListOut(
        mode="item",
        personalized=False,
        label="More Like This",
        count=len(items),
        items=_items_from_scored(items),
    )


@router.post("/recommendations/what-to-watch", response_model=WhatToWatchOut)
def post_what_to_watch(
    payload: WhatToWatchIn,
    db: DbSession,
    user: OptionalSubscriber,
) -> WhatToWatchOut:
    result = what_to_watch(
        db,
        content_type=payload.content_type,
        genre=payload.genre,
        mood=payload.mood,
        duration=payload.duration,
        language=payload.language,
        subtitles=payload.subtitles,
        release_period=payload.release_period,
        limit=payload.limit,
        subscriber=user,
    )
    return WhatToWatchOut.model_validate(result)


@router.get("/recommendations/what-to-watch", response_model=WhatToWatchOut)
def get_what_to_watch(
    db: DbSession,
    user: OptionalSubscriber,
    content_type: Literal["movie", "series", "either"] = Query("either"),
    genre: str | None = Query(None),
    mood: str | None = Query(None),
    duration: str | None = Query("any"),
    language: str | None = Query("any"),
    subtitles: str | None = Query("optional"),
    release_period: str | None = Query("any"),
    limit: int = Query(8, ge=3, le=10),
) -> WhatToWatchOut:
    result = what_to_watch(
        db,
        content_type=content_type,
        genre=genre,
        mood=mood,
        duration=duration,
        language=language,
        subtitles=subtitles,
        release_period=release_period,
        limit=limit,
        subscriber=user,
    )
    return WhatToWatchOut.model_validate(result)


@router.get("/admin/recommendations/inspect", response_model=RecommendationInspectOut)
def admin_inspect_recommendations(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("movies.read"))],
    subscriber_id: int = Query(..., ge=1),
    limit: int = Query(20, ge=1, le=50),
) -> RecommendationInspectOut:
    """Debug tool: preference signals + ranked candidates. Not a surveillance dashboard."""
    payload = inspect_recommendations(db, subscriber_id=subscriber_id, limit=limit)
    if payload.get("error") == "subscriber_not_found":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")
    return RecommendationInspectOut.model_validate(payload)
