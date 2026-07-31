"""Subscriber authentication orchestration: login, refresh, logout."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_refresh_token,
    new_token_family_id,
)
from app.models.media_assets import utcnow
from app.models.subscriber_auth import SubscriberRefreshToken
from app.models.user import Subscriber
from app.services.devices import (
    DeviceLimitExceeded,
    register_or_touch_device,
    revoke_all_refresh_for_subscriber,
    revoke_family,
)
from app.services.entitlements import (
    apply_entitlement_to_subscriber,
    entitlement_from_auth_result,
    persist_snapshot,
)
from app.services.identity import GENERIC_FAILURE, get_identity_provider
from app.services.identity.provider import PROVIDER_FIXTURE, PROVIDER_RADIUS


@dataclass
class AuthTokens:
    access_token: str
    refresh_token: str
    expires_in: int


@dataclass
class LoginOutcome:
    ok: bool
    tokens: AuthTokens | None = None
    subscriber: Subscriber | None = None
    http_status: int = 401
    code: str = "invalid_credentials"
    detail: str = GENERIC_FAILURE


def _issue_tokens(
    db: Session,
    subscriber: Subscriber,
    *,
    device_session_id: int | None,
    settings: Settings,
    family_id: str | None = None,
) -> AuthTokens:
    access = create_access_token(
        str(subscriber.id),
        claims={
            "typ": "subscriber",
            "username": subscriber.username,
            "device_session_id": device_session_id,
        },
    )
    raw_refresh = generate_refresh_token()
    family = family_id or new_token_family_id()
    now = utcnow()
    row = SubscriberRefreshToken(
        subscriber_id=subscriber.id,
        device_session_id=device_session_id,
        token_hash=hash_refresh_token(raw_refresh),
        family_id=family,
        created_at=now,
        expires_at=now + timedelta(days=int(settings.refresh_token_expire_days)),
    )
    db.add(row)
    db.flush()
    return AuthTokens(
        access_token=access,
        refresh_token=raw_refresh,
        expires_in=int(settings.access_token_expire_minutes) * 60,
    )


def upsert_subscriber_from_identity(
    db: Session,
    *,
    username: str,
    identity,
    settings: Settings,
) -> Subscriber:
    provider_name = identity.source if identity.source in {PROVIDER_FIXTURE, PROVIDER_RADIUS} else identity.source
    external = identity.external_subject or username
    user = db.query(Subscriber).filter(Subscriber.username == username).one_or_none()
    if user is None:
        user = (
            db.query(Subscriber)
            .filter(
                Subscriber.identity_provider == provider_name,
                Subscriber.external_subject == external,
            )
            .one_or_none()
        )
    if user is None:
        user = Subscriber(
            username=username,
            hashed_password=None,
            name=identity.display_name or username,
            branch=identity.branch_code or "",
            package=identity.package_name or "",
            status=identity.account_status or "unknown",
            expiration="",
            radius_synced=provider_name == PROVIDER_RADIUS,
            identity_provider=provider_name,
            external_subject=external,
            max_devices=identity.max_devices or settings.subscriber_max_devices_default,
            service_status=identity.service_status or "unknown",
            valid_from=identity.valid_from,
            valid_until=identity.valid_until,
            last_activity=utcnow(),
        )
        db.add(user)
        db.flush()
    else:
        user.hashed_password = None  # never store provider passwords
        user.name = identity.display_name or user.name or username
        user.identity_provider = provider_name
        user.external_subject = external
        user.radius_synced = provider_name == PROVIDER_RADIUS
        user.last_activity = utcnow()
        db.add(user)
        db.flush()
    return user


def login_subscriber(
    db: Session,
    *,
    username: str,
    password: str,
    client_device_id: str | None = None,
    device_name: str = "",
    device_type: str = "desktop",
    browser: str = "",
    ip: str = "",
    user_agent: str | None = None,
    settings: Settings | None = None,
) -> LoginOutcome:
    cfg = settings or get_settings()
    provider = get_identity_provider(cfg)
    identity = provider.authenticate(username, password)
    if not identity.success:
        code = identity.denial_code or "invalid_credentials"
        if code == "provider_unavailable":
            return LoginOutcome(
                ok=False,
                http_status=503,
                code=code,
                detail=identity.safe_reason or "Identity provider unavailable",
            )
        return LoginOutcome(
            ok=False,
            http_status=401,
            code="invalid_credentials",
            detail=GENERIC_FAILURE,
        )

    user = upsert_subscriber_from_identity(db, username=username, identity=identity, settings=cfg)
    ent = entitlement_from_auth_result(
        account_status=identity.account_status,
        service_status=identity.service_status,
        package_name=identity.package_name,
        branch_code=identity.branch_code,
        valid_from=identity.valid_from,
        valid_until=identity.valid_until,
        max_devices=identity.max_devices,
        denial_code=identity.denial_code,
        safe_reason=identity.safe_reason,
        source=identity.source,
        settings=cfg,
    )
    apply_entitlement_to_subscriber(user, ent)
    persist_snapshot(db, user, ent, settings=cfg)
    db.add(user)
    db.flush()

    # Suspended / disabled / expired: still allow login so profile & entitlement APIs work,
    # except disabled accounts which are denied tokens.
    if ent.denial_code == "account_disabled":
        db.commit()
        return LoginOutcome(
            ok=False,
            http_status=403,
            code=ent.denial_code,
            detail=ent.safe_reason or "Account is disabled",
            subscriber=user,
        )

    device_session_id: int | None = None
    if client_device_id:
        try:
            device = register_or_touch_device(
                db,
                user,
                client_device_id=client_device_id,
                name=device_name,
                device_type=device_type,
                browser=browser,
                ip=ip,
                user_agent=user_agent,
                settings=cfg,
            )
            device_session_id = device.id
        except DeviceLimitExceeded:
            db.commit()
            return LoginOutcome(
                ok=False,
                http_status=403,
                code="device_limit_exceeded",
                detail="Device limit reached. Remove a device and try again.",
                subscriber=user,
            )
        except ValueError:
            db.commit()
            return LoginOutcome(
                ok=False,
                http_status=400,
                code="invalid_device",
                detail="Invalid device identifier",
                subscriber=user,
            )

    tokens = _issue_tokens(db, user, device_session_id=device_session_id, settings=cfg)
    db.commit()
    db.refresh(user)
    return LoginOutcome(ok=True, tokens=tokens, subscriber=user, http_status=200, code="ok", detail="ok")


def refresh_subscriber_tokens(
    db: Session,
    *,
    refresh_token: str,
    settings: Settings | None = None,
) -> LoginOutcome:
    cfg = settings or get_settings()
    digest = hash_refresh_token(refresh_token)
    row = (
        db.query(SubscriberRefreshToken)
        .filter(SubscriberRefreshToken.token_hash == digest)
        .one_or_none()
    )
    if row is None:
        return LoginOutcome(ok=False, http_status=401, code="invalid_token", detail="Invalid refresh token")

    now = utcnow()
    expires = row.expires_at
    if expires.tzinfo is None:
        from datetime import UTC

        expires = expires.replace(tzinfo=UTC)

    # Reuse detection: already revoked/rotated token presented again.
    if row.revoked_at is not None or row.replaced_by_id is not None:
        revoke_family(db, row.family_id)
        revoke_all_refresh_for_subscriber(db, row.subscriber_id)
        db.commit()
        return LoginOutcome(
            ok=False,
            http_status=401,
            code="refresh_reuse",
            detail="Refresh token reuse detected",
        )

    if expires <= now:
        row.revoked_at = now
        db.add(row)
        db.commit()
        return LoginOutcome(ok=False, http_status=401, code="token_expired", detail="Refresh token expired")

    user = db.get(Subscriber, row.subscriber_id)
    if user is None:
        return LoginOutcome(ok=False, http_status=401, code="invalid_token", detail="Invalid refresh token")

    tokens = _issue_tokens(
        db,
        user,
        device_session_id=row.device_session_id,
        settings=cfg,
        family_id=row.family_id,
    )
    # Mark old token rotated
    new_row = (
        db.query(SubscriberRefreshToken)
        .filter(SubscriberRefreshToken.token_hash == hash_refresh_token(tokens.refresh_token))
        .one()
    )
    row.revoked_at = now
    row.replaced_by_id = new_row.id
    db.add(row)
    db.commit()
    return LoginOutcome(ok=True, tokens=tokens, subscriber=user, http_status=200, code="ok", detail="ok")


def logout_subscriber(
    db: Session,
    *,
    subscriber: Subscriber,
    refresh_token: str | None = None,
) -> None:
    now = utcnow()
    if refresh_token:
        digest = hash_refresh_token(refresh_token)
        row = (
            db.query(SubscriberRefreshToken)
            .filter(
                SubscriberRefreshToken.token_hash == digest,
                SubscriberRefreshToken.subscriber_id == subscriber.id,
            )
            .one_or_none()
        )
        if row is not None and row.revoked_at is None:
            row.revoked_at = now
            db.add(row)
            revoke_family(db, row.family_id)
    else:
        revoke_all_refresh_for_subscriber(db, subscriber.id)
    db.commit()
