from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.deps import DbSession, admin_permissions, get_current_admin
from app.models.admin import AdminUser
from app.models.content import Movie, Series
from app.services.catalog import movie_out, series_out
from app.services.tmdb.artwork import build_image_url, download_artwork
from app.services.tmdb.client import TMDBClient, TMDBClientError
from app.services.tmdb.import_service import (
    import_movie,
    import_series,
    preview_movie,
    preview_series,
)
from app.services.tmdb.refresh import refresh_real_demo_metadata

router = APIRouter(tags=["tmdb-admin"])


def require_tmdb_admin(admin: Annotated[AdminUser, Depends(get_current_admin)]) -> AdminUser:
    perms = admin_permissions(admin)
    allowed = {"catalog.edit", "movies.manage", "movies"}
    if perms.isdisjoint(allowed):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    return admin


TMDBAdmin = Annotated[AdminUser, Depends(require_tmdb_admin)]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    media_type: Literal["movie", "series"] = "movie"
    page: int = Field(default=1, ge=1)


class PreviewRequest(BaseModel):
    tmdb_id: int
    media_type: Literal["movie", "series"] = "movie"


class ImportRequest(PreviewRequest):
    force: bool = False


class RefreshRequest(BaseModel):
    force: bool = False


class ReplaceArtworkRequest(BaseModel):
    media_type: Literal["movie", "series"]
    entity_id: int
    kinds: list[Literal["poster", "backdrop", "logo"]] = Field(min_length=1)


def _client() -> TMDBClient:
    settings = get_settings()
    client = TMDBClient(settings)
    if not client.enabled:
        raise HTTPException(status_code=400, detail="TMDB is disabled or TMDB_API_READ_TOKEN is missing")
    return client


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    return value


@router.get("/admin/tools/tmdb/search")
def search_tmdb_get(
    db: DbSession,
    _: TMDBAdmin,
    query: str = Query(min_length=1),
    media_type: Literal["movie", "series"] = "movie",
    page: int = Query(1, ge=1),
):
    _ = db
    client = _client()
    try:
        return client.search_movie(query, page=page) if media_type == "movie" else client.search_tv(query, page=page)
    except TMDBClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/admin/tools/tmdb/search")
def search_tmdb_post(payload: SearchRequest, db: DbSession, _: TMDBAdmin):
    _ = db
    client = _client()
    try:
        return (
            client.search_movie(payload.query, page=payload.page)
            if payload.media_type == "movie"
            else client.search_tv(payload.query, page=payload.page)
        )
    except TMDBClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/admin/tools/tmdb/preview")
def preview_tmdb(payload: PreviewRequest, db: DbSession, _: TMDBAdmin):
    _ = db
    client = _client()
    try:
        data = (
            preview_movie(get_settings(), payload.tmdb_id, client=client)
            if payload.media_type == "movie"
            else preview_series(get_settings(), payload.tmdb_id, client=client)
        )
    except TMDBClientError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return _jsonable(data)


@router.post("/admin/tools/tmdb/import")
def import_tmdb_draft(payload: ImportRequest, db: DbSession, _: TMDBAdmin):
    settings = get_settings()
    client = _client()
    try:
        if payload.media_type == "movie":
            result = import_movie(db, settings, payload.tmdb_id, client=client, force=payload.force)
            db.commit()
            movie = db.get(Movie, result.entity_id)
            if movie is None:
                raise HTTPException(status_code=404, detail="Movie not found after import")
            item = movie_out(movie)
        else:
            result = import_series(db, settings, payload.tmdb_id, client=client, force=payload.force)
            db.commit()
            series = db.get(Series, result.entity_id)
            if series is None:
                raise HTTPException(status_code=404, detail="Series not found after import")
            item = series_out(series)
    except TMDBClientError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return {"result": _jsonable(result), "item": item}


@router.post("/admin/tools/tmdb/refresh")
def refresh_tmdb_demo(payload: RefreshRequest, db: DbSession, _: TMDBAdmin):
    settings = get_settings()
    client = _client()
    try:
        results = refresh_real_demo_metadata(db, settings, client=client, force=payload.force)
        db.commit()
    except TMDBClientError as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return {"refreshed": len(results), "results": _jsonable(results)}


@router.post("/admin/tools/tmdb/artwork/replace")
def replace_tmdb_artwork(payload: ReplaceArtworkRequest, db: DbSession, _: TMDBAdmin):
    settings = get_settings()
    client = _client()
    if payload.media_type == "movie":
        entity = db.get(Movie, payload.entity_id)
        if entity is None or not entity.tmdb_id:
            raise HTTPException(status_code=404, detail="Movie not found or missing TMDB id")
        details = client.movie_details(entity.tmdb_id)
    else:
        entity = db.get(Series, payload.entity_id)
        if entity is None or not entity.tmdb_id:
            raise HTTPException(status_code=404, detail="Series not found or missing TMDB id")
        details = client.tv_details(entity.tmdb_id)
    config = client.configuration()
    selected = {
        "poster": details.get("poster_path"),
        "backdrop": details.get("backdrop_path"),
        "logo": (((details.get("images") or {}).get("logos") or [{}])[0] or {}).get("file_path"),
    }
    changed: dict[str, str] = {}
    try:
        for kind in payload.kinds:
            path = selected.get(kind)
            if not path:
                continue
            stored = download_artwork(
                settings,
                build_image_url(settings, str(path), size="original"),
                kind=kind,
                tmdb_id=int(entity.tmdb_id),
                tmdb_configuration=config,
            )
            field = {"poster": "poster_url", "backdrop": "backdrop_url", "logo": "logo_url"}[kind]
            setattr(entity, field, stored.url)
            changed[field] = stored.url
        db.add(entity)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"changed": changed}
