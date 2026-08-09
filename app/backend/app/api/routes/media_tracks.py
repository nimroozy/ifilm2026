"""Admin APIs for media audio/subtitle track metadata."""

from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentAdmin, DbSession, require_permissions
from app.schemas.media_tracks import MediaTrackCreate, MediaTrackListOut, MediaTrackOut, MediaTrackUpdate
from app.services import media_tracks as tracks_svc

router = APIRouter(tags=["media-tracks"])


@router.get(
    "/admin/media/assets/{asset_id}/tracks",
    response_model=MediaTrackListOut,
    dependencies=[require_permissions("processing.read")],
)
def list_asset_tracks(asset_id: str, db: DbSession, _admin: CurrentAdmin):
    return tracks_svc.list_tracks(db, asset_id)


@router.post(
    "/admin/media/assets/{asset_id}/tracks",
    response_model=MediaTrackOut,
    dependencies=[require_permissions("processing.manage")],
)
def create_asset_track(asset_id: str, body: MediaTrackCreate, db: DbSession, _admin: CurrentAdmin):
    return tracks_svc.create_track(db, asset_id, body)


@router.patch(
    "/admin/media/tracks/{track_id}",
    response_model=MediaTrackOut,
    dependencies=[require_permissions("processing.manage")],
)
def patch_track(track_id: int, body: MediaTrackUpdate, db: DbSession, _admin: CurrentAdmin):
    return tracks_svc.update_track(db, track_id, body)


@router.delete(
    "/admin/media/tracks/{track_id}",
    status_code=204,
    dependencies=[require_permissions("processing.manage")],
)
def remove_track(track_id: int, db: DbSession, _admin: CurrentAdmin):
    tracks_svc.delete_track(db, track_id)
    return None
