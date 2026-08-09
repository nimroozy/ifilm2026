"""Admin APIs for media audio/subtitle track metadata."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.deps import DbSession, require_permissions
from app.models.admin import AdminUser
from app.schemas.media_tracks import (
    MediaTrackCreate,
    MediaTrackListOut,
    MediaTrackOut,
    MediaTrackUpdate,
)
from app.services import media_tracks as tracks_svc

router = APIRouter(tags=["media-tracks"])


@router.get(
    "/admin/media/assets/{asset_id}/tracks",
    response_model=MediaTrackListOut,
)
def list_asset_tracks(
    asset_id: str,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("processing.read"))],
):
    return tracks_svc.list_tracks(db, asset_id)


@router.post(
    "/admin/media/assets/{asset_id}/tracks",
    response_model=MediaTrackOut,
)
def create_asset_track(
    asset_id: str,
    body: MediaTrackCreate,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("processing.manage"))],
):
    return tracks_svc.create_track(db, asset_id, body)


@router.patch(
    "/admin/media/tracks/{track_id}",
    response_model=MediaTrackOut,
)
def patch_track(
    track_id: int,
    body: MediaTrackUpdate,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("processing.manage"))],
):
    return tracks_svc.update_track(db, track_id, body)


@router.delete(
    "/admin/media/tracks/{track_id}",
    status_code=204,
)
def remove_track(
    track_id: int,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("processing.manage"))],
):
    tracks_svc.delete_track(db, track_id)
    return None
