"""Authoritative subscriber identity provider boundary.

Modes:
- fixture: development/test only (RADIUS_MOCK_USERS)
- radius: live SAS/FreeRADIUS adapter (fail-closed; live SAS unverified)
- disabled: all authentication denied

Never expose raw Radius responses or credentials to clients.
Never log passwords or Radius secrets.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol

from app.core.config import Settings, get_settings
from app.core.runtime import RuntimeConfigurationError, is_dev_like

logger = logging.getLogger(__name__)

GENERIC_FAILURE = "Invalid credentials"
PROVIDER_UNAVAILABLE = "provider_unavailable"
ACCOUNT_SUSPENDED = "account_suspended"
ACCOUNT_DISABLED = "account_disabled"
SERVICE_EXPIRED = "service_expired"
SERVICE_INACTIVE = "service_inactive"

PROVIDER_FIXTURE = "fixture"
PROVIDER_RADIUS = "radius"
PROVIDER_DISABLED = "disabled"
PROVIDER_LOCAL = "local"


@dataclass(frozen=True)
class IdentityAuthResult:
    success: bool
    external_subject: str | None = None
    display_name: str | None = None
    account_status: str = "unknown"
    service_status: str = "unknown"
    package_name: str | None = None
    branch_code: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_devices: int | None = None
    denial_code: str | None = None
    safe_reason: str | None = None
    source: str = "unknown"

    @property
    def message(self) -> str:
        """Legacy RadiusService compatibility."""
        return self.safe_reason or (GENERIC_FAILURE if not self.success else "ok")


@dataclass(frozen=True)
class AccountStatusResult:
    account_status: str
    service_status: str
    denial_code: str | None = None
    safe_reason: str | None = None
    source: str = "unknown"
    available: bool = True


@dataclass(frozen=True)
class EntitlementProviderResult:
    allowed: bool
    account_status: str = "unknown"
    service_status: str = "unknown"
    package_name: str | None = None
    branch_code: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    max_devices: int | None = None
    denial_code: str | None = None
    safe_reason: str | None = None
    source: str = "unknown"
    available: bool = True


class SubscriberIdentityProvider(Protocol):
    def authenticate(self, username: str, password: str) -> IdentityAuthResult: ...

    def get_account_status(self, external_subject: str) -> AccountStatusResult: ...

    def get_entitlement(self, external_subject: str) -> EntitlementProviderResult: ...


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if "T" in text:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt
        d = date.fromisoformat(text)
        return datetime(d.year, d.month, d.day, tzinfo=UTC)
    except ValueError:
        return None


def _fixture_row(settings: Settings, username: str) -> dict | None:
    for user in settings.radius_mock_users:
        if user.get("username") == username:
            return user
    return None


def _statuses_from_fixture(row: dict) -> tuple[str, str, str | None, str | None, datetime | None]:
    account_status = str(row.get("account_status") or row.get("status") or "active").lower()
    service_status = str(row.get("service_status") or "active").lower()
    raw_exp = row.get("expiration") if "expiration" in row else row.get("valid_until")
    # Distinguish missing expiry from present-but-malformed.
    expiry_provided = raw_exp is not None and str(raw_exp).strip() != ""
    valid_until = _parse_date(str(raw_exp) if expiry_provided else None)
    package = str(row.get("package") or "").strip()
    now = datetime.now(UTC)
    denial: str | None = None
    reason: str | None = None
    if account_status in {"suspended"}:
        denial = ACCOUNT_SUSPENDED
        reason = "Account is suspended"
    elif account_status in {"disabled", "inactive"}:
        denial = ACCOUNT_DISABLED
        reason = "Account is disabled"
        account_status = "disabled"
    elif expiry_provided and valid_until is None:
        denial = "malformed_expiry"
        reason = "Service expiry attribute is malformed"
        service_status = "unknown"
    elif service_status in {"expired"} or (valid_until is not None and valid_until < now):
        denial = SERVICE_EXPIRED
        reason = "Service entitlement has expired"
        service_status = "expired"
    elif service_status not in {"active"}:
        denial = SERVICE_INACTIVE
        reason = "Service is not active"
    elif package.lower() in {"", "unknown", "none", "n/a"}:
        denial = "unknown_package"
        reason = "Package entitlement is missing or unknown"
    return account_status, service_status, denial, reason, valid_until


def _reply_attr(reply: object, name: str) -> str | None:
    """Safely read a single Radius reply attribute without exposing raw packets."""
    if not name:
        return None
    try:
        values = reply[name]  # type: ignore[index]
    except Exception:
        return None
    if not values:
        return None
    first = values[0]
    if isinstance(first, bytes):
        try:
            return first.decode("utf-8", errors="replace").strip() or None
        except Exception:
            return None
    text = str(first).strip()
    return text or None


def _entitlement_from_radius_attrs(
    settings: Settings, reply: object | None
) -> tuple[str, str, str | None, str | None, datetime | None, int | None, str | None, str | None]:
    """Map Radius attributes to entitlement fields. Fail closed on gaps.

    Returns:
      account_status, service_status, package, branch, valid_until, max_devices, denial, reason
    """
    if not settings.radius_entitlement_mapping_enabled:
        return (
            "unknown",
            "unknown",
            None,
            None,
            None,
            None,
            "entitlement_unverified",
            "Live Radius entitlement mapping is disabled; Access-Accept alone never grants playback",
        )
    if reply is None:
        return (
            "unknown",
            "unknown",
            None,
            None,
            None,
            None,
            "entitlement_missing",
            "Required Radius entitlement attributes are missing",
        )

    package = _reply_attr(reply, settings.radius_attr_package)
    branch = _reply_attr(reply, settings.radius_attr_branch) if settings.radius_attr_branch else None
    raw_exp = _reply_attr(reply, settings.radius_attr_expiration)
    account_status = (
        (_reply_attr(reply, settings.radius_attr_account_status) or "active").lower()
        if settings.radius_attr_account_status
        else "active"
    )
    service_status = (
        (_reply_attr(reply, settings.radius_attr_service_status) or "active").lower()
        if settings.radius_attr_service_status
        else "active"
    )
    max_devices = None
    if settings.radius_attr_max_devices:
        raw_max = _reply_attr(reply, settings.radius_attr_max_devices)
        if raw_max:
            try:
                max_devices = int(raw_max)
            except ValueError:
                return (
                    account_status,
                    "unknown",
                    package,
                    branch,
                    None,
                    None,
                    "entitlement_missing",
                    "Radius max-devices attribute is malformed",
                )

    if not package or package.lower() in {"unknown", "none", "n/a"}:
        return (
            account_status,
            service_status,
            package,
            branch,
            None,
            max_devices,
            "unknown_package",
            "Package entitlement is missing or unknown",
        )
    if raw_exp is None:
        return (
            account_status,
            service_status,
            package,
            branch,
            None,
            max_devices,
            "entitlement_missing",
            "Required Radius expiry attribute is missing",
        )
    valid_until = _parse_date(raw_exp)
    if valid_until is None:
        return (
            account_status,
            service_status,
            package,
            branch,
            None,
            max_devices,
            "malformed_expiry",
            "Service expiry attribute is malformed",
        )
    now = datetime.now(UTC)
    if account_status in {"suspended"}:
        return account_status, service_status, package, branch, valid_until, max_devices, ACCOUNT_SUSPENDED, "Account is suspended"
    if account_status in {"disabled", "inactive"}:
        return "disabled", service_status, package, branch, valid_until, max_devices, ACCOUNT_DISABLED, "Account is disabled"
    if service_status == "expired" or valid_until < now:
        return account_status, "expired", package, branch, valid_until, max_devices, SERVICE_EXPIRED, "Service entitlement has expired"
    if service_status != "active":
        return account_status, service_status, package, branch, valid_until, max_devices, SERVICE_INACTIVE, "Service is not active"
    return account_status, service_status, package, branch, valid_until, max_devices, None, None


class FixtureIdentityProvider:
    """Development/test fixture provider. Rejected outside APP_ENV development/test."""

    def __init__(self, settings: Settings) -> None:
        if not is_dev_like(settings.app_env):
            raise RuntimeConfigurationError(
                "Fixture subscriber identity is not allowed outside development/test"
            )
        self.settings = settings

    def authenticate(self, username: str, password: str) -> IdentityAuthResult:
        row = _fixture_row(self.settings, username)
        if row is None or row.get("password") != password:
            return IdentityAuthResult(
                success=False,
                denial_code="invalid_credentials",
                safe_reason=GENERIC_FAILURE,
                source=PROVIDER_FIXTURE,
            )
        account_status, service_status, denial, reason, valid_until = _statuses_from_fixture(row)
        max_devices = row.get("max_devices")
        try:
            max_devices_i = int(max_devices) if max_devices is not None else None
        except (TypeError, ValueError):
            max_devices_i = None
        return IdentityAuthResult(
            success=True,
            external_subject=str(row.get("external_subject") or username),
            display_name=str(row.get("name") or username),
            account_status=account_status,
            service_status=service_status,
            package_name=str(row.get("package") or "Standard"),
            branch_code=str(row.get("branch") or "Kabul"),
            valid_from=_parse_date(row.get("valid_from")),
            valid_until=valid_until,
            max_devices=max_devices_i,
            denial_code=denial,
            safe_reason=reason,
            source=PROVIDER_FIXTURE,
        )

    def get_account_status(self, external_subject: str) -> AccountStatusResult:
        row = _fixture_row(self.settings, external_subject)
        if row is None:
            # Try match by external_subject field
            for user in self.settings.radius_mock_users:
                if str(user.get("external_subject") or user.get("username")) == external_subject:
                    row = user
                    break
        if row is None:
            return AccountStatusResult(
                account_status="unknown",
                service_status="unknown",
                denial_code="entitlement_missing",
                safe_reason="Account not found at provider",
                source=PROVIDER_FIXTURE,
                available=True,
            )
        account_status, service_status, denial, reason, _ = _statuses_from_fixture(row)
        return AccountStatusResult(
            account_status=account_status,
            service_status=service_status,
            denial_code=denial,
            safe_reason=reason,
            source=PROVIDER_FIXTURE,
            available=True,
        )

    def get_entitlement(self, external_subject: str) -> EntitlementProviderResult:
        row = _fixture_row(self.settings, external_subject)
        if row is None:
            for user in self.settings.radius_mock_users:
                if str(user.get("external_subject") or user.get("username")) == external_subject:
                    row = user
                    break
        if row is None:
            return EntitlementProviderResult(
                allowed=False,
                denial_code="entitlement_missing",
                safe_reason="Entitlement not found",
                source=PROVIDER_FIXTURE,
            )
        account_status, service_status, denial, reason, valid_until = _statuses_from_fixture(row)
        allowed = denial is None
        max_devices = row.get("max_devices")
        try:
            max_devices_i = int(max_devices) if max_devices is not None else None
        except (TypeError, ValueError):
            max_devices_i = None
        return EntitlementProviderResult(
            allowed=allowed,
            account_status=account_status,
            service_status=service_status,
            package_name=str(row.get("package") or "Standard"),
            branch_code=str(row.get("branch") or "Kabul"),
            valid_from=_parse_date(row.get("valid_from")),
            valid_until=valid_until,
            max_devices=max_devices_i,
            denial_code=denial,
            safe_reason=reason,
            source=PROVIDER_FIXTURE,
            available=True,
        )


class RadiusIdentityProvider:
    """Live Radius adapter. Fail-closed. Live SAS Radius is unverified."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def authenticate(self, username: str, password: str) -> IdentityAuthResult:
        if not self.settings.radius_enabled:
            return IdentityAuthResult(
                success=False,
                denial_code=PROVIDER_UNAVAILABLE,
                safe_reason="Identity provider unavailable",
                source=PROVIDER_RADIUS,
            )
        try:
            from pyrad import packet
            from pyrad.client import Client
            from pyrad.dictionary import Dictionary
        except Exception:
            logger.exception("Radius client library unavailable")
            return IdentityAuthResult(
                success=False,
                denial_code=PROVIDER_UNAVAILABLE,
                safe_reason="Identity provider unavailable",
                source=PROVIDER_RADIUS,
            )

        try:
            client = Client(
                server=self.settings.radius_server,
                authport=self.settings.radius_port,
                secret=self.settings.radius_secret.encode("utf-8"),
                dict=Dictionary(),
            )
            client.timeout = self.settings.radius_timeout_seconds
            # Bounded single attempt — no silent retry storms.
            req = client.CreateAuthPacket(code=packet.AccessRequest, User_Name=username)
            req["User-Password"] = req.PwCrypt(password)
            req["NAS-Identifier"] = self.settings.radius_nas_identifier
            reply = client.SendPacket(req)
            if reply.code != packet.AccessAccept:
                return IdentityAuthResult(
                    success=False,
                    denial_code="invalid_credentials",
                    safe_reason=GENERIC_FAILURE,
                    source=PROVIDER_RADIUS,
                )
            # Access-Accept establishes identity only. Entitlement requires separately
            # validated attribute mapping (disabled by default; live SAS unverified).
            (
                account_status,
                service_status,
                package_name,
                branch_code,
                valid_until,
                max_devices,
                denial,
                reason,
            ) = _entitlement_from_radius_attrs(self.settings, reply)
            return IdentityAuthResult(
                success=True,
                external_subject=username,
                display_name=username,
                account_status=account_status,
                service_status=service_status,
                package_name=package_name,
                branch_code=branch_code,
                valid_from=None,
                valid_until=valid_until,
                max_devices=max_devices,
                denial_code=denial,
                safe_reason=reason
                or (
                    None
                    if denial is None
                    else "Live Radius accepted identity; entitlement not confirmed"
                ),
                source=PROVIDER_RADIUS,
            )
        except TimeoutError:
            logger.warning("Radius authentication timed out")
            return IdentityAuthResult(
                success=False,
                denial_code=PROVIDER_UNAVAILABLE,
                safe_reason="Identity provider unavailable",
                source=PROVIDER_RADIUS,
            )
        except Exception:
            logger.exception("Radius authentication failed")
            return IdentityAuthResult(
                success=False,
                denial_code=PROVIDER_UNAVAILABLE,
                safe_reason="Identity provider unavailable",
                source=PROVIDER_RADIUS,
            )

    def get_account_status(self, external_subject: str) -> AccountStatusResult:
        # Live SAS account-status query is unverified — fail closed.
        _ = external_subject
        return AccountStatusResult(
            account_status="unknown",
            service_status="unknown",
            denial_code=PROVIDER_UNAVAILABLE,
            safe_reason="Live Radius account status is unverified",
            source=PROVIDER_RADIUS,
            available=False,
        )

    def get_entitlement(self, external_subject: str) -> EntitlementProviderResult:
        _ = external_subject
        # Live SAS has no verified out-of-band entitlement query. Without a still-valid
        # local snapshot, callers must fail closed. Mapping-disabled always denies.
        if not self.settings.radius_entitlement_mapping_enabled:
            return EntitlementProviderResult(
                allowed=False,
                denial_code="entitlement_unverified",
                safe_reason=(
                    "Live Radius entitlement mapping is disabled; "
                    "Access-Accept alone never grants playback"
                ),
                source=PROVIDER_RADIUS,
                available=False,
            )
        return EntitlementProviderResult(
            allowed=False,
            denial_code=PROVIDER_UNAVAILABLE,
            safe_reason=(
                "Live Radius entitlement re-check is unverified; "
                "use a still-valid cached entitlement or deny playback"
            ),
            source=PROVIDER_RADIUS,
            available=False,
        )


