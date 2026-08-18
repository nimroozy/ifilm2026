"""ISP / portal.mns.af subscriber login (A1)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.deps import DbSession
from app.schemas.auth import SubscriberTokenResponse
from app.services.portal import list_active_locations
from app.services.portal.auth_decision import MSG_INVALID, MSG_UNAVAILABLE
from app.services.rate_limit import login_rate_limiter
from app.services.subscriber_auth import login_portal_subscriber

router = APIRouter(prefix="/auth/isp", tags=["auth-isp"])


class IspLocationOut(BaseModel):
    id: str
    name: str
    code: str
    active: bool = True


class IspLocationsResponse(BaseModel):
    locations: list[IspLocationOut]


class IspLoginRequest(BaseModel):
    branch: str = Field(min_length=1, max_length=100)
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)
    remember_device: bool = False
    device_id: str | None = Field(default=None, max_length=64)
    device_name: str = ""
    device_type: str = "desktop"
    browser: str = ""


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return (request.client.host or "")[:64]
    return ""


@router.get("/locations", response_model=IspLocationsResponse)
def isp_locations():
    settings = get_settings()
    if not settings.portal_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "provider_unavailable", "message": MSG_UNAVAILABLE},
        )
    return IspLocationsResponse(
        locations=[
            IspLocationOut(id=loc.id, name=loc.name, code=loc.code, active=loc.active)
            for loc in list_active_locations()
        ]
    )


@router.post("/login", response_model=SubscriberTokenResponse)
def isp_login(payload: IspLoginRequest, db: DbSession, request: Request):
    settings = get_settings()
    if not settings.portal_auth_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": "provider_unavailable", "message": MSG_UNAVAILABLE},
        )

    ip = _client_ip(request)
    branch_key = payload.branch.strip().casefold()
    user_key = payload.username.strip().casefold()
    rate_keys = (
        f"isp:ip:{ip}",
        f"isp:branch-user:{branch_key}:{user_key}:{ip}",
    )
    for key in rate_keys:
        if not login_rate_limiter.allow(
            key,
            limit=int(settings.portal_login_rate_limit),
            window_seconds=int(settings.portal_login_rate_window_seconds),
        ):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "code": "rate_limited",
                    "message": "Too many login attempts. Try again later.",
                },
            )

    outcome = login_portal_subscriber(
        db,
        branch=payload.branch,
        username=payload.username,
        password=payload.password,
        client_device_id=payload.device_id,
        device_name=payload.device_name,
        device_type=payload.device_type,
        browser=payload.browser,
        ip=ip,
        user_agent=request.headers.get("user-agent"),
        settings=settings,
    )
    if not outcome.ok or outcome.tokens is None:
        if outcome.http_status in {403, 429, 503}:
            raise HTTPException(
                status_code=outcome.http_status,
                detail={"code": outcome.code, "message": outcome.detail},
            )
        raise HTTPException(
            status_code=outcome.http_status or 401,
            detail={"code": outcome.code or "invalid_credentials", "message": outcome.detail or MSG_INVALID},
        )

    return SubscriberTokenResponse(
        access_token=outcome.tokens.access_token,
        refresh_token=outcome.tokens.refresh_token,
        expires_in=outcome.tokens.expires_in,
    )
