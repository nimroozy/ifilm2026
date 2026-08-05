"""Playback session lifecycle: create, lookup, revoke, access touch."""

from __future__ import annotations

from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings, get_settings
from app.models.admin import AdminUser
from app.models.media_assets import MediaAsset, utcnow
from app.models.media_playback import (
    PRINCIPAL_ADMIN,
    PRINCIPAL_SUBSCRIBER,
    SESSION_ACTIVE,
    SESSION_EXPIRED,
    SESSION_REVOKED,
    MediaPlaybackSession,
)
from app.models.user import Subscriber
from app.services.media_external_attach import is_external_playable
from app.services.streaming.activation import require_active_completed_package
from app.services.streaming.audit import record_session_event
from app.services.streaming.eligibility import playback_eligibility
from app.services.streaming.tokens import (
    generate_playback_token,
    hash_playback_token,
    hashes_equal,
    is_well_formed_token,
)


class SessionGoneError(Exception):
    """Expired or revoked session (HTTP 410)."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def _principal_fields(principal: AdminUser | Subscriber) -> tuple[str, str]:
    if isinstance(principal, AdminUser):
        return PRINCIPAL_ADMIN, str(principal.id)
    return PRINCIPAL_SUBSCRIBER, str(principal.id)


def create_playback_session(
    db: Session,
    *,
    principal: AdminUser | Subscriber,
    media_asset: MediaAsset,
    settings: Settings | None = None,
    client_ip: str | None = None,
    user_agent: str | None = None,
    created_by_admin: AdminUser | None = None,
    device_session_id: int | None = None,
) -> tuple[MediaPlaybackSession, str]:
    """Create a session. Returns (session, raw_token). Raw token only returned once."""
    cfg = settings or get_settings()
    if not cfg.enable_local_streaming:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local streaming is disabled",
        )

    eligibility = playback_eligibility.can_play(db, principal=principal, media_asset=media_asset)
    if not eligibility.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=eligibility.reason or "Playback not allowed",
        )

    package_id: str | None
    if is_external_playable(media_asset):
        package_id = None
    else:
        package = require_active_completed_package(db, media_asset.id)
        package_id = package.id

    raw_token = generate_playback_token()
    token_hash = hash_playback_token(raw_token, cfg)
    principal_type, principal_id = _principal_fields(principal)
    now = utcnow()
    session = MediaPlaybackSession(
        media_asset_id=media_asset.id,
        media_package_id=package_id,
        principal_type=principal_type,
        principal_id=principal_id,
        token_hash=token_hash,
        status=SESSION_ACTIVE,
        expires_at=now + timedelta(seconds=int(cfg.playback_token_ttl_seconds)),
        created_by_admin_id=(
            created_by_admin.id if created_by_admin is not None else (
                principal.id if isinstance(principal, AdminUser) else None
            )
        ),
        client_ip=client_ip,
        user_agent=(user_agent[:512] if user_agent else None),
        device_session_id=device_session_id if isinstance(principal, Subscriber) else None,
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    record_session_event(
        "playback_session_created",
        session_id=session.id,
        media_asset_id=session.media_asset_id,
        media_package_id=session.media_package_id,
        principal_type=session.principal_type,
    )
    return session, raw_token


def _mark_expired_if_needed(db: Session, session: MediaPlaybackSession) -> MediaPlaybackSession:
    now = utcnow()
    expires = session.expires_at
    if expires.tzinfo is None:
        from datetime import UTC

        expires = expires.replace(tzinfo=UTC)
    if session.status == SESSION_ACTIVE and expires <= now:
        session.status = SESSION_EXPIRED
        db.add(session)
        db.commit()
        db.refresh(session)
    return session


def lookup_session_by_token(
    db: Session, token: str, *, settings: Settings | None = None
) -> MediaPlaybackSession:
    if not is_well_formed_token(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")
    cfg = settings or get_settings()
    if not cfg.enable_local_streaming:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Local streaming is disabled",
        )
    digest = hash_playback_token(token, cfg)
    session = (
        db.query(MediaPlaybackSession)
        .options(
            joinedload(MediaPlaybackSession.media_package),
            joinedload(MediaPlaybackSession.media_asset),
        )
        .filter(MediaPlaybackSession.token_hash == digest)
        .one_or_none()
    )
    if session is None:
        # Constant-time-ish miss: still compare against a dummy hash.
        hashes_equal(digest, "0" * 64)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown token")

    session = _mark_expired_if_needed(db, session)
    if session.status == SESSION_REVOKED:
        raise SessionGoneError("revoked", "Playback session revoked")
    if session.status == SESSION_EXPIRED:
        raise SessionGoneError("expired", "Playback session expired")
    if session.status != SESSION_ACTIVE:
        raise SessionGoneError("inactive", "Playback session is not active")

    # Ensure package still active and matches session binding.
    package = session.media_package
    if (
        package is None
        or package.id != session.media_package_id
        or not package.is_active
        or package.status != "completed"
    ):
        raise SessionGoneError("package_inactive", "Active package no longer available")

    return session


def touch_session_access(
    db: Session,
    session: MediaPlaybackSession,
    *,
    settings: Settings | None = None,
) -> None:
    """Throttled last_accessed_at update (avoid per-segment writes)."""
    cfg = settings or get_settings()
    now = utcnow()
    throttle = int(cfg.playback_access_touch_seconds)
    last = session.last_accessed_at
    if last is not None:
        if last.tzinfo is None:
            from datetime import UTC

            last = last.replace(tzinfo=UTC)
        if (now - last).total_seconds() < throttle:
            return
    session.last_accessed_at = now
    session.access_count = int(session.access_count or 0) + 1
    db.add(session)
    db.commit()


def revoke_session(
    db: Session,
    session: MediaPlaybackSession,
    *,
    reason: str | None = None,
) -> MediaPlaybackSession:
    if session.status == SESSION_REVOKED:
        return session
    session.status = SESSION_REVOKED
    session.revoked_at = utcnow()
    session.revoke_reason = reason
    db.add(session)
    db.commit()
    db.refresh(session)
    record_session_event(
        "playback_session_revoked",
        session_id=session.id,
        media_asset_id=session.media_asset_id,
        media_package_id=session.media_package_id,
        principal_type=session.principal_type,
        reason=reason,
    )
    return session


def revoke_sessions_for_user(
    db: Session, *, principal_type: str, principal_id: str, reason: str | None = None
) -> int:
    rows = (
        db.query(MediaPlaybackSession)
        .filter(
            MediaPlaybackSession.principal_type == principal_type,
            MediaPlaybackSession.principal_id == principal_id,
            MediaPlaybackSession.status == SESSION_ACTIVE,
        )
        .all()
    )
    count = 0
    for session in rows:
        revoke_session(db, session, reason=reason)
        count += 1
    return count


def revoke_sessions_for_asset(
    db: Session, *, media_asset_id: str, reason: str | None = None
) -> int:
    rows = (
        db.query(MediaPlaybackSession)
        .filter(
            MediaPlaybackSession.media_asset_id == media_asset_id,
            MediaPlaybackSession.status == SESSION_ACTIVE,
        )
        .all()
    )
    count = 0
    for session in rows:
        revoke_session(db, session, reason=reason)
        count += 1
    return count


def master_playlist_url(*, api_prefix: str, token: str) -> str:
    prefix = api_prefix.rstrip("/") or "/api"
    return f"{prefix}/stream/{token}/master.m3u8"


def stream_base_path(*, api_prefix: str, token: str) -> str:
    prefix = api_prefix.rstrip("/") or "/api"
    return f"{prefix}/stream/{token}"
