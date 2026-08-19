"""HTTP client for portal.mns.af Voice AI customer lookup (backend only)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.services.portal.runtime_config import PortalRuntimeConfig

logger = logging.getLogger(__name__)


class PortalClientError(Exception):
    """Safe, non-secret portal client failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PortalLookupResult:
    success: bool
    verified: bool
    customer: dict[str, Any] | None
    http_status: int
    portal_code: str | None = None


def lookup_customer(
    config: PortalRuntimeConfig,
    *,
    branch: str,
    username: str,
    password: str,
    http_client: httpx.Client | None = None,
) -> PortalLookupResult:
    """POST /customers/lookup. Never logs password or Authorization."""
    token = (config.token or "").strip()
    if not token:
        raise PortalClientError("provider_unavailable", "Portal credentials are not configured")

    url = f"{config.voice_ai_base}/customers/lookup"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Mobin-Client": (config.client or "ifilm").strip(),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    body = {
        "branch": branch,
        "username": username,
        "password": password,
        "request_source": (config.request_source or "ifilm").strip(),
    }

    timeout = httpx.Timeout(
        float(config.read_timeout_seconds),
        connect=float(config.connect_timeout_seconds),
    )
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout)
    try:
        response = client.post(url, headers=headers, json=body)
    except httpx.TimeoutException:
        logger.warning("portal_lookup_timeout branch=%s", branch)
        raise PortalClientError(
            "provider_unavailable",
            "Authentication service is temporarily unavailable. Please try again.",
        ) from None
    except httpx.HTTPError:
        logger.warning("portal_lookup_http_error branch=%s", branch)
        raise PortalClientError(
            "provider_unavailable",
            "Authentication service is temporarily unavailable. Please try again.",
        ) from None
    finally:
        if owns_client:
            client.close()

    status = int(response.status_code)
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    if not isinstance(payload, dict):
        payload = {}

    portal_code = payload.get("code")
    if isinstance(portal_code, str):
        portal_code = portal_code.strip() or None
    else:
        portal_code = None

    if status >= 500:
        logger.warning("portal_lookup_upstream_error status=%s code=%s", status, portal_code)
        raise PortalClientError(
            "provider_unavailable",
            "Authentication service is temporarily unavailable. Please try again.",
        )

    if status == 401 and portal_code == "unauthorized":
        # Misconfigured iFilm→portal service credential (not subscriber password).
        logger.error("portal_lookup_service_unauthorized")
        raise PortalClientError(
            "provider_unavailable",
            "Authentication service is temporarily unavailable. Please try again.",
        )

    success = bool(payload.get("success"))
    verified = bool(payload.get("verified"))
    customer = payload.get("customer")
    if not isinstance(customer, dict):
        customer = None

    logger.info(
        "portal_lookup_complete status=%s success=%s verified=%s branch=%s",
        status,
        success,
        verified,
        branch,
    )
    return PortalLookupResult(
        success=success,
        verified=verified,
        customer=customer,
        http_status=status,
        portal_code=portal_code,
    )


def probe_portal_connection(config: PortalRuntimeConfig, *, http_client: httpx.Client | None = None) -> dict[str, Any]:
    """Synthetic lookup probe — never uses a real subscriber password."""
    import uuid

    branch = "Kabul"
    probe_id = uuid.uuid4().hex[:16]
    username = f"ifilm-probe-{probe_id}"
    password = f"probe-{probe_id}"
    token = (config.token or "").strip()
    if not token:
        return {
            "ok": False,
            "portal_reachable": False,
            "credential_accepted": False,
            "http_status": None,
            "message": "Portal service token is not configured.",
        }

    url = f"{config.voice_ai_base}/customers/lookup"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Mobin-Client": (config.client or "ifilm").strip(),
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    body = {
        "branch": branch,
        "username": username,
        "password": password,
        "request_source": (config.request_source or "ifilm").strip(),
    }
    timeout = httpx.Timeout(
        float(config.read_timeout_seconds),
        connect=float(config.connect_timeout_seconds),
    )
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout)
    try:
        response = client.post(url, headers=headers, json=body)
    except httpx.TimeoutException:
        logger.warning("portal_probe_timeout")
        return {
            "ok": False,
            "portal_reachable": False,
            "credential_accepted": False,
            "http_status": None,
            "message": "Portal connection timed out.",
        }
    except httpx.HTTPError:
        logger.warning("portal_probe_http_error")
        return {
            "ok": False,
            "portal_reachable": False,
            "credential_accepted": False,
            "http_status": None,
            "message": "Portal connection failed.",
        }
    finally:
        if owns_client:
            client.close()

    status = int(response.status_code)
    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    portal_code = payload.get("code")
    if isinstance(portal_code, str):
        portal_code = portal_code.strip() or None
    else:
        portal_code = None

    if status >= 500:
        return {
            "ok": False,
            "portal_reachable": False,
            "credential_accepted": False,
            "http_status": status,
            "message": "Portal service unavailable.",
        }

    if status == 401 and portal_code == "unauthorized":
        return {
            "ok": False,
            "portal_reachable": True,
            "credential_accepted": False,
            "http_status": status,
            "message": "Portal rejected the service token.",
        }

    credential_accepted = status in {200, 400, 422} or (
        status == 200 and (not payload.get("verified") or portal_code == "verification_failed")
    )
    if status == 200:
        credential_accepted = portal_code != "unauthorized"
        ok = credential_accepted
        return {
            "ok": ok,
            "portal_reachable": True,
            "credential_accepted": credential_accepted,
            "http_status": status,
            "message": "Portal connection successful." if ok else "Portal rejected the service token.",
        }

    if status in {400, 422}:
        return {
            "ok": True,
            "portal_reachable": True,
            "credential_accepted": True,
            "http_status": status,
            "message": "Portal accepted the service token.",
        }

    return {
        "ok": False,
        "portal_reachable": True,
        "credential_accepted": False,
        "http_status": status,
        "message": "Unexpected Portal response.",
    }
