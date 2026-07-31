from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import TokenError, safe_decode_token
from app.db.session import get_db
from app.models.admin import AdminUser
from app.models.user import Subscriber

bearer = HTTPBearer(auto_error=False)
DbSession = Annotated[Session, Depends(get_db)]


def _token_payload(credentials: HTTPAuthorizationCredentials | None) -> dict:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        return safe_decode_token(credentials.credentials)
    except TokenError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc


def get_current_admin(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
) -> AdminUser:
    payload = _token_payload(credentials)
    if payload.get("typ") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin token required")
    admin = db.get(AdminUser, int(payload["sub"]))
    if not admin or not admin.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found")
    return admin


def get_current_subscriber(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
) -> Subscriber:
    payload = _token_payload(credentials)
    if payload.get("typ") != "subscriber":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Subscriber token required")
    user = db.get(Subscriber, int(payload["sub"]))
    if not user or user.status != "active":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Subscriber not found")
    return user


def get_optional_subscriber(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)] = None,
) -> Subscriber | None:
    if credentials is None:
        return None
    try:
        return get_current_subscriber(db, credentials)
    except HTTPException:
        return None


CurrentAdmin = Annotated[AdminUser, Depends(get_current_admin)]
CurrentSubscriber = Annotated[Subscriber, Depends(get_current_subscriber)]
OptionalSubscriber = Annotated[Subscriber | None, Depends(get_optional_subscriber)]
