"""Service locations for A1 (backend single source of truth).

A1 v1: owner-approved temporary production registry while portal
``GET /api/voice-ai/v1/service-locations`` is LIVE_QA 404.

Keep this module as the only list. Frontend must fetch
``GET /api/auth/isp/locations`` (no duplicated production list).
A1.1 / tech debt: replace with a dynamic portal JSON provider without UI changes.

S2S / login accept canonical **name** or **code**. Numeric HTML ids are not
valid Voice AI ``branch`` values.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceLocation:
    id: str
    name: str
    code: str
    active: bool = True


# Order matches common portal UX (alpha by name is also fine; keep stable).
PORTAL_SERVICE_LOCATIONS: tuple[ServiceLocation, ...] = (
    ServiceLocation(id="1", name="Kabul", code="KBL"),
    ServiceLocation(id="3", name="Kandahar", code="KDR"),
    ServiceLocation(id="4", name="Ghazni", code="GHZ"),
    ServiceLocation(id="2", name="Nimruz", code="NMZ"),
    ServiceLocation(id="6", name="Buldak", code="BLD"),
    ServiceLocation(id="5", name="Helmand", code="HLD"),
)

_BY_NAME = {loc.name.casefold(): loc for loc in PORTAL_SERVICE_LOCATIONS}
_BY_CODE = {loc.code.upper(): loc for loc in PORTAL_SERVICE_LOCATIONS}


def list_active_locations() -> list[ServiceLocation]:
    return [loc for loc in PORTAL_SERVICE_LOCATIONS if loc.active]


def resolve_location(branch: str | None) -> ServiceLocation | None:
    """Resolve a portal branch name or code (not numeric HTML id)."""
    if branch is None:
        return None
    text = str(branch).strip()
    if not text or text.isdigit():
        return None
    by_code = _BY_CODE.get(text.upper())
    if by_code is not None:
        return by_code
    return _BY_NAME.get(text.casefold())


def canonical_branch_name(branch: str | None) -> str | None:
    loc = resolve_location(branch)
    return loc.name if loc else None


def branch_code(branch: str | None) -> str | None:
    loc = resolve_location(branch)
    return loc.code if loc else None


def external_subject_for(*, branch: str, customer_number: str) -> str | None:
    """A1 v1 subject: ``{BRANCH_CODE}:{customer_number}`` (branch-scoped)."""
    code = branch_code(branch)
    number = (customer_number or "").strip()
    if not code or not number:
        return None
    return f"{code}:{number}"
