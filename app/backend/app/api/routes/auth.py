from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import get_settings
from app.core.deps import CurrentSubscriber, DbSession
from app.core.features import require_feature
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    SubscriberOut,
    SubscriberTokenResponse,
)
from app.schemas.common import Message
from app.services.identity import GENERIC_FAILURE
from app.services.rate_limit import login_rate_limiter
from app.services.subscriber_auth import (
    login_subscriber,
    logout_subscriber,
    refresh_subscriber_tokens,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return (request.client.host or "")[:64]
    return ""


def _subscriber_out(user) -> SubscriberOut:
    def _iso(dt: datetime | None) -> str | None:
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.isoformat()

    return SubscriberOut(
        id=user.id,
        username=user.username,
        name=user.name,
        branch=user.branch,
        status=user.status,
        package=user.package,
        expiration=user.expiration,
        service_status=getattr(user, "service_status", "unknown") or "unknown",
        max_devices=int(getattr(user, "max_devices", 3) or 3),
        identity_provider=getattr(user, "identity_provider", "local") or "local",
        external_subject=getattr(user, "external_subject", None),
        valid_from=_iso(getattr(user, "valid_from", None)),
        valid_until=_iso(getattr(user, "valid_until", None)),
    )


def _token_response(tokens) -> SubscriberTokenResponse:
    return SubscriberTokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_in=tokens.expires_in,
    )


def _login_impl(payload: LoginRequest, db: DbSession, request: Request) -> SubscriberTokenResponse:
    settings = get_settings()
    if settings.subscriber_identity_mode == "disabled":
        require_feature("enable_radius_login", settings)

    ip = _client_ip(request)
    rate_key = f"{ip}:{payload.username.strip().lower()}"
    if not login_rate_limiter.allow(
        rate_key,
        limit=int(settings.subscriber_login_rate_limit),
        window_seconds=int(settings.subscriber_login_rate_window_seconds),
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "rate_limited", "message": "Too many login attempts. Try again later."},
        )

    outcome = login_subscriber(
        db,
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
        detail: str | dict
        if outcome.http_status in {403, 429, 503}:
            detail = {"code": outcome.code, "message": outcome.detail}
        else:
            detail = outcome.detail or GENERIC_FAILURE
        raise HTTPException(status_code=outcome.http_status, detail=detail)
    return _token_response(outcome.tokens)


@router.post("/subscriber/login", response_model=SubscriberTokenResponse)
def subscriber_login(payload: LoginRequest, db: DbSession, request: Request):
    return _login_impl(payload, db, request)


@router.post("/login", response_model=SubscriberTokenResponse)
def login(payload: LoginRequest, db: DbSession, request: Request):
    """Compatibility alias for POST /api/auth/subscriber/login."""
    return _login_impl(payload, db, request)


@router.post("/subscriber/refresh", response_model=SubscriberTokenResponse)
def subscriber_refresh(payload: RefreshRequest, db: DbSession):
    outcome = refresh_subscriber_tokens(db, refresh_token=payload.refresh_token)
    if not outcome.ok or outcome.tokens is None:
        raise HTTPException(
            status_code=outcome.http_status,
            detail={"code": outcome.code, "message": outcome.detail},
        )
    return _token_response(outcome.tokens)


@router.post("/subscriber/logout", response_model=Message)
def subscriber_logout(payload: LogoutRequest, db: DbSession, user: CurrentSubscriber):
    logout_subscriber(db, subscriber=user, refresh_token=payload.refresh_token)
    return Message(detail="Logged out")


@router.post("/logout", response_model=Message)
def logout(db: DbSession, user: CurrentSubscriber, payload: LogoutRequest = LogoutRequest()):
    logout_subscriber(
        db,
        subscriber=user,
        refresh_token=payload.refresh_token,
    )
    return Message(detail="Logged out")


@router.get("/me", response_model=SubscriberOut)
def me(user: CurrentSubscriber):
    return _subscriber_out(user)


@router.get("/subscriber/me", response_model=SubscriberOut)
def subscriber_me(user: CurrentSubscriber):
    return _subscriber_out(user)
