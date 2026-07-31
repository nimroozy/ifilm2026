"""Protected HLS streaming endpoints (authoritative Phase 7 implementation).

Legacy placeholder stream routes and write_placeholder_package delivery are removed.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials

from app.core.config import get_settings
from app.core.deps import (
    DbSession,
    bearer,
    get_current_admin,
    get_current_subscriber,
    require_permissions,
)
from app.core.features import require_local_streaming
from app.core.security import TokenError, safe_decode_token
from app.models.admin import AdminUser
from app.models.media_playback import MediaPlaybackSession
from app.models.user import Subscriber
from app.schemas.common import Envelope, paginated
from app.schemas.streaming import (
    CustomerPlaybackSessionCreate,
    PlaybackSessionCreate,
    PlaybackSessionCreated,
    PlaybackSessionOut,
    PlaybackSessionRevokeResult,
    StreamingStatusOut,
)
from app.services.streaming.delivery import deliver_master, deliver_segment, deliver_variant
from app.services.streaming.resolve import get_playable_asset_by_id, get_playable_asset_for_content
from app.services.streaming.sessions import (
    create_playback_session,
    master_playlist_url,
    revoke_session,
    revoke_sessions_for_asset,
    revoke_sessions_for_user,
)

PlaybackPrincipal = AdminUser | Subscriber


def get_playback_principal(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
) -> PlaybackPrincipal:
    """Accept either an admin or subscriber JWT for player session creation."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = safe_decode_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token"
        ) from exc
    typ = payload.get("typ")
    if typ == "admin":
        return get_current_admin(db, credentials)
    if typ == "subscriber":
        return get_current_subscriber(db, credentials)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unsupported token type")


def _created_response(session: MediaPlaybackSession, raw_token: str) -> PlaybackSessionCreated:
    settings = get_settings()
    return PlaybackSessionCreated(
        id=session.id,
        media_asset_id=session.media_asset_id,
        media_package_id=session.media_package_id,
        expires_at=session.expires_at,
        playback_token=raw_token,
        master_playlist_url=master_playlist_url(
            api_prefix=settings.api_prefix, token=raw_token
        ),
    )

router = APIRouter(tags=["streaming"])


def _session_out(session: MediaPlaybackSession) -> PlaybackSessionOut:
    return PlaybackSessionOut.model_validate(
        {
            "id": session.id,
            "media_asset_id": session.media_asset_id,
            "media_package_id": session.media_package_id,
            "principal_type": session.principal_type,
            "principal_id": session.principal_id,
            "status": session.status,
            "expires_at": session.expires_at,
            "revoked_at": session.revoked_at,
            "created_at": session.created_at,
            "last_accessed_at": session.last_accessed_at,
            "created_by_admin_id": session.created_by_admin_id,
            "client_ip": session.client_ip,
            "user_agent": session.user_agent,
            "revoke_reason": session.revoke_reason,
            "access_count": session.access_count,
        }
    )


@router.get("/streaming/status", response_model=StreamingStatusOut)
def streaming_status():
    settings = get_settings()
    return StreamingStatusOut(
        enabled=bool(settings.enable_local_streaming),
        supported_principals=["admin", "subscriber"],
        subscriber_entitlement=(
            "deferred — published catalog visibility only; no subscription/payment rules"
        ),
    )