class DisabledIdentityProvider:
    def authenticate(self, username: str, password: str) -> IdentityAuthResult:
        _ = username, password
        return IdentityAuthResult(
            success=False,
            denial_code=PROVIDER_UNAVAILABLE,
            safe_reason="Subscriber authentication is disabled",
            source=PROVIDER_DISABLED,
        )

    def get_account_status(self, external_subject: str) -> AccountStatusResult:
        _ = external_subject
        return AccountStatusResult(
            account_status="unknown",
            service_status="unknown",
            denial_code=PROVIDER_UNAVAILABLE,
            safe_reason="Subscriber authentication is disabled",
            source=PROVIDER_DISABLED,
            available=False,
        )

    def get_entitlement(self, external_subject: str) -> EntitlementProviderResult:
        _ = external_subject
        return EntitlementProviderResult(
            allowed=False,
            denial_code=PROVIDER_UNAVAILABLE,
            safe_reason="Subscriber authentication is disabled",
            source=PROVIDER_DISABLED,
            available=False,
        )


def get_identity_provider(settings: Settings | None = None) -> SubscriberIdentityProvider:
    cfg = settings or get_settings()
    mode = cfg.subscriber_identity_mode
    if mode == PROVIDER_FIXTURE:
        return FixtureIdentityProvider(cfg)
    if mode == PROVIDER_RADIUS:
        return RadiusIdentityProvider(cfg)
    return DisabledIdentityProvider()
