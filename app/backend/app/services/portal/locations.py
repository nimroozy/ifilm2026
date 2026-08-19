"""Service locations for A1 (backend abstraction).

TEMPORARY FALLBACK / test fixture only — not the final production authority.
Production A1 still requires a dynamic portal JSON source (preferably
``GET /api/voice-ai/v1/service-locations``). Keep this module as the single
backend entry point so a dynamic provider can replace the static list without
UI or frontend list duplication.
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
_BY_ID = {loc.id: loc for loc in PORTAL_SERVICE_LOCATIONS}


def list_active_locations() -> list[ServiceLocation]:
    return [loc for loc in PORTAL_SERVICE_LOCATIONS if loc.active]


def resolve_location(branch: str | None) -> ServiceLocation | None:
    """Resolve a portal branch name, code, or id to a canonical location."""
    if branch is None:
        return None
    text = str(branch).strip()
    if not text:
        return None
    by_id = _BY_ID.get(text)
    if by_id is not None:
        return by_id
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


def external_subject_for(*, branch: str, username: str) -> str | None:
    """PROVISIONAL subject: ``{CODE}:{normalized_username}``.

    Not the final stable identity until live portal QA confirms username vs
    ``customer_number`` semantics (prefer ``customer_number`` forms when proven).
    """
    code = branch_code(branch)
    user = (username or "").strip()
    if not code or not user:
        return None
    return f"{code}:{user}"
