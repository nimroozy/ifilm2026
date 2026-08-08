from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import joinedload

from app.core.deps import DbSession, require_permissions
from app.models.admin import AdminUser
from app.models.content import Episode, Season, Series
from app.models.enums import SORT_OPTIONS
from app.schemas.common import Envelope, Message, paginated
from app.schemas.content import (
    EpisodeOut,
    PublishAction,
    SeasonCreate,
    SeasonOut,
    SeriesCreate,
    SeriesOut,
    SeriesUpdate,
)
from app.services.catalog import (
    apply_sort,
    ensure_unique_imdb,
    episode_out,
    filter_catalog_query,
    get_series,
    load_genres,
    make_slug_for_series,
    not_deleted,
    resolve_series,
    season_out,
    series_out,
    soft_delete,
    utcnow,
)
from app.services.catalog_availability import (
    availability_for_series,
    item_has_dub,
    item_has_subtitles,
)
from app.services.publishing import workflow as publishing_workflow

router = APIRouter(tags=["series"])

SortParam = Annotated[str, Query(description="Sort order")]


def _list_query(
    db: DbSession,
    *,
    q: str | None,
    genre: str | None,
    year: int | None,
    language: str | None,
    featured: bool | None,
    trending: bool | None,
    status_filter: str | None,
    published_only: bool,
    sort: str,
):
    query = db.query(Series).options(
        joinedload(Series.genre_links),
        joinedload(Series.seasons).joinedload(Season.episodes),
    )
    query = filter_catalog_query(
        query,
        Series,
        q=q,
        genre=genre,
        year=year,
        language=language,
        featured=featured,
        trending=trending,
        status=status_filter,
        published_only=published_only,
    )
    return apply_sort(query, Series, sort if sort in SORT_OPTIONS else "newest")


def _paginate_series(
    db: DbSession,
    query,
    *,
    page: int,
    page_size: int,
    has_dubbed: bool | None = None,
    has_subtitles: bool | None = None,
    public_counts: bool = False,
    locale: str | None = None,
):
    if not has_dubbed and not has_subtitles:
        total = query.count()
        items = query.offset((page - 1) * page_size).limit(page_size).all()
        return paginated(
            [
                series_out(s, public_counts=public_counts, db=db, locale=locale)
                for s in items
            ],
            total=total,
            page=page,
            page_size=page_size,
        )

    candidates = query.all()
    filtered = []
    for series in candidates:
        audio_av, sub_av = availability_for_series(series, db)
        if has_dubbed and not item_has_dub(audio_av):
            continue
        if has_subtitles and not item_has_subtitles(sub_av):
            continue
        filtered.append(
            series_out(series, public_counts=public_counts, db=db, locale=locale)
        )
    total = len(filtered)
    start = (page - 1) * page_size
    return paginated(filtered[start : start + page_size], total=total, page=page, page_size=page_size)


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


def _public_seasons(series: Series) -> list[Season]:
    return [
        s
        for s in (series.seasons or [])
        if s.deleted_at is None and s.status == "published"
    ]


def _public_episodes(series: Series, season_number: int | None = None) -> list[Episode]:
    episodes: list[Episode] = []
    for season in _public_seasons(series):
        if season_number is not None and season.season_number != season_number:
            continue
        for episode in season.episodes or []:
            if episode.deleted_at is None and episode.status == "published":
                episodes.append(episode)
    episodes.sort(key=lambda e: (e.season.season_number if e.season else 0, e.episode_number))
    return episodes


@router.get("/series", response_model=Envelope[SeriesOut])
def list_series(
    db: DbSession,
    q: str | None = None,
    genre: str | None = None,
    year: int | None = None,
    language: str | None = None,
    featured: bool | None = None,
    trending: bool | None = None,
    has_dubbed: bool | None = None,
    has_subtitles: bool | None = None,
    sort: SortParam = "newest",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    locale: str | None = Query(None, description="UI locale: en|fa|ps"),
) -> Envelope[SeriesOut]:
    query = _list_query(
        db,
        q=q,
        genre=genre,
        year=year,
        language=language,
        featured=featured,
        trending=trending,
        status_filter=None,
        published_only=True,
        sort=sort,
    )
    return _paginate_series(
        db,
        query,
        page=page,
        page_size=page_size,
        has_dubbed=has_dubbed,
        has_subtitles=has_subtitles,
        public_counts=True,
        locale=locale,
    )


@router.get("/series/{id_or_slug}", response_model=SeriesOut)
def get_public_series(
    id_or_slug: str,
    db: DbSession,
    locale: str | None = Query(None, description="UI locale: en|fa|ps"),
) -> SeriesOut:
    return series_out(
        resolve_series(db, id_or_slug, published_only=True),
        public_counts=True,
        db=db,
        locale=locale,
    )


@router.get("/series/{id_or_slug}/seasons", response_model=list[SeasonOut])
def list_public_seasons(id_or_slug: str, db: DbSession) -> list[SeasonOut]:
    series = resolve_series(db, id_or_slug, published_only=True)
    seasons = sorted(_public_seasons(series), key=lambda s: s.season_number)
    return [season_out(s) for s in seasons]


@router.get("/series/{id_or_slug}/seasons/{season_number}", response_model=SeasonOut)
def get_public_season(id_or_slug: str, season_number: int, db: DbSession) -> SeasonOut:
    series = resolve_series(db, id_or_slug, published_only=True)
    for season in _public_seasons(series):
        if season.season_number == season_number:
            return season_out(season)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Season not found")


@router.get("/series/{id_or_slug}/episodes", response_model=list[EpisodeOut])
def list_public_episodes(
    id_or_slug: str,
    db: DbSession,
    season: int | None = None,
    locale: str | None = Query(None, description="UI locale: en|fa|ps"),
) -> list[EpisodeOut]:
    series = resolve_series(db, id_or_slug, published_only=True)
    return [episode_out(e, db, locale=locale) for e in _public_episodes(series, season)]


