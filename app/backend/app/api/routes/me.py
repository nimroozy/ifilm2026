"""Authenticated subscriber profile, entitlement, devices, and watch history."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from app.core.config import get_settings
from app.core.deps import CurrentSubscriber, DbSession
from app.core.security import TokenError, safe_decode_token
from app.schemas.auth import DeviceOut, EntitlementOut, SubscriberOut
from app.schemas.common import Envelope, Message, paginated
from app.schemas.watch_history import (
    WatchProgressActionOut,
    WatchProgressOut,
    WatchProgressUpdate,
)
from app.schemas.watchlist import (
    WatchlistActionOut,
    WatchlistAddIn,
    WatchlistItemOut,
    WatchlistMembershipOut,
)
from app.services import watch_history as wh
from app.services import watchlist as wl
from app.services.devices import get_owned_device, list_active_devices, revoke_device
from app.services.entitlements import check_entitlement

router = APIRouter(prefix="/me", tags=["me"])


def _require_watch_history() -> None:
    if not get_settings().enable_watch_history:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watch history disabled")


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def _subscriber_out(user) -> SubscriberOut:
    return SubscriberOut(
        id=user.id,
        username=user.username,
        name=user.name,
        branch=user.branch,
        status=user.status,
        package=user.package,
        expiration=user.expiration,
        service_status=getattr(user, "service_status", "unknown") or "unknown",
        max_devices=int(getattr(user, "max_devices", 3) or 3),
        identity_provider=getattr(user, "identity_provider", "local") or "local",
        external_subject=getattr(user, "external_subject", None),
        valid_from=_iso(getattr(user, "valid_from", None)),
        valid_until=_iso(getattr(user, "valid_until", None)),
    )


@router.get("", response_model=SubscriberOut)
def get_me(user: CurrentSubscriber) -> SubscriberOut:
    return _subscriber_out(user)


@router.get("/entitlement", response_model=EntitlementOut)
def get_entitlement(db: DbSession, user: CurrentSubscriber) -> EntitlementOut:
    result = check_entitlement(db, user, refresh=True)
    db.commit()
    return EntitlementOut(
        allowed=result.allowed,
        account_status=result.account_status,
        service_status=result.service_status,
        package_name=result.package_name,
        branch_code=result.branch_code,
        valid_from=_iso(result.valid_from),
        valid_until=_iso(result.valid_until),
        denial_code=result.denial_code,
        safe_reason=result.safe_reason,
        max_devices=result.max_devices,
        source=result.source,
        checked_at=_iso(result.checked_at),
        from_cache=result.from_cache,
    )


@router.get("/devices", response_model=list[DeviceOut])
def get_devices(
    db: DbSession,
    user: CurrentSubscriber,
    request: Request,
    authorization: str | None = Header(default=None),
) -> list[DeviceOut]:
    current_device_session_id: int | None = None
    if authorization and authorization.lower().startswith("bearer "):
        try:
            payload = safe_decode_token(authorization.split(" ", 1)[1])
            raw = payload.get("device_session_id")
            if raw is not None:
                current_device_session_id = int(raw)
        except (TokenError, TypeError, ValueError):
            current_device_session_id = None
    _ = request
    devices = list_active_devices(db, user)
    return [
        DeviceOut(
            id=d.id,
            client_device_id=d.client_device_id,
            name=d.name,
            device_type=d.device_type,
            browser=d.browser,
            ip=d.ip,
            first_seen_at=_iso(d.first_seen_at),
            last_seen_at=_iso(d.last_seen_at),
            current=current_device_session_id is not None and d.id == current_device_session_id,
        )
        for d in devices
    ]


@router.delete("/devices/{device_id}", response_model=Message)
def delete_device(device_id: int, db: DbSession, user: CurrentSubscriber) -> Message:
    device = get_owned_device(db, user, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    revoke_device(db, user, device, reason="user_revoke")
    db.commit()
    return Message(detail="Device revoked")


@router.put("/watch-progress/{asset_id}", response_model=WatchProgressOut)
def put_watch_progress(
    asset_id: str,
    payload: WatchProgressUpdate,
    db: DbSession,
    user: CurrentSubscriber,
) -> WatchProgressOut:
    _require_watch_history()
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
    _require_watch_history()
    out = wh.mark_complete(db, user, asset_id, payload)
    db.commit()
    return out


@router.get("/watch-progress/{asset_id}", response_model=WatchProgressOut)
def get_watch_progress(asset_id: str, db: DbSession, user: CurrentSubscriber) -> WatchProgressOut:
    _require_watch_history()
    out = wh.get_progress(db, user, asset_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Watch progress not found")
    return out


@router.get("/continue-watching", response_model=list[WatchProgressOut])
def continue_watching(db: DbSession, user: CurrentSubscriber) -> list[WatchProgressOut]:
    _require_watch_history()
    return wh.list_continue_watching(db, user)


@router.get("/watch-history", response_model=Envelope[WatchProgressOut])
def watch_history(
    db: DbSession,
    user: CurrentSubscriber,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Envelope[WatchProgressOut]:
    _require_watch_history()
    items, total = wh.list_history(db, user, page=page, page_size=page_size)
    return paginated(items, total=total, page=page, page_size=page_size)


@router.delete("/watch-history/{asset_id}", response_model=WatchProgressActionOut)
def delete_watch_history_item(asset_id: str, db: DbSession, user: CurrentSubscriber) -> WatchProgressActionOut:
    _require_watch_history()
    deleted = wh.delete_one(db, user, asset_id)
    db.commit()
    if deleted < 1:
        raise HTTPException(status_code=404, detail="Watch history item not found")
    return WatchProgressActionOut(detail="ok", deleted=deleted)


@router.delete("/watch-history", response_model=WatchProgressActionOut)
def clear_watch_history(db: DbSession, user: CurrentSubscriber) -> WatchProgressActionOut:
    _require_watch_history()
    deleted = wh.delete_all(db, user)
    db.commit()
    return WatchProgressActionOut(detail="ok", deleted=deleted)


@router.delete("/continue-watching/{asset_id}", response_model=WatchProgressActionOut)
def dismiss_continue_watching(asset_id: str, db: DbSession, user: CurrentSubscriber) -> WatchProgressActionOut:
    """Remove from Continue Watching shelf; history row is retained."""
    _require_watch_history()
    deleted = wh.dismiss_continue_watching(db, user, asset_id)
    db.commit()
    if deleted < 1:
        raise HTTPException(status_code=404, detail="Continue Watching item not found")
    return WatchProgressActionOut(detail="ok", deleted=deleted)


@router.get("/watchlist", response_model=Envelope[WatchlistItemOut])
def get_watchlist(
    db: DbSession,
    user: CurrentSubscriber,
    page: int = Query(1, ge=1),
    page_size: int = Query(40, ge=1, le=100),
) -> Envelope[WatchlistItemOut]:
    items, total = wl.list_watchlist(db, user, page=page, page_size=page_size)
    return paginated(items, total=total, page=page, page_size=page_size)


@router.get("/watchlist/membership", response_model=WatchlistMembershipOut)
def get_watchlist_membership(
    db: DbSession,
    user: CurrentSubscriber,
    movie_id: int | None = Query(default=None, ge=1),
    series_id: int | None = Query(default=None, ge=1),
) -> WatchlistMembershipOut:
    in_list, item_id = wl.membership(db, user, movie_id=movie_id, series_id=series_id)
    return WatchlistMembershipOut(in_watchlist=in_list, item_id=item_id)


@router.post("/watchlist", response_model=WatchlistItemOut, status_code=status.HTTP_201_CREATED)
def add_watchlist_item(payload: WatchlistAddIn, db: DbSession, user: CurrentSubscriber) -> WatchlistItemOut:
    out = wl.add_item(db, user, payload)
    db.commit()
    return out


@router.delete("/watchlist/{item_id}", response_model=WatchlistActionOut)
def delete_watchlist_item(item_id: int, db: DbSession, user: CurrentSubscriber) -> WatchlistActionOut:
    deleted = wl.remove_item(db, user, item_id)
    db.commit()
    if deleted < 1:
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    return WatchlistActionOut(detail="ok", deleted=deleted)


@router.delete("/watchlist", response_model=WatchlistActionOut)
def clear_watchlist(
    db: DbSession,
    user: CurrentSubscriber,
    movie_id: int | None = Query(default=None, ge=1),
    series_id: int | None = Query(default=None, ge=1),
) -> WatchlistActionOut:
    if movie_id is not None or series_id is not None:
        deleted = wl.remove_by_content(db, user, movie_id=movie_id, series_id=series_id)
        db.commit()
        if deleted < 1:
            raise HTTPException(status_code=404, detail="Watchlist item not found")
        return WatchlistActionOut(detail="ok", deleted=deleted)
    deleted = wl.clear_all(db, user)
    db.commit()
    return WatchlistActionOut(detail="ok", deleted=deleted)
