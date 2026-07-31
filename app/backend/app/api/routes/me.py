"""Authenticated subscriber watch progress and history APIs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status

from app.core.config import get_settings
from app.core.deps import CurrentSubscriber, DbSession
from app.schemas.common import Envelope, paginated
from app.schemas.watch_history import (
    WatchProgressActionOut,
    WatchProgressOut,
    WatchProgressUpdate,
)
from app.services import watch_history as wh

router = APIRouter(prefix="/me", tags=["watch-history"])


def _require_enabled() -> None:
    if not get_settings().enable_watch_history:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch history disabled")


@router.put("/watch-progress/{asset_id}", response_model=WatchProgressOut)
def put_watch_progress(
    asset_id: str,
    payload: WatchProgressUpdate,
    db: DbSession,
    user: CurrentSubscriber,
) -> WatchProgressOut:
    _require_enabled()
    out = wh.upsert_progress(db, user, asset_id, payload)
    db.commit()
    return out


@router.post("/watch-progress/{asset_id}/complete", response_model=WatchProgressOut)
def complete_watch_progress(
    asset_id: str,
    payload: WatchProgressUpdate,
    db: DbSession,
    user: CurrentSubscriber,
) -> WatchProgressOut:
    _require_enabled()
    out = wh.mark_complete(db, user, asset_id, payload)
    db.commit()
    return out


@router.get("/watch-progress/{asset_id}", response_model=WatchProgressOut)
def get_watch_progress(asset_id: str, db: DbSession, user: CurrentSubscriber) -> WatchProgressOut:
    _require_enabled()
    out = wh.get_progress(db, user, asset_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Watch progress not found")
    return out


@router.get("/continue-watching", response_model=list[WatchProgressOut])
def continue_watching(db: DbSession, user: CurrentSubscriber) -> list[WatchProgressOut]:
    _require_enabled()
    return wh.list_continue_watching(db, user)


@router.get("/watch-history", response_model=Envelope[WatchProgressOut])
def watch_history(
    db: DbSession,
    user: CurrentSubscriber,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Envelope[WatchProgressOut]:
    _require_enabled()
    items, total = wh.list_history(db, user, page=page, page_size=page_size)
    return paginated(items, total=total, page=page, page_size=page_size)


@router.delete("/watch-history/{asset_id}", response_model=WatchProgressActionOut)
def delete_watch_history_item(asset_id: str, db: DbSession, user: CurrentSubscriber) -> WatchProgressActionOut:
    _require_enabled()
    deleted = wh.delete_one(db, user, asset_id)
    db.commit()
    if deleted < 1:
        raise HTTPException(status_code=404, detail="Watch history item not found")
    return WatchProgressActionOut(detail="ok", deleted=deleted)


@router.delete("/watch-history", response_model=WatchProgressActionOut)
def clear_watch_history(db: DbSession, user: CurrentSubscriber) -> WatchProgressActionOut:
    _require_enabled()
    deleted = wh.delete_all(db, user)
    db.commit()
    return WatchProgressActionOut(detail="ok", deleted=deleted)
