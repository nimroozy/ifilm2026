from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import joinedload

from app.core.deps import DbSession, require_permissions
from app.models.admin import AdminUser
from app.models.content import Episode, Season
from app.schemas.common import Message
from app.schemas.content import (
    EpisodeCreate,
    EpisodeOut,
    EpisodeUpdate,
    PublishAction,
    SeasonOut,
    SeasonUpdate,
)
from app.services.catalog import (
    episode_out,
    not_deleted,
    season_out,
    soft_delete,
    utcnow,
)
from app.services.publishing import workflow as publishing_workflow

router = APIRouter(tags=["seasons"])


@router.get("/seasons/{season_id}/episodes", response_model=list[EpisodeOut])
def list_public_season_episodes(season_id: int, db: DbSession) -> list[EpisodeOut]:
    """Published episodes for a published, non-deleted season whose series is published."""
    season = (
        db.query(Season)
        .options(joinedload(Season.episodes), joinedload(Season.series))
        .filter(Season.id == season_id)
        .first()
    )
    if (
        not season
        or season.deleted_at is not None
        or season.status != "published"
        or not season.series
        or season.series.deleted_at is not None
        or season.series.status != "published"
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    episodes = sorted(
        [
            e
            for e in (season.episodes or [])
            if e.deleted_at is None and e.status == "published"
        ],
        key=lambda e: e.episode_number,
    )
    return [episode_out(e) for e in episodes]


def _get_season(db: DbSession, season_id: int) -> Season:
    season = (
        db.query(Season)
        .options(joinedload(Season.episodes), joinedload(Season.series))
        .filter(Season.id == season_id)
        .first()
    )
    if not season or season.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")
    return season


def _get_episode(db: DbSession, episode_id: int) -> Episode:
    episode = (
        db.query(Episode)
        .options(joinedload(Episode.season), joinedload(Episode.series))
        .filter(Episode.id == episode_id)
        .first()
    )
    if not episode or episode.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    return episode


def _ensure_unique_season_number(
    db: DbSession,
    series_id: int,
    season_number: int,
    *,
    exclude_id: int | None = None,
) -> None:
    query = not_deleted(db.query(Season), Season).filter(
        Season.series_id == series_id,
        Season.season_number == season_number,
    )
    if exclude_id is not None:
        query = query.filter(Season.id != exclude_id)
    if query.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Season number already exists for this series",
        )


def _ensure_unique_episode_number(
    db: DbSession,
    season_id: int,
    episode_number: int,
    *,
    exclude_id: int | None = None,
) -> None:
    query = not_deleted(db.query(Episode), Episode).filter(
        Episode.season_id == season_id,
        Episode.episode_number == episode_number,
    )
    if exclude_id is not None:
        query = query.filter(Episode.id != exclude_id)
    if query.first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Episode number already exists for this season",
        )


@router.get("/admin/seasons/{season_id}", response_model=SeasonOut)
def get_season(
    season_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("series.read"))],
) -> SeasonOut:
    return season_out(_get_season(db, season_id))


@router.patch("/admin/seasons/{season_id}", response_model=SeasonOut)
def update_season(
    season_id: int,
    payload: SeasonUpdate,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("series.manage"))],
) -> SeasonOut:
    season = _get_season(db, season_id)
    data = payload.model_dump(exclude_unset=True)
    if "season_number" in payload.model_fields_set and payload.season_number is not None:
        _ensure_unique_season_number(
            db,
            season.series_id,
            payload.season_number,
            exclude_id=season.id,
        )
    for key, value in data.items():
        setattr(season, key, value)
    season.updated_at = utcnow()
    db.add(season)
    db.commit()
    db.refresh(season)
    return season_out(season)


@router.delete("/admin/seasons/{season_id}", response_model=Message)
def delete_season(
    season_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("series.manage"))],
) -> Message:
    season = _get_season(db, season_id)
    soft_delete(season)
    season.updated_at = utcnow()
    for episode in season.episodes or []:
        if episode.deleted_at is None:
            soft_delete(episode)
            episode.updated_at = utcnow()
            db.add(episode)
    db.add(season)
    db.commit()
    return Message(detail="Season deleted")


@router.get("/admin/seasons/{season_id}/episodes", response_model=list[EpisodeOut])
def list_season_episodes(
    season_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("series.read"))],
) -> list[EpisodeOut]:
    season = _get_season(db, season_id)
    episodes = sorted(
        [e for e in (season.episodes or []) if e.deleted_at is None],
        key=lambda e: e.episode_number,
    )
    return [episode_out(e) for e in episodes]


@router.post(
    "/admin/seasons/{season_id}/episodes",
    response_model=EpisodeOut,
    status_code=status.HTTP_201_CREATED,
)
def create_episode(
    season_id: int,
    payload: EpisodeCreate,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("series.manage"))],
) -> EpisodeOut:
    season = _get_season(db, season_id)
    _ensure_unique_episode_number(db, season.id, payload.episode_number)
    episode = Episode(
        season_id=season.id,
        series_id=season.series_id,
        **{**payload.model_dump(), "status": "draft"},
    )
    db.add(episode)
    db.commit()
    return episode_out(_get_episode(db, episode.id))


@router.get("/admin/episodes/{episode_id}", response_model=EpisodeOut)
def get_episode(
    episode_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("series.read"))],
) -> EpisodeOut:
    return episode_out(_get_episode(db, episode_id))


@router.patch("/admin/episodes/{episode_id}", response_model=EpisodeOut)
def update_episode(
    episode_id: int,
    payload: EpisodeUpdate,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("series.manage"))],
) -> EpisodeOut:
    episode = _get_episode(db, episode_id)
    data = payload.model_dump(exclude_unset=True)
    if "episode_number" in payload.model_fields_set and payload.episode_number is not None:
        _ensure_unique_episode_number(
            db,
            episode.season_id,
            payload.episode_number,
            exclude_id=episode.id,
        )
    for key, value in data.items():
        setattr(episode, key, value)
    episode.updated_at = utcnow()
    db.add(episode)
    db.commit()
    return episode_out(_get_episode(db, episode.id))


@router.delete("/admin/episodes/{episode_id}", response_model=Message)
def delete_episode(
    episode_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("series.manage"))],
) -> Message:
    episode = _get_episode(db, episode_id)
    soft_delete(episode)
    episode.updated_at = utcnow()
    db.add(episode)
    db.commit()
    return Message(detail="Episode deleted")


@router.post("/admin/episodes/{episode_id}/publish", response_model=PublishAction)
def publish_episode_route(
    episode_id: int,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("catalog.publish"))],
) -> PublishAction:
    episode = publishing_workflow.workflow_http(
        publishing_workflow.publish, db, entity_type="episode", entity_id=episode_id, actor=admin
    )
    db.commit()
    return PublishAction(detail="ok", status=episode.status)


@router.post("/admin/episodes/{episode_id}/unpublish", response_model=PublishAction)
def unpublish_episode(
    episode_id: int,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("catalog.publish"))],
) -> PublishAction:
    episode = publishing_workflow.workflow_http(
        publishing_workflow.unpublish, db, entity_type="episode", entity_id=episode_id, actor=admin
    )
    db.commit()
    return PublishAction(detail="ok", status=episode.status)