@router.post(
    "/playback/sessions",
    response_model=PlaybackSessionCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_customer_playback_session(
    body: CustomerPlaybackSessionCreate,
    request: Request,
    db: DbSession,
    principal: Annotated[PlaybackPrincipal, Depends(get_playback_principal)],
):
    """Create a protected playback session for the customer player (or admin ops test)."""
    require_local_streaming()
    if body.media_asset_id:
        asset = get_playable_asset_by_id(db, body.media_asset_id)
    else:
        assert body.content_type is not None and body.content_id is not None
        asset = get_playable_asset_for_content(
            db, content_type=body.content_type, content_id=body.content_id
        )
    created_by_admin = principal if isinstance(principal, AdminUser) else None
    session, raw_token = create_playback_session(
        db,
        principal=principal,
        media_asset=asset,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        created_by_admin=created_by_admin,
    )
    return _created_response(session, raw_token)


@router.post(
    "/playback/sessions/{session_id}/revoke",
    response_model=PlaybackSessionOut,
)
def revoke_own_playback_session(
    session_id: str,
    db: DbSession,
    principal: Annotated[PlaybackPrincipal, Depends(get_playback_principal)],
):
    """Revoke a session owned by the current principal."""
    require_local_streaming()
    session = db.get(MediaPlaybackSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Playback session not found")
    if isinstance(principal, AdminUser):
        principal_type, principal_id = "admin", str(principal.id)
    else:
        principal_type, principal_id = "subscriber", str(principal.id)
    if session.principal_type != principal_type or session.principal_id != principal_id:
        raise HTTPException(status_code=403, detail="Cannot revoke another user's session")
    return _session_out(revoke_session(db, session, reason="owner_revoke"))


@router.post(
    "/admin/playback/sessions",
    response_model=PlaybackSessionCreated,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_playback_session(
    body: PlaybackSessionCreate,
    request: Request,
    db: DbSession,
    admin: Annotated[AdminUser, Depends(require_permissions("streaming.manage"))],
):
    require_local_streaming()
    asset = get_playable_asset_by_id(db, body.media_asset_id)
    session, raw_token = create_playback_session(
        db,
        principal=admin,
        media_asset=asset,
        client_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        created_by_admin=admin,
    )
    return _created_response(session, raw_token)


@router.get("/admin/playback/sessions", response_model=Envelope[PlaybackSessionOut])
def admin_list_playback_sessions(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("streaming.read"))],
    page: int = 1,
    page_size: int = 50,
    media_asset_id: str | None = None,
    media_package_id: str | None = None,
    principal_type: str | None = None,
    principal_id: str | None = None,
    session_status: str | None = Query(None, alias="status"),
):
    require_local_streaming()
    query = db.query(MediaPlaybackSession)
    if media_asset_id:
        query = query.filter(MediaPlaybackSession.media_asset_id == media_asset_id)
    if media_package_id:
        query = query.filter(MediaPlaybackSession.media_package_id == media_package_id)
    if principal_type:
        query = query.filter(MediaPlaybackSession.principal_type == principal_type)
    if principal_id:
        query = query.filter(MediaPlaybackSession.principal_id == principal_id)
    if session_status:
        query = query.filter(MediaPlaybackSession.status == session_status)
    total = query.count()
    page = max(1, page)
    page_size = min(max(1, page_size), 100)
    rows = (
        query.order_by(MediaPlaybackSession.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return paginated(
        [_session_out(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/admin/playback/sessions/{session_id}/revoke",
    response_model=PlaybackSessionOut,
)
def admin_revoke_session(
    session_id: str,
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("streaming.manage"))],
):
    require_local_streaming()
    session = db.get(MediaPlaybackSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Playback session not found")
    return _session_out(revoke_session(db, session, reason="admin_revoke"))


@router.post(
    "/admin/playback/sessions/revoke-user",
    response_model=PlaybackSessionRevokeResult,
)
def admin_revoke_user_sessions(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("streaming.manage"))],
    principal_type: str = Query(...),
    principal_id: str = Query(...),
):
    require_local_streaming()
    count = revoke_sessions_for_user(
        db, principal_type=principal_type, principal_id=principal_id, reason="admin_revoke_user"
    )
    return PlaybackSessionRevokeResult(revoked=count)


@router.post(
    "/admin/playback/sessions/revoke-asset",
    response_model=PlaybackSessionRevokeResult,
)
def admin_revoke_asset_sessions(
    db: DbSession,
    _: Annotated[AdminUser, Depends(require_permissions("streaming.manage"))],
    media_asset_id: str = Query(...),
):
    require_local_streaming()
    count = revoke_sessions_for_asset(
        db, media_asset_id=media_asset_id, reason="admin_revoke_asset"
    )
    return PlaybackSessionRevokeResult(revoked=count)


@router.get("/stream/{token}/master.m3u8")
def stream_master(token: str, request: Request, db: DbSession):
    return deliver_master(db, token, request)


@router.get("/stream/{token}/{label}/index.m3u8")
def stream_variant(token: str, label: str, request: Request, db: DbSession):
    return deliver_variant(db, token, label, request)


@router.get("/stream/{token}/{label}/{segment_name}")
def stream_segment(
    token: str, label: str, segment_name: str, request: Request, db: DbSession
):
    return deliver_segment(db, token, label, segment_name, request)


# Keep route module focused on streaming + admin session APIs.
