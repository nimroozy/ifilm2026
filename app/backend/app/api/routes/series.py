from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_

from app.core.deps import CurrentAdmin, DbSession
from app.models.content import Episode, Series
from app.schemas.common import Message, Page
from app.schemas.content import EpisodeCreate, EpisodeOut, SeriesCreate, SeriesOut, SeriesUpdate

router = APIRouter(tags=["series"])


@router.get("/series", response_model=Page[SeriesOut])
def list_series(
    db: DbSession,
    q: Optional[str] = None,
    genre: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = db.query(Series).filter(Series.published.is_(True))
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Series.title.ilike(like), Series.original_title.ilike(like)))
    total = query.count()
    items = query.order_by(Series.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    if genre:
        items = [s for s in items if genre in (s.genres or [])]
    return Page(items=[SeriesOut.from_orm_series(s) for s in items], total=total, page=page, page_size=page_size)


@router.get("/series/{series_id}", response_model=SeriesOut)
def get_series(series_id: int, db: DbSession):
    series = db.get(Series, series_id)
    if not series or not series.published:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
    return SeriesOut.from_orm_series(series)


@router.get("/series/{series_id}/episodes", response_model=list[EpisodeOut])
def list_episodes(series_id: int, db: DbSession, season: Optional[int] = None):
    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
    query = db.query(Episode).filter(Episode.series_id == series_id, Episode.published.is_(True))
    if season is not None:
        query = query.filter(Episode.season == season)
    return query.order_by(Episode.season.asc(), Episode.episode.asc()).all()


@router.post("/admin/series", response_model=SeriesOut, status_code=status.HTTP_201_CREATED)
def create_series(payload: SeriesCreate, db: DbSession, _: CurrentAdmin):
    series = Series(**payload.model_dump())
    db.add(series)
    db.commit()
    db.refresh(series)
    return SeriesOut.from_orm_series(series)


@router.patch("/admin/series/{series_id}", response_model=SeriesOut)
def update_series(series_id: int, payload: SeriesUpdate, db: DbSession, _: CurrentAdmin):
    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(series, key, value)
    db.add(series)
    db.commit()
    db.refresh(series)
    return SeriesOut.from_orm_series(series)


@router.delete("/admin/series/{series_id}", response_model=Message)
def delete_series(series_id: int, db: DbSession, _: CurrentAdmin):
    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
    db.delete(series)
    db.commit()
    return Message(detail="Series deleted")


@router.post("/admin/series/{series_id}/episodes", response_model=EpisodeOut, status_code=status.HTTP_201_CREATED)
def create_episode(series_id: int, payload: EpisodeCreate, db: DbSession, _: CurrentAdmin):
    series = db.get(Series, series_id)
    if not series:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Series not found")
    episode = Episode(series_id=series_id, **payload.model_dump())
    db.add(episode)
    series.episode_count = (series.episode_count or 0) + 1
    db.add(series)
    db.commit()
    db.refresh(episode)
    return episode
