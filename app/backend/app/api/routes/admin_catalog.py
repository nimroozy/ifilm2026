from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import DbSession, require_permissions
from app.models.admin import AdminUser
from app.models.content import Episode, Genre, Movie, Season, Series
from app.schemas.content import DashboardStats
from app.services.catalog import not_deleted

router = APIRouter(tags=["admin-catalog"])


@router.get("/admin/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("movies.read"))],
) -> DashboardStats:
    return DashboardStats(
        total_movies=not_deleted(db.query(Movie), Movie).count(),
        published_movies=not_deleted(db.query(Movie), Movie)
        .filter(Movie.status == "published")
        .count(),
        draft_movies=not_deleted(db.query(Movie), Movie).filter(Movie.status == "draft").count(),
        total_series=not_deleted(db.query(Series), Series).count(),
        published_series=not_deleted(db.query(Series), Series)
        .filter(Series.status == "published")
        .count(),
        total_seasons=not_deleted(db.query(Season), Season).count(),
        total_episodes=not_deleted(db.query(Episode), Episode).count(),
        total_genres=db.query(Genre).count(),
    )
