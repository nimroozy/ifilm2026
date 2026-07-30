from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import CurrentSubscriber, DbSession
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import Subscriber
from app.schemas.auth import LoginRequest, SubscriberOut
from app.schemas.common import Message, TokenResponse
from app.services.radius import RadiusService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: DbSession):
    radius = RadiusService().authenticate(payload.username, payload.password)
    if not radius.success:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=radius.message)

    user = db.query(Subscriber).filter(Subscriber.username == payload.username).one_or_none()
    if user is None:
        user = Subscriber(
            username=payload.username,
            hashed_password=hash_password(payload.password),
            name=payload.username,
            branch=radius.branch or "Kabul",
            package=radius.package or "Standard",
            expiration=radius.expiration or "",
            status="active",
            radius_synced=True,
        )
        db.add(user)
    else:
        if user.hashed_password and not verify_password(payload.password, user.hashed_password):
            # Radius accepted; refresh local hash to keep offline fallback in sync.
            user.hashed_password = hash_password(payload.password)
        user.branch = radius.branch or user.branch
        user.package = radius.package or user.package
        user.expiration = radius.expiration or user.expiration
        user.status = "active"
        user.radius_synced = True
        user.last_activity = datetime.now(timezone.utc)
        db.add(user)

    db.commit()
    db.refresh(user)
    token = create_access_token(str(user.id), claims={"typ": "subscriber", "username": user.username})
    return TokenResponse(access_token=token)


@router.post("/logout", response_model=Message)
def logout(_: CurrentSubscriber):
    return Message(detail="Logged out")


@router.get("/me", response_model=SubscriberOut)
def me(user: CurrentSubscriber):
    return user
