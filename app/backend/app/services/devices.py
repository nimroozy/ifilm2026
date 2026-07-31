"""Subscriber device session management with real concurrent limits."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.media_assets import utcnow
from app.models.media_playback import SESSION_ACTIVE, MediaPlaybackSession
from app.models.subscriber_auth import SubscriberDeviceSession, SubscriberRefreshToken
from app.models.user import Subscriber
from app.services.entitlements import DENY_DEVICE_LIMIT
from app.services.streaming.sessions import revoke_session


class DeviceLimitExceeded(Exception):
    def __init__(self, message: str = "Device limit reached"):
        self.code = DENY_DEVICE_LIMIT
        super().__init__(message)


def list_active_devices(db: Session, subscriber: Subscriber) -> list[SubscriberDeviceSession]:
    return (
        db.query(SubscriberDeviceSession)
        .filter(
            SubscriberDeviceSession.subscriber_id == subscriber.id,
            SubscriberDeviceSession.revoked_at.is_(None),
        )
        .order_by(SubscriberDeviceSession.last_seen_at.desc())
        .all()
    )


def get_owned_device(
    db: Session, subscriber: Subscriber, device_id: int
) -> SubscriberDeviceSession | None:
    return (
        db.query(SubscriberDeviceSession)
        .filter(
            SubscriberDeviceSession.id == device_id,
            SubscriberDeviceSession.subscriber_id == subscriber.id,
        )
        .one_or_none()
    )


def _touch(
    device: SubscriberDeviceSession,
    *,
    name: str,
    device_type: str,
    browser: str,
    ip: str,
    user_agent: str | None,
) -> SubscriberDeviceSession:
    device.last_seen_at = utcnow()
    if name:
        device.name = name
    if device_type:
        device.device_type = device_type
    if browser:
        device.browser = browser
    if ip:
        device.ip = ip
    if user_agent:
        device.user_agent = user_agent
    return device


def register_or_touch_device(
    db: Session,
    subscriber: Subscriber,
    *,
    client_device_id: str,
    name: str = "",
    device_type: str = "desktop",
    browser: str = "",
    ip: str = "",
    user_agent: str | None = None,
    settings: Settings | None = None,
) -> SubscriberDeviceSession:
    cfg = settings or get_settings()
    client_device_id = (client_device_id or "").strip()
    if not client_device_id or len(client_device_id) > 64:
        raise ValueError("Invalid device identifier")

    limit = int(subscriber.max_devices or cfg.subscriber_max_devices_default)
    existing = (
        db.query(SubscriberDeviceSession)
        .filter(
            SubscriberDeviceSession.subscriber_id == subscriber.id,
            SubscriberDeviceSession.client_device_id == client_device_id,
        )
        .one_or_none()
    )

    if existing is not None and existing.revoked_at is None:
        _touch(
            existing,
            name=name,
            device_type=device_type,
            browser=browser,
            ip=ip,
            user_agent=user_agent,
        )
        db.add(existing)
        db.flush()
        return existing

    active_count = (
        db.query(SubscriberDeviceSession)
        .filter(
            SubscriberDeviceSession.subscriber_id == subscriber.id,
            SubscriberDeviceSession.revoked_at.is_(None),
        )
        .count()
    )
    if active_count >= limit:
        raise DeviceLimitExceeded()

    now = utcnow()
    if existing is not None:
        existing.revoked_at = None
        existing.revoke_reason = None
        existing.first_seen_at = now
        _touch(
            existing,
            name=name or existing.name,
            device_type=device_type,
            browser=browser,
            ip=ip,
            user_agent=user_agent,
        )
        db.add(existing)
        db.flush()
        return existing

    row = SubscriberDeviceSession(
        subscriber_id=subscriber.id,
        client_device_id=client_device_id,
        name=name or "Device",
        device_type=device_type or "desktop",
        browser=browser or "",
        ip=ip or "",
        user_agent=user_agent,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(row)
    db.flush()
    return row


def revoke_device(
    db: Session,
    subscriber: Subscriber,
    device: SubscriberDeviceSession,
    *,
    reason: str = "user_revoke",
) -> SubscriberDeviceSession:
    if device.subscriber_id != subscriber.id:
        raise PermissionError("cross-user device access denied")
    if device.revoked_at is not None:
        return device
    now = utcnow()
    device.revoked_at = now
    device.revoke_reason = reason
    db.add(device)

    tokens = (
        db.query(SubscriberRefreshToken)
        .filter(
            SubscriberRefreshToken.device_session_id == device.id,
            SubscriberRefreshToken.revoked_at.is_(None),
        )
        .all()
    )
    for tok in tokens:
        tok.revoked_at = now
        db.add(tok)

    sessions = (
        db.query(MediaPlaybackSession)
        .filter(
            MediaPlaybackSession.device_session_id == device.id,
            MediaPlaybackSession.status == SESSION_ACTIVE,
        )
        .all()
    )
    for session in sessions:
        revoke_session(db, session, reason=f"device_revoked:{reason}")

    db.flush()
    return device


def revoke_all_refresh_for_subscriber(db: Session, subscriber_id: int) -> int:
    now = utcnow()
    rows = (
        db.query(SubscriberRefreshToken)
        .filter(
            SubscriberRefreshToken.subscriber_id == subscriber_id,
            SubscriberRefreshToken.revoked_at.is_(None),
        )
        .all()
    )
    for row in rows:
        row.revoked_at = now
        db.add(row)
    return len(rows)


def revoke_family(db: Session, family_id: str) -> int:
    now = utcnow()
    rows = (
        db.query(SubscriberRefreshToken)
        .filter(
            SubscriberRefreshToken.family_id == family_id,
            SubscriberRefreshToken.revoked_at.is_(None),
        )
        .all()
    )
    for row in rows:
        row.revoked_at = now
        db.add(row)
    return len(rows)