@router.get("/admin/series", response_model=Envelope[SeriesOut])
def admin_list_series(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("series.read"))],
    q: str | None = None,
    genre: str | None = None,
    year: int | None = None,
    language: str | None = None,
    featured: bool | None = None,
    trending: bool | None = None,
    status: str | None = None,
    sort: SortParam = "newest",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Envelope[SeriesOut]:
    query = _list_query(
        db,
        q=q,
        genre=genre,
        year=year,
        language=language,
        featured=featured,
        trending=trending,
        status_filter=status,
        published_only=False,
        sort=sort,
    )
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return paginated([series_out(s, db=db) for s in items], total=total, page=page, page_size=page_size)


@router.post("/admin/series", response_model=SeriesOut, status_code=status.HTTP_201_CREATED)
def create_series(
    payload: SeriesCreate,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("series.manage"))],
) -> SeriesOut:
    data = payload.model_dump(exclude={"genre_ids", "slug"})
    data["status"] = "draft"
    slug = make_slug_for_series(db, payload.title, payload.slug)
    ensure_unique_imdb(db, Series, payload.imdb_id)
    genres = load_genres(db, payload.genre_ids)
    series = Series(**data, slug=slug)
    series.genre_links = genres
    db.add(series)
    db.commit()
    return series_out(get_series(db, series.id), db=db)


@router.get("/admin/series/{series_id}", response_model=SeriesOut)
def admin_get_series(
    series_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("series.read"))],
) -> SeriesOut:
    return series_out(get_series(db, series_id), db=db)


@router.patch("/admin/series/{series_id}", response_model=SeriesOut)
def update_series(
    series_id: int,
    payload: SeriesUpdate,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("series.manage"))],
) -> SeriesOut:
    import logging

    series = get_series(db, series_id)
    data = payload.model_dump(exclude_unset=True, exclude={"genre_ids", "slug"})
    if "title" in payload.model_fields_set or "slug" in payload.model_fields_set:
        title = payload.title if payload.title is not None else series.title
        slug_value = payload.slug if "slug" in payload.model_fields_set else series.slug
        series.slug = make_slug_for_series(db, title, slug_value, exclude_id=series.id)
    if "imdb_id" in payload.model_fields_set:
        ensure_unique_imdb(db, Series, payload.imdb_id, exclude_id=series.id)
    track_fields = ("audio", "subtitles", "dubbed")
    before_tracks = {k: list(getattr(series, k) or []) for k in track_fields}
    for key, value in data.items():
        if hasattr(series, key):
            setattr(series, key, value)
    if "genre_ids" in payload.model_fields_set and payload.genre_ids is not None:
        series.genre_links = load_genres(db, payload.genre_ids)
    series.updated_at = utcnow()
    db.add(series)
    db.commit()
    after_tracks = {k: list(getattr(series, k) or []) for k in track_fields}
    changed = {
        k: {"from": before_tracks[k], "to": after_tracks[k]}
        for k in track_fields
        if before_tracks[k] != after_tracks[k]
    }
    if changed:
        logging.getLogger("app.catalog.audit").info(
            "catalog_audit event=series_availability_updated details=%s",
            {"series_id": series.id, "admin_id": admin.id, "changes": changed},
        )
    return series_out(get_series(db, series.id), db=db)


@router.delete("/admin/series/{series_id}", response_model=Message)
def delete_series(
    series_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("series.manage"))],
) -> Message:
    series = get_series(db, series_id)
    soft_delete(series)
    series.updated_at = utcnow()
    for season in series.seasons or []:
        if season.deleted_at is None:
            soft_delete(season)
            season.updated_at = utcnow()
            db.add(season)
            for episode in season.episodes or []:
                if episode.deleted_at is None:
                    soft_delete(episode)
                    episode.updated_at = utcnow()
                    db.add(episode)
    db.add(series)
    db.commit()
    return Message(detail="Series deleted")


@router.post("/admin/series/{series_id}/publish", response_model=PublishAction)
def publish_series(
    series_id: int,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("catalog.publish"))],
) -> PublishAction:
    series = publishing_workflow.workflow_http(
        publishing_workflow.publish, db, entity_type="series", entity_id=series_id, actor=admin
    )
    db.commit()
    return PublishAction(detail="ok", status=series.status)


@router.post("/admin/series/{series_id}/unpublish", response_model=PublishAction)
def unpublish_series(
    series_id: int,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("catalog.publish"))],
) -> PublishAction:
    series = publishing_workflow.workflow_http(
        publishing_workflow.unpublish, db, entity_type="series", entity_id=series_id, actor=admin
    )
    db.commit()
    return PublishAction(detail="ok", status=series.status)


@router.get("/admin/series/{series_id}/seasons", response_model=list[SeasonOut])
def admin_list_seasons(
    series_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("series.read"))],
) -> list[SeasonOut]:
    series = get_series(db, series_id)
    seasons = sorted(
        [s for s in (series.seasons or []) if s.deleted_at is None],
        key=lambda s: s.season_number,
    )
    return [season_out(s) for s in seasons]


@router.post(
    "/admin/series/{series_id}/seasons",
    response_model=SeasonOut,
    status_code=status.HTTP_201_CREATED,
)
def create_season(
    series_id: int,
    payload: SeasonCreate,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("series.manage"))],
) -> SeasonOut:
    series = get_series(db, series_id)
    _ensure_unique_season_number(db, series.id, payload.season_number)
    season = Season(series_id=series.id, **{**payload.model_dump(), "status": "draft"})
    db.add(season)
    db.commit()
    db.refresh(season)
    return season_out(season)
