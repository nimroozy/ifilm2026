"""Map portal lookup results to iFilm identity + entitlement (A1 v1)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime

from app.services.entitlements import EntitlementResult
from app.services.identity.provider import IdentityAuthResult
from app.services.portal import PROVIDER_PORTAL, external_subject_for, resolve_location

MSG_INVALID = "Unable to sign in with the provided Internet account."
MSG_INACTIVE = "Your Internet service is not currently active."
MSG_UNAVAILABLE = "Authentication service is temporarily unavailable. Please try again."

# LIVE_QA observed account_status: active, expired. Unknown → fail closed.
# Do not invent extra enum semantics beyond safe deny.
_DENY_STATUSES = {
    "expired": ("service_expired", MSG_INACTIVE),
}


@dataclass(frozen=True)
class PortalAuthDecision:
    identity: IdentityAuthResult
    entitlement: EntitlementResult
    http_status: int
    code: str
    detail: str
    display_expiry: datetime | None = None


def _parse_expiry(value: object) -> datetime | None:
    if value is None:
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


def _package_name(customer: dict) -> str | None:
    pkg = customer.get("current_package")
    if isinstance(pkg, dict):
        name = str(pkg.get("name") or "").strip()
        return name or None
    if isinstance(pkg, str):
        return pkg.strip() or None
    return None


def _customer_number(customer: dict) -> str | None:
    raw = customer.get("customer_number")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _invalid(*, checked_at: datetime) -> PortalAuthDecision:
    identity = IdentityAuthResult(
        success=False,
        denial_code="invalid_credentials",
        safe_reason=MSG_INVALID,
        source=PROVIDER_PORTAL,
    )
    ent = EntitlementResult(
        allowed=False,
        account_status="unknown",
        service_status="unknown",
        denial_code="invalid_credentials",
        safe_reason=MSG_INVALID,
        source=PROVIDER_PORTAL,
        checked_at=checked_at,
    )
    return PortalAuthDecision(
        identity=identity,
        entitlement=ent,
        http_status=401,
        code="invalid_credentials",
        detail=MSG_INVALID,
    )


def decide_from_lookup(
    *,
    branch: str,
    username: str,
    success: bool,
    verified: bool,
    customer: dict | None,
    http_status: int,
) -> PortalAuthDecision:
    """A1 v1: allow iff success && verified && account_status==active.

    Identity requires customer.customer_number (no username fallback).
    internet_status is session state and does not gate access.
    expiry_date is display/snapshot metadata only (no independent gate).
    """
    checked_at = datetime.now(UTC)
    loc = resolve_location(branch)
    branch_name = loc.name if loc else branch
    _ = username

    if http_status in {400, 422} or not success or not verified or not customer:
        return _invalid(checked_at=checked_at)

    number = _customer_number(customer)
    if number is None:
        # Successful/verified payload without stable identity — fail closed.
        identity = IdentityAuthResult(
            success=False,
            denial_code="entitlement_unverified",
            safe_reason=MSG_UNAVAILABLE,
            source=PROVIDER_PORTAL,
        )
        ent = EntitlementResult(
            allowed=False,
            account_status="unknown",
            service_status="unknown",
            denial_code="entitlement_unverified",
            safe_reason=MSG_UNAVAILABLE,
            source=PROVIDER_PORTAL,
            checked_at=checked_at,
        )
        return PortalAuthDecision(
            identity=identity,
            entitlement=ent,
            http_status=503,
            code="provider_unavailable",
            detail=MSG_UNAVAILABLE,
        )

    account_status = str(customer.get("account_status") or "unknown").strip().lower() or "unknown"
    internet_status = str(customer.get("internet_status") or "unknown").strip().lower() or "unknown"
    display_name = str(customer.get("display_name") or "").strip() or number
    package = _package_name(customer)
    expiry = _parse_expiry(customer.get("expiry_date"))
    cust_branch = str(customer.get("branch") or branch_name).strip() or branch_name
    resolved = resolve_location(cust_branch) or loc
    final_branch = resolved.name if resolved else cust_branch
    subject = external_subject_for(branch=final_branch, customer_number=number)
    if subject is None:
        return PortalAuthDecision(
            identity=IdentityAuthResult(
                success=False,
                denial_code="entitlement_unverified",
                safe_reason=MSG_UNAVAILABLE,
                source=PROVIDER_PORTAL,
            ),
            entitlement=EntitlementResult(
                allowed=False,
                account_status="unknown",
                service_status="unknown",
                denial_code="entitlement_unverified",
                safe_reason=MSG_UNAVAILABLE,
                source=PROVIDER_PORTAL,
                checked_at=checked_at,
            ),
            http_status=503,
            code="provider_unavailable",
            detail=MSG_UNAVAILABLE,
        )

    if account_status != "active":
        denial, detail = _DENY_STATUSES.get(
            account_status,
            ("entitlement_unverified", MSG_INACTIVE),
        )
        identity = IdentityAuthResult(
            success=False,
            external_subject=subject,
            display_name=display_name,
            account_status=account_status,
            service_status=internet_status,
            package_name=package,
            branch_code=final_branch,
            valid_until=expiry,
            denial_code=denial,
            safe_reason=detail,
            source=PROVIDER_PORTAL,
        )
        ent = EntitlementResult(
            allowed=False,
            account_status=account_status,
            service_status="inactive",
            package_name=package or "",
            branch_code=final_branch,
            valid_until=None,
            denial_code=denial,
            safe_reason=detail,
            source=PROVIDER_PORTAL,
            checked_at=checked_at,
        )
        return PortalAuthDecision(
            identity=identity,
            entitlement=ent,
            http_status=403,
            code=denial,
            detail=detail,
            display_expiry=expiry,
        )

    identity = IdentityAuthResult(
        success=True,
        external_subject=subject,
        display_name=display_name,
        account_status="active",
        service_status="active",
        package_name=package,
        branch_code=final_branch,
        valid_until=None,
        source=PROVIDER_PORTAL,
    )
    ent = EntitlementResult(
        allowed=True,
        account_status="active",
        service_status="active",
        package_name=package or "",
        branch_code=final_branch,
        valid_until=None,
        source=PROVIDER_PORTAL,
        checked_at=checked_at,
    )
    return PortalAuthDecision(
        identity=identity,
        entitlement=ent,
        http_status=200,
        code="ok",
        detail="ok",
        display_expiry=expiry,
    )
