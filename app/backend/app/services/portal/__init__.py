"""Portal.mns.af Voice AI identity helpers (A1)."""

from __future__ import annotations

from app.services.portal.client import PortalClientError, PortalLookupResult, lookup_customer
from app.services.portal.locations import (
    PORTAL_SERVICE_LOCATIONS,
    ServiceLocation,
    branch_code,
    canonical_branch_name,
    external_subject_for,
    list_active_locations,
    resolve_location,
)

PROVIDER_PORTAL = "portal_mns"

__all__ = [
    "PROVIDER_PORTAL",
    "PORTAL_SERVICE_LOCATIONS",
    "PortalClientError",
    "PortalLookupResult",
    "ServiceLocation",
    "branch_code",
    "canonical_branch_name",
    "external_subject_for",
    "list_active_locations",
    "lookup_customer",
    "resolve_location",
]
