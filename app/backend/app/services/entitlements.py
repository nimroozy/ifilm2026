"""Narrow access-entitlement layer for subscriber playback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.subscriber_auth import SubscriberEntitlementSnapshot
from app.models.user import Subscriber
from app.services.identity import get_identity_provider
from app.services.identity.provider import EntitlementProviderResult

DENY_ACCOUNT_SUSPENDED = "account_suspended"
DENY_ACCOUNT_DISABLED = "account_disabled"
DENY_SERVICE_EXPIRED = "service_expired"
DENY_SERVICE_INACTIVE = "service_inactive"
DENY_ENTITLEMENT_MISSING = "entitlement_missing"
DENY_PROVIDER_UNAVAILABLE = "provider_unavailable"
DENY_CACHE_EXPIRED = "entitlement_cache_expired"
DENY_DEVICE_LIMIT = "device_limit_exceeded"


@dataclass(frozen=True)
class EntitlementResult:
    allowed: bool
    account_status: str = "unknown"
    service_status: str = "unknown"
    package_name: str = ""
    branch_code: str = ""
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    denial_code: str | None = None
    safe_reason: str | None = None
    max_devices: int = 3
    source: str = "unknown"
    checked_at: datetime | None = None
    from_cache: bool = False


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _now() -> datetime:
    return datetime.now(UTC)


def _evaluate_local(subscriber: Subscriber, *, source: str, checked_at: datetime) -> EntitlementResult:
    settings = get_settings()
    account = (subscriber.status or "unknown").lower()
    service = (subscriber.service_status or "unknown").lower()
    valid_until = _aware(subscriber.valid_until)
    now = _now()

    denial: str | None = None
    reason: str | None = None
    if account in {"suspended"}:
        denial = DENY_ACCOUNT_SUSPENDED
        reason = "Account is suspended"
    elif account in {"disabled", "inactive"}:
        denial = DENY_ACCOUNT_DISABLED
        reason = "Account is disabled"
    elif service in {"expired"} or (valid_until is not None and valid_until < now):
        denial = DENY_SERVICE_EXPIRED
        reason = "Service entitlement has expired"
        service = "expired"
    elif service not in {"active"}:
        denial = DENY_SERVICE_INACTIVE
        reason = "Service entitlement is not active"
    elif not subscriber.package:
        denial = DENY_ENTITLEMENT_MISSING
        reason = "Package entitlement is missing"

    return EntitlementResult(
        allowed=denial is None,
        account_status=account,
        service_status=service,
        package_name=subscriber.package or "",
        branch_code=subscriber.branch or "",
        valid_from=_aware(subscriber.valid_from),
        valid_until=valid_until,
        denial_code=denial,
        safe_reason=reason,
        max_devices=int(subscriber.max_devices or settings.subscriber_max_devices_default),
        source=source,
        checked_at=checked_at,
        from_cache=False,
    )


def _from_provider(
    provider: EntitlementProviderResult,
    *,
    defaults: Settings,
    checked_at: datetime,
) -> EntitlementResult:
    return EntitlementResult(
        allowed=bool(provider.allowed and provider.available),
        account_status=provider.account_status,
        service_status=provider.service_status,
        package_name=provider.package_name or "",
        branch_code=provider.branch_code or "",
        valid_from=_aware(provider.valid_from),
        valid_until=_aware(provider.valid_until),
        denial_code=provider.denial_code
        or (None if provider.allowed else DENY_ENTITLEMENT_MISSING),
        safe_reason=provider.safe_reason,
        max_devices=int(provider.max_devices or defaults.subscriber_max_devices_default),
        source=provider.source,
        checked_at=checked_at,
        from_cache=False,
    )


def _from_snapshot(row: SubscriberEntitlementSnapshot) -> EntitlementResult:
    return EntitlementResult(
        allowed=bool(row.allowed),
        account_status=row.account_status,
        service_status=row.service_status,
        package_name=row.package_name,
        branch_code=row.branch_code,
        valid_from=_aware(row.valid_from),
        valid_until=_aware(row.valid_until),
        denial_code=row.denial_code,
        safe_reason=row.safe_reason,
        max_devices=int(row.max_devices),
        source=row.source,
        checked_at=_aware(row.checked_at),
        from_cache=True,
    )


def _cache_still_valid(row: SubscriberEntitlementSnapshot, settings: Settings) -> bool:
    now = _now()
    expires = _aware(row.expires_at)
    if expires is None:
        # Fall back to checked_at + TTL
        checked = _aware(row.checked_at) or now
        expires = checked + timedelta(seconds=int(settings.entitlement_cache_ttl_seconds))
    grace = int(settings.entitlement_cache_grace_seconds)
    # Grace never extends past entitlement valid_until.
    valid_until = _aware(row.valid_until)
    limit = expires + timedelta(seconds=grace) if grace > 0 else expires
    if valid_until is not None and limit > valid_until:
        limit = valid_until
    if now > limit:
        return False
    if not row.allowed:
        return False
    if valid_until is not None and now > valid_until:
        return False
    return True


def persist_snapshot(
    db: Session,
    subscriber: Subscriber,
    result: EntitlementResult,
    *,
    settings: Settings | None = None,
) -> SubscriberEntitlementSnapshot:
    cfg = settings or get_settings()
    checked = result.checked_at or _now()
    expires = checked + timedelta(seconds=int(cfg.entitlement_cache_ttl_seconds))
    if result.valid_until is not None and expires > result.valid_until:
        expires = result.valid_until
    row = SubscriberEntitlementSnapshot(
        subscriber_id=subscriber.id,
        allowed=result.allowed,
        account_status=result.account_status,
        service_status=result.service_status,
        package_name=result.package_name,
        branch_code=result.branch_code,
        valid_from=result.valid_from,
        valid_until=result.valid_until,
        denial_code=result.denial_code,
        safe_reason=result.safe_reason,
        max_devices=result.max_devices,
        source=result.source,
        checked_at=checked,
        expires_at=expires,
    )
    db.add(row)
    db.flush()
    return row


def apply_entitlement_to_subscriber(subscriber: Subscriber, result: EntitlementResult) -> None:
    subscriber.status = result.account_status if result.account_status != "unknown" else subscriber.status
    subscriber.service_status = result.service_status
    if result.package_name:
        subscriber.package = result.package_name
    if result.branch_code:
        subscriber.branch = result.branch_code
    subscriber.valid_from = result.valid_from
    subscriber.valid_until = result.valid_until
    subscriber.max_devices = result.max_devices
    if result.valid_until:
        subscriber.expiration = result.valid_until.date().isoformat()
    db_add = subscriber  # noqa: F841 — caller commits


def check_entitlement(
    db: Session,
    subscriber: Subscriber,
    *,
    settings: Settings | None = None,
    refresh: bool = False,
) -> EntitlementResult:
    """Fail-closed entitlement check.

    Uses provider when available. On provider unavailability, uses a still-valid
    allowed cache only. Expired or missing cache denies playback.
    """
    cfg = settings or get_settings()
    checked_at = _now()

    if not refresh and subscriber.external_subject:
        latest = (
            db.query(SubscriberEntitlementSnapshot)
            .filter(SubscriberEntitlementSnapshot.subscriber_id == subscriber.id)
            .order_by(SubscriberEntitlementSnapshot.checked_at.desc())
            .first()
        )
        if latest is not None and _cache_still_valid(latest, cfg):
            return _from_snapshot(latest)

    provider = get_identity_provider(cfg)
    if subscriber.external_subject:
        provider_result = provider.get_entitlement(subscriber.external_subject)
        if provider_result.available:
            result = _from_provider(provider_result, defaults=cfg, checked_at=checked_at)
            apply_entitlement_to_subscriber(subscriber, result)
            persist_snapshot(db, subscriber, result, settings=cfg)
            db.add(subscriber)
            return result
        # Provider unavailable — try valid cache only
        latest = (
            db.query(SubscriberEntitlementSnapshot)
            .filter(SubscriberEntitlementSnapshot.subscriber_id == subscriber.id)
            .order_by(SubscriberEntitlementSnapshot.checked_at.desc())
            .first()
        )
        if latest is not None and _cache_still_valid(latest, cfg):
            cached = _from_snapshot(latest)
            return EntitlementResult(
                allowed=cached.allowed,
                account_status=cached.account_status,
                service_status=cached.service_status,
                package_name=cached.package_name,
                branch_code=cached.branch_code,
                valid_from=cached.valid_from,
                valid_until=cached.valid_until,
                denial_code=cached.denial_code,
                safe_reason=cached.safe_reason,
                max_devices=cached.max_devices,
                source=f"{cached.source}+cache",
                checked_at=cached.checked_at,
                from_cache=True,
            )
        return EntitlementResult(
            allowed=False,
            account_status=subscriber.status,
            service_status=subscriber.service_status,
            package_name=subscriber.package or "",
            branch_code=subscriber.branch or "",
            valid_from=_aware(subscriber.valid_from),
            valid_until=_aware(subscriber.valid_until),
            denial_code=DENY_PROVIDER_UNAVAILABLE
            if latest is None
            else DENY_CACHE_EXPIRED,
            safe_reason=(
                "Entitlement provider unavailable"
                if latest is None
                else "Cached entitlement expired; playback denied"
            ),
            max_devices=int(subscriber.max_devices or cfg.subscriber_max_devices_default),
            source="cache",
            checked_at=checked_at,
            from_cache=True,
        )

    # Local-only evaluation (no external subject) — do not invent allow.
    result = _evaluate_local(subscriber, source="local", checked_at=checked_at)
    persist_snapshot(db, subscriber, result, settings=cfg)
    return result


def entitlement_from_auth_result(
    *,
    account_status: str,
    service_status: str,
    package_name: str | None,
    branch_code: str | None,
    valid_from: datetime | None,
    valid_until: datetime | None,
    max_devices: int | None,
    denial_code: str | None,
    safe_reason: str | None,
    source: str,
    settings: Settings | None = None,
) -> EntitlementResult:
    cfg = settings or get_settings()
    checked_at = _now()
    # Re-evaluate expiry even if provider omitted denial.
    now = checked_at
    denial = denial_code
    reason = safe_reason
    service = service_status
    if denial is None:
        until = _aware(valid_until)
        if account_status == "suspended":
            denial = DENY_ACCOUNT_SUSPENDED
            reason = "Account is suspended"
        elif account_status in {"disabled", "inactive"}:
            denial = DENY_ACCOUNT_DISABLED
            reason = "Account is disabled"
        elif service_status == "expired" or (until is not None and until < now):
            denial = DENY_SERVICE_EXPIRED
            reason = "Service entitlement has expired"
            service = "expired"
        elif service_status != "active":
            denial = DENY_SERVICE_INACTIVE
            reason = "Service entitlement is not active"
        elif not package_name:
            denial = DENY_ENTITLEMENT_MISSING
            reason = "Package entitlement is missing"
    return EntitlementResult(
        allowed=denial is None,
        account_status=account_status,
        service_status=service,
        package_name=package_name or "",
        branch_code=branch_code or "",
        valid_from=_aware(valid_from),
        valid_until=_aware(valid_until),
        denial_code=denial,
        safe_reason=reason,
        max_devices=int(max_devices or cfg.subscriber_max_devices_default),
        source=source,
        checked_at=checked_at,
    )
